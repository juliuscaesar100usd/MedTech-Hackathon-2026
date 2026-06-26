"""The per-document ingestion pipeline (parse -> resolve -> match -> validate
-> version) plus the synchronous batch driver used by the CLI.

Both entry points take an explicit ``db`` Session so tests can inject their own
engine. The matcher is built once per batch (catalog read + index build is the
expensive part) and reused across documents.
"""
from __future__ import annotations

import traceback
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings as default_settings
from ..enums import BatchStatus, MatchStatus, ParseStatus
from ..models import IngestionBatch, PriceDocument, PriceItem
from ..normalization import Matcher, build_matcher, normalize
from ..parsers import parse_file
from ..validation import (
    finalize_document_status,
    upsert_with_versioning,
    validate_row,
)
from .partner import filename_hints, resolve_partner

_MATCHED = {MatchStatus.matched_auto, MatchStatus.matched_manual}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _first(*values):
    """Return the first non-empty value, or None."""
    for v in values:
        if v:
            return v
    return None


def process_document(
    db: Session,
    doc_id: str,
    matcher: Matcher | None = None,
) -> PriceDocument:
    """Run the full pipeline for one :class:`PriceDocument`.

    On success the document ends ``done`` / ``needs_review`` with items staged;
    on failure it is marked ``error`` (and the exception is re-raised so a
    synchronous caller can react — batch drivers catch it per-document).
    """
    settings = default_settings
    if matcher is None:
        matcher = build_matcher(db, settings)

    doc = db.get(PriceDocument, doc_id)
    if doc is None:
        raise ValueError(f"PriceDocument {doc_id!r} not found")

    # 1) mark processing.
    doc.parse_status = ParseStatus.processing
    db.commit()

    try:
        # 2) parse the stored original.
        parsed = parse_file(doc.stored_path, doc.file_name)

        fn_hints = filename_hints(doc.file_name)

        # 3) resolve partner (parsed hints, with filename fallback for name).
        name_hint = _first(parsed.partner_name_hint, fn_hints["partner_name"])
        partner = resolve_partner(
            db,
            name_hint=name_hint,
            city_hint=parsed.city_hint,
            address_hint=parsed.address_hint,
            bin_hint=parsed.bin_hint,
            email_hint=parsed.email_hint,
            phone_hint=parsed.phone_hint,
        )
        doc.partner_id = partner.partner_id
        doc.language = parsed.language
        # partner confidence heuristic.
        if parsed.bin_hint:
            doc.partner_confidence = 0.9
        elif name_hint:
            doc.partner_confidence = 0.6
        else:
            doc.partner_confidence = 0.3

        # 4) effective date: parsed hint else filename date.
        effective_date: date | None = _first(
            parsed.effective_date_hint, fn_hints["effective_date"]
        )
        doc.effective_date = effective_date

        # 5) per-row match + validate + version.
        n_items = 0
        n_matched = 0
        row_logs: list[str] = []
        for row in parsed.rows:
            match = matcher.match(row.service_name_raw)
            outcome = validate_row(row, effective_date, settings)
            item = upsert_with_versioning(
                db,
                document=doc,
                partner_id=doc.partner_id,
                row=row,
                outcome=outcome,
                match=match,
                settings=settings,
            )
            if item is None:
                # Skipped (empty name etc.) — keep the validator's note.
                row_logs.extend(outcome.log_messages)
                continue
            n_items += 1
            if item.match_status in _MATCHED:
                n_matched += 1
            row_logs.extend(outcome.log_messages)

        # 6) document-level fields + status.
        doc.raw_content = (parsed.raw_text or "")[:200000]
        doc.n_items = n_items
        doc.n_matched = n_matched
        doc.parse_log = "\n".join(parsed.warnings + row_logs)[:50000]
        db.flush()  # ensure staged items are visible to finalize_document_status
        doc.parse_status = finalize_document_status(doc, n_items, n_errors=0)
        doc.parsed_at = _now()
        db.commit()
        return doc

    except Exception as exc:  # noqa: BLE001 - want every failure recorded
        db.rollback()
        # Re-fetch: rollback may have expired/detached the instance.
        doc = db.get(PriceDocument, doc_id)
        if doc is not None:
            doc.parse_status = ParseStatus.error
            tb = traceback.format_exc(limit=6)
            prefix = (doc.parse_log + "\n") if doc.parse_log else ""
            doc.parse_log = (prefix + f"ERROR: {exc}\n{tb}")[:50000]
            doc.parsed_at = _now()
            db.commit()
        raise


def reconcile_active_versions(db: Session) -> int:
    """Ensure exactly the price with the latest effective_date is active per
    (partner, service line), regardless of the order documents were processed.

    Price history is preserved (older versions stay, just archived). Grouping is
    by service_id when matched, otherwise by the normalized raw name. Returns the
    number of items whose is_active flag changed.
    """
    groups: dict[tuple, list[PriceItem]] = defaultdict(list)
    for it in db.query(PriceItem).all():
        key = (it.partner_id, it.service_id or ("raw:" + normalize(it.service_name_raw)))
        groups[key].append(it)

    def rank(i: PriceItem):
        return (
            i.effective_date or date.min,
            i.version or 0,
            i.created_at.timestamp() if i.created_at else 0.0,
        )

    changed = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        winner = max(group, key=rank)
        for it in group:
            should_be = it is winner
            if it.is_active != should_be:
                it.is_active = should_be
                changed += 1
    if changed:
        db.commit()
    return changed


def process_pending(
    db: Session,
    batch_id: str | None = None,
    matcher: Matcher | None = None,
) -> dict:
    """Synchronously process every pending document (optionally one batch).

    Builds the matcher once, catches per-document failures so one bad file does
    not abort the run, and returns a small summary dict.
    """
    if matcher is None:
        matcher = build_matcher(db, default_settings)

    stmt = select(PriceDocument.doc_id).where(
        PriceDocument.parse_status == ParseStatus.pending
    )
    if batch_id is not None:
        stmt = stmt.where(PriceDocument.batch_id == batch_id)
    doc_ids = list(db.execute(stmt).scalars())

    summary = {
        "total": len(doc_ids),
        "done": 0,
        "needs_review": 0,
        "error": 0,
        "n_items": 0,
        "n_matched": 0,
    }

    for doc_id in doc_ids:
        try:
            doc = process_document(db, doc_id, matcher=matcher)
        except Exception:  # noqa: BLE001 - recorded on the doc already
            summary["error"] += 1
            continue
        if doc.parse_status == ParseStatus.done:
            summary["done"] += 1
        elif doc.parse_status == ParseStatus.needs_review:
            summary["needs_review"] += 1
        elif doc.parse_status == ParseStatus.error:
            summary["error"] += 1
        summary["n_items"] += doc.n_items or 0
        summary["n_matched"] += doc.n_matched or 0

    # After the whole run, make the latest-dated price active per service line.
    summary["reactivated"] = reconcile_active_versions(db)

    # Finalize batch status (the worker path does this for uploads; do it here
    # for the synchronous CLI/bootstrap path so batches don't linger as
    # "processing" in the dashboard).
    finalize_batch_ids = (
        [batch_id]
        if batch_id is not None
        else [
            bid
            for (bid,) in db.execute(
                select(PriceDocument.batch_id).distinct()
            ).all()
            if bid is not None
        ]
    )
    for bid in finalize_batch_ids:
        _finalize_batch(db, bid)
    return summary


def _finalize_batch(db: Session, batch_id: str) -> None:
    """Recompute a batch's counters and terminal status from its documents."""
    batch = db.get(IngestionBatch, batch_id)
    if batch is None:
        return
    docs = list(
        db.execute(
            select(PriceDocument).where(PriceDocument.batch_id == batch_id)
        ).scalars()
    )
    processed = sum(
        1 for d in docs
        if d.parse_status in (ParseStatus.done, ParseStatus.needs_review)
    )
    error_files = sum(1 for d in docs if d.parse_status == ParseStatus.error)
    pending = sum(
        1 for d in docs
        if d.parse_status in (ParseStatus.pending, ParseStatus.processing)
    )
    batch.processed_files = processed
    batch.error_files = error_files
    if pending:
        batch.status = BatchStatus.processing
    elif error_files == 0:
        batch.status = BatchStatus.done
    elif processed > 0:
        batch.status = BatchStatus.partial
    else:
        batch.status = BatchStatus.error
    if not pending:
        batch.finished_at = _now()
    db.commit()
