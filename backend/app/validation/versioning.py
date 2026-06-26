"""Price-history versioning, deduplication and the cross-row anomaly check
(spec §4.4) — the parts that need the database.

  * Duplicate (same clinic, service, date) -> dedup: keep new, archive old.
  * Price differs from previous version by > 50% -> PRICE_ANOMALY flag,
    needs manual confirmation.

``upsert_with_versioning`` builds one new :class:`PriceItem` from a parsed row,
its :class:`ValidationOutcome` and the matcher's :class:`MatchResult`, applies
dedup + anomaly logic, links the version chain, and stages it on the session
(the caller commits). ``finalize_document_status`` maps item counts to a
:class:`ParseStatus` for the owning document.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from ..config import Settings
from ..config import settings as default_settings
from ..enums import MatchMethod, MatchStatus, ParseStatus
from ..models import PriceDocument, PriceItem
from ..normalization.types import MatchResult
from ..parsers.base import ParsedRow
from .types import ValidationOutcome


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None


def upsert_with_versioning(
    db: Session,
    *,
    document: PriceDocument,
    partner_id: str | None,
    row: ParsedRow,
    outcome: ValidationOutcome,
    match: MatchResult,
    section: str | None = None,
    settings: Settings | None = None,
) -> PriceItem | None:
    """Create, version and stage a :class:`PriceItem`. Returns it, or None if
    the row was skipped by validation. Does NOT commit."""
    if outcome.skip:
        return None

    cfg = settings or default_settings
    name = (row.service_name_raw or "").strip()
    eff: date | None = document.effective_date

    needs_review = bool(outcome.needs_review) or (
        match is not None and match.status == MatchStatus.needs_review
    )

    item = PriceItem(
        doc_id=document.doc_id,
        partner_id=partner_id,
        service_name_raw=name,
        service_code_source=row.service_code_source,
        section=section,
        service_id=match.service_id if match is not None else None,
        price_resident_kzt=outcome.price_resident_kzt,
        price_nonresident_kzt=outcome.price_nonresident_kzt,
        price_original=outcome.price_original,
        currency_original=outcome.currency_original,
        fx_rate_to_kzt=outcome.fx_rate_to_kzt,
        match_status=(match.status if match is not None else MatchStatus.unmatched),
        match_method=(match.method if match is not None else MatchMethod.none),
        match_confidence=(match.score if match is not None else None),
        needs_review=needs_review,
        anomaly_flags=list(outcome.anomaly_flags),
        effective_date=eff,
        is_active=True,
        version=1,
    )

    # --- DEDUP: same partner + service + effective_date ------------------- #
    dup = db.execute(
        select(PriceItem)
        .where(
            PriceItem.partner_id == partner_id,
            PriceItem.service_name_raw == name,
            PriceItem.effective_date == eff,
            PriceItem.is_active.is_(True),
        )
        .order_by(PriceItem.version.desc())
    ).scalars().first()

    if dup is not None:
        dup.is_active = False
        item.version = (dup.version or 1) + 1
        item.previous_item_id = dup.item_id

    # --- ANOMALY vs the most recent prior version (different date) -------- #
    prior = db.execute(
        select(PriceItem)
        .where(
            PriceItem.partner_id == partner_id,
            PriceItem.service_name_raw == name,
            PriceItem.effective_date != eff,
        )
        .order_by(
            PriceItem.is_active.desc(),
            PriceItem.effective_date.desc(),
            PriceItem.version.desc(),
        )
    ).scalars().first()

    if prior is not None:
        old_price = _as_decimal(prior.price_resident_kzt)
        new_price = _as_decimal(item.price_resident_kzt)
        if old_price is not None and old_price != 0 and new_price is not None:
            change = abs(new_price - old_price) / abs(old_price)
            if change > Decimal(str(cfg.price_anomaly_pct)):
                if "PRICE_ANOMALY" not in item.anomaly_flags:
                    item.anomaly_flags.append("PRICE_ANOMALY")
                item.needs_review = True

        # Maintain a single active line per service: chain to the latest prior
        # version and archive whatever active prior remains (if dedup did not).
        if item.previous_item_id is None:
            item.previous_item_id = prior.item_id
            item.version = max(item.version, (prior.version or 1) + 1)
        if prior.is_active:
            prior.is_active = False

    db.add(item)
    return item


def finalize_document_status(
    document: PriceDocument,
    n_items: int,
    n_errors: int,
) -> ParseStatus:
    """Map item/error counts to a document :class:`ParseStatus`.

    Spec §4.4: a document with no recognizable data -> error; if any staged item
    needs review -> needs_review; otherwise done. The caller assigns the result.
    """
    if n_items <= 0:
        return ParseStatus.error

    # Resolve this document's items from the live session (the relationship
    # collection may be cached/stale when items were staged via db.add()).
    sess = object_session(document)
    if sess is not None:
        items = sess.execute(
            select(PriceItem).where(PriceItem.doc_id == document.doc_id)
        ).scalars().all()
    else:
        items = list(document.items)

    any_review = any(getattr(it, "needs_review", False) for it in items)
    if any_review:
        return ParseStatus.needs_review
    return ParseStatus.done
