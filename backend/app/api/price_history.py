"""Price-history router: per-(service, partner) price timeline with anomaly flags.

Surfaces the version history that ``validation.versioning.upsert_with_versioning``
and ``ingestion.pipeline.reconcile_active_versions`` already maintain — every
:class:`PriceItem` (active *or* archived) for a (service, partner) pair is a
point on the price timeline. ``PRICE_ANOMALY`` in an item's ``anomaly_flags``
marks a >50% jump vs. the previous version (spec §4.4); we expose that as a
simple ``is_anomaly`` boolean so the client can flag the point.

This router reads the existing model + versioning logic; it does not redefine
or duplicate either.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models import Partner, PriceItem, Service
from ..schemas import ORMModel
from .deps import get_db

router = APIRouter(tags=["price-history"])


class PriceHistoryPoint(ORMModel):
    """One version on a (service, partner) price line, oldest-first ordered."""

    effective_date: date | None = None
    price_resident_kzt: Decimal | None = None
    price_nonresident_kzt: Decimal | None = None
    is_anomaly: bool = False
    version: int = 1


@router.get(
    "/services/{service_id}/partners/{partner_id}/history",
    response_model=list[PriceHistoryPoint],
)
def service_partner_price_history(
    service_id: str,
    partner_id: str,
    db: Session = Depends(get_db),
) -> list[PriceHistoryPoint]:
    """Chronological price timeline for one service at one partner.

    Returns every version (active + archived) ordered by effective date, oldest
    first, so the client can draw a line chart. A point is flagged
    ``is_anomaly`` when versioning recorded a ``PRICE_ANOMALY`` (a >50% change
    from the previous price, spec §4.4).
    """
    if db.get(Service, service_id) is None:
        raise HTTPException(status_code=404, detail="Service not found")
    if db.get(Partner, partner_id) is None:
        raise HTTPException(status_code=404, detail="Partner not found")

    items = (
        db.query(PriceItem)
        .filter(
            PriceItem.service_id == service_id,
            PriceItem.partner_id == partner_id,
        )
        .order_by(
            PriceItem.effective_date.asc(),
            PriceItem.version.asc(),
            PriceItem.created_at.asc(),
        )
        .all()
    )

    return [
        PriceHistoryPoint(
            effective_date=item.effective_date,
            price_resident_kzt=item.price_resident_kzt,
            price_nonresident_kzt=item.price_nonresident_kzt,
            is_anomaly="PRICE_ANOMALY" in (item.anomaly_flags or []),
            version=item.version or 1,
        )
        for item in items
    ]
