"""Partners router: directory + per-partner service price lists."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models import Partner, PriceItem, Service
from ..schemas import PartnerOut, ServicePriceOut
from .deps import Pagination, get_db, pagination

router = APIRouter(tags=["partners"])


@router.get("/partners", response_model=list[PartnerOut])
def list_partners(
    city: str | None = None,
    is_active: bool | None = None,
    q: str | None = None,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[Partner]:
    """List partner clinics with optional city / activity / name filters."""
    query = db.query(Partner)
    if is_active is not None:
        query = query.filter(Partner.is_active.is_(is_active))

    rows = query.order_by(Partner.name).all()

    # Python-side text filters: SQLite LOWER() is ASCII-only (breaks Cyrillic).
    if city:
        c = city.strip().lower()
        rows = [p for p in rows if (p.city or "").lower() == c]
    if q:
        needle = q.strip().lower()
        rows = [p for p in rows if needle in (p.name or "").lower()]

    return rows[page.offset : page.offset + page.limit]


@router.get("/partners/{partner_id}", response_model=PartnerOut)
def get_partner(partner_id: str, db: Session = Depends(get_db)) -> Partner:
    partner = db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    return partner


@router.get("/partners/{partner_id}/services", response_model=list[ServicePriceOut])
def partner_services(
    partner_id: str,
    db: Session = Depends(get_db),
) -> list[ServicePriceOut]:
    """All active price items for a partner, ordered by category then name."""
    partner = db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")

    rows = (
        db.query(PriceItem, Service)
        .outerjoin(Service, PriceItem.service_id == Service.service_id)
        .filter(PriceItem.partner_id == partner_id, PriceItem.is_active.is_(True))
        .all()
    )

    out = [
        ServicePriceOut(
            item_id=item.item_id,
            service_id=item.service_id,
            service_name=service.service_name if service is not None else None,
            service_name_raw=item.service_name_raw,
            category=service.category if service is not None else None,
            price_resident_kzt=item.price_resident_kzt,
            price_nonresident_kzt=item.price_nonresident_kzt,
            currency_original=item.currency_original,
            effective_date=item.effective_date,
            match_status=item.match_status,
            is_verified=item.is_verified,
        )
        for item, service in rows
    ]

    out.sort(
        key=lambda r: (
            (r.category or "￿").lower(),
            (r.service_name or r.service_name_raw or "").lower(),
        )
    )
    return out
