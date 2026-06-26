"""Operator verification actions (spec §4.4) used by the API.

An operator can approve or reject a :class:`PriceItem`, optionally correcting the
matched service and prices. Every action is recorded as a :class:`MatchEvent`
for traceability. ``verify_item`` commits.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from ..enums import MatchMethod, MatchStatus
from ..models import MatchEvent, PriceItem


class ItemNotFoundError(LookupError):
    """Raised when the targeted PriceItem does not exist."""


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def verify_item(
    db: Session,
    item_id: str,
    *,
    approve: bool = True,
    service_id: str | None = None,
    price_resident_kzt: Decimal | float | None = None,
    price_nonresident_kzt: Decimal | float | None = None,
    note: str | None = None,
    operator: str = "operator",
) -> PriceItem:
    """Apply an operator's verify/reject decision to a price item.

    Optional corrections (service, prices) are applied first; assigning a
    ``service_id`` marks the match as manual. ``approve=True`` clears the review
    flag. A :class:`MatchEvent` records the action. Commits before returning.
    """
    item = db.get(PriceItem, item_id)
    if item is None:
        raise ItemNotFoundError(f"PriceItem {item_id!r} not found.")

    old_service_id = item.service_id

    # --- optional corrections -------------------------------------------- #
    if price_resident_kzt is not None:
        item.price_resident_kzt = _as_decimal(price_resident_kzt)
    if price_nonresident_kzt is not None:
        item.price_nonresident_kzt = _as_decimal(price_nonresident_kzt)
    if service_id is not None:
        item.service_id = service_id
        item.match_status = MatchStatus.matched_manual
        item.match_method = MatchMethod.manual

    # --- verification state ---------------------------------------------- #
    item.is_verified = approve
    item.verification_note = note
    item.verified_by = operator
    item.verified_at = datetime.now(timezone.utc)
    if approve:
        item.needs_review = False

    db.add(
        MatchEvent(
            item_id=item.item_id,
            old_service_id=old_service_id,
            new_service_id=item.service_id,
            action="verify" if approve else "reject",
            note=note,
            operator=operator,
        )
    )

    db.commit()
    db.refresh(item)
    return item
