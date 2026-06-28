"""Partners router: directory + per-partner service price lists + price tree."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models import Partner, PriceItem, Service
from ..schemas import PartnerOut, PartnerTreeResponse, ServicePriceOut
from .deps import Pagination, get_db, pagination
from .services import build_category_tree, effective_path

router = APIRouter(tags=["partners"])


def _service_price_out(item: PriceItem, service: Service | None) -> ServicePriceOut:
    """Build a :class:`ServicePriceOut` (incl. the new hierarchy fields)."""
    return ServicePriceOut(
        item_id=item.item_id,
        service_id=item.service_id,
        service_name=service.service_name if service is not None else None,
        service_name_raw=item.service_name_raw,
        category=service.category if service is not None else None,
        category_path=(service.category_path if service is not None else None),
        section_path=item.section_path,
        price_resident_kzt=item.price_resident_kzt,
        price_nonresident_kzt=item.price_nonresident_kzt,
        currency_original=item.currency_original,
        effective_date=item.effective_date,
        match_status=item.match_status,
        is_verified=item.is_verified,
    )


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

    out = [_service_price_out(item, service) for item, service in rows]

    out.sort(
        key=lambda r: (
            (r.category or "￿").lower(),
            (r.service_name or r.service_name_raw or "").lower(),
        )
    )
    return out


@router.get("/partners/{partner_id}/tree", response_model=PartnerTreeResponse)
def partner_tree(
    partner_id: str,
    db: Session = Depends(get_db),
) -> PartnerTreeResponse:
    """The partner's active price list grouped by ``PriceItem.section_path``.

    Same ``TreeNode`` shape as ``/services/tree`` but with
    :class:`ServicePriceOut` leaves (resident/non-resident prices kept). Items
    with no section nesting fall back to the matched service's category, then a
    "Без категории" bucket — so every priced item is still reachable.
    """
    partner = db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")

    rows = (
        db.query(PriceItem, Service)
        .outerjoin(Service, PriceItem.service_id == Service.service_id)
        .filter(PriceItem.partner_id == partner_id, PriceItem.is_active.is_(True))
        .order_by(PriceItem.service_name_raw)
        .all()
    )

    entries: list[tuple[list[str], ServicePriceOut]] = []
    for item, service in rows:
        fallback = item.section or (service.category if service is not None else None)
        path = effective_path(item.section_path, fallback)
        entries.append((path, _service_price_out(item, service)))

    return PartnerTreeResponse(tree=build_category_tree(entries))
