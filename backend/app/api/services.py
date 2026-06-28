"""Services router: catalog browse + per-service partner prices + category tree."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from ..models import Partner, PriceItem, Service
from ..schemas import (
    PartnerOut,
    PartnerPriceOut,
    ServiceOut,
    ServiceTreeResponse,
)
from .deps import Pagination, get_db, pagination

router = APIRouter(tags=["services"])


# --------------------------------------------------------------------------- #
# Generic N-level tree builder (shared by the catalog + partner price trees).  #
# --------------------------------------------------------------------------- #
def effective_path(path: list[str] | None, fallback: str | None) -> list[str]:
    """The path to file a leaf under: explicit path, else [fallback], else Other."""
    if path:
        return [str(p) for p in path if str(p).strip()]
    if fallback and str(fallback).strip():
        return [str(fallback).strip()]
    return ["Без категории"]


def catalog_path(svc: Service) -> list[str]:
    """Where a catalog service is filed in the browse tree.

    Prefers the explicit ``category_path`` (organizer hierarchy), then the flat
    ``category`` string, then the service's primary specialty (real organizer
    catalogs ship specialties but no category column), then "Без категории".
    """
    if svc.category_path or (svc.category and str(svc.category).strip()):
        return effective_path(svc.category_path, svc.category)
    specs = sorted(
        (s.specialty.strip() for s in (svc.specialties or []) if s.specialty and s.specialty.strip()),
        key=str.lower,
    )
    if specs:
        return [specs[0]]
    return ["Без категории"]


def build_category_tree(entries: list[tuple[list[str], Any]]) -> list[dict]:
    """Build nested ``TreeNode`` dicts from ``(path, leaf)`` pairs.

    Every emitted node sits on the path of at least one leaf, so the "only
    include nodes that have services (directly or via descendants)" rule holds
    by construction. Sorting is done in Python (``str.lower``) which is
    Cyrillic-safe, unlike SQLite's ASCII-only ``LOWER()``.
    """
    roots: dict[str, dict] = {}
    for path, leaf in entries:
        level = roots
        node: dict | None = None
        acc: list[str] = []
        for name in path:
            acc = acc + [name]
            node = level.get(name)
            if node is None:
                node = {"name": name, "path": list(acc), "children": {}, "services": []}
                level[name] = node
            level = node["children"]
        if node is not None:
            node["services"].append(leaf)

    def finalize(level: dict[str, dict]) -> list[dict]:
        out: list[dict] = []
        for name in sorted(level.keys(), key=lambda s: s.lower()):
            n = level[name]
            out.append(
                {
                    "name": n["name"],
                    "path": n["path"],
                    "children": finalize(n["children"]),
                    "services": n["services"],
                }
            )
        return out

    return finalize(roots)


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


@router.get("/services/tree", response_model=ServiceTreeResponse)
def services_tree(
    is_active: bool = True,
    db: Session = Depends(get_db),
) -> ServiceTreeResponse:
    """The catalog as an N-level tree built from ``Service.category_path``.

    ``{ "tree": [TreeNode] }`` with ``TreeNode = {name, path, children,
    services}``; services are the catalog leaves attached at each node. Only
    nodes that contain services (directly or via descendants) appear.
    """
    query = db.query(Service).options(selectinload(Service.specialties))
    if is_active is not None:
        query = query.filter(Service.is_active.is_(is_active))
    services = query.order_by(Service.service_name).all()

    entries: list[tuple[list[str], ServiceOut]] = [
        (catalog_path(svc), ServiceOut.model_validate(svc)) for svc in services
    ]
    return ServiceTreeResponse(tree=build_category_tree(entries))


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
