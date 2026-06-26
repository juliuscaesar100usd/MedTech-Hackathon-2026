"""Services router: catalog browse + per-service partner prices."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models import Partner, PriceItem, Service
from ..schemas import PartnerOut, PartnerPriceOut, ServiceOut
from .deps import Pagination, get_db, pagination

router = APIRouter(tags=["services"])


@router.get("/services", response_model=list[ServiceOut])
def list_services(
    category: str | None = None,
    q: str | None = None,
    is_active: bool = True,
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[Service]:
    """List catalog services.

    ``q`` matches the service name OR any synonym (case-insensitive).
    ``category`` is an exact (case-insensitive) match.
    """
    query = db.query(Service)
    if is_active is not None:
        query = query.filter(Service.is_active.is_(is_active))

    rows = query.order_by(Service.service_name).all()

    if category:
        # Python-side compare: SQLite LOWER() is ASCII-only (breaks Cyrillic).
        cat = category.strip().lower()
        rows = [s for s in rows if (s.category or "").lower() == cat]

    if q:
        needle = q.strip().lower()
        filtered: list[Service] = []
        for svc in rows:
            if needle in (svc.service_name or "").lower():
                filtered.append(svc)
                continue
            if any(needle in str(syn).lower() for syn in (svc.synonyms or [])):
                filtered.append(svc)
        rows = filtered

    return rows[page.offset : page.offset + page.limit]


@router.get("/services/{service_id}/partners", response_model=list[PartnerPriceOut])
def service_partners(
    service_id: str,
    db: Session = Depends(get_db),
) -> list[PartnerPriceOut]:
    """All active priced offerings for a service, cheapest (resident) first."""
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")

    rows = (
        db.query(PriceItem, Partner)
        .join(Partner, PriceItem.partner_id == Partner.partner_id)
        .filter(PriceItem.service_id == service_id, PriceItem.is_active.is_(True))
        .all()
    )

    out = [
        PartnerPriceOut(
            partner=PartnerOut.model_validate(partner),
            item_id=item.item_id,
            service_name_raw=item.service_name_raw,
            price_resident_kzt=item.price_resident_kzt,
            price_nonresident_kzt=item.price_nonresident_kzt,
            currency_original=item.currency_original,
            effective_date=item.effective_date,
            is_verified=item.is_verified,
            match_confidence=item.match_confidence,
        )
        for item, partner in rows
    ]

    # Sort by resident price ascending, nulls last.
    out.sort(
        key=lambda r: (
            r.price_resident_kzt is None,
            r.price_resident_kzt if r.price_resident_kzt is not None else 0,
        )
    )
    return out
