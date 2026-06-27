"""Matching router: operator review queue + manual match assignment."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..enums import MatchMethod, MatchStatus
from ..models import MatchEvent, Partner, PriceItem, Service
from ..normalization import build_matcher, seed_services
from ..schemas import MatchCandidate, MatchRequest, PriceItemOut, UnmatchedItemOut
from ..auth.deps import require_admin
from .deps import Pagination, get_db, pagination

router = APIRouter(tags=["matching"], dependencies=[Depends(require_admin)])

# needs_review surfaces before unmatched in the operator queue.
_STATUS_ORDER = {
    MatchStatus.needs_review: 0,
    MatchStatus.unmatched: 1,
}


@router.get("/unmatched", response_model=list[UnmatchedItemOut])
def list_unmatched(
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[UnmatchedItemOut]:
    """Active items needing operator attention, with fresh match candidates."""
    rows = (
        db.query(PriceItem, Partner)
        .outerjoin(Partner, PriceItem.partner_id == Partner.partner_id)
        .filter(
            PriceItem.is_active.is_(True),
            PriceItem.match_status.in_(
                [MatchStatus.unmatched, MatchStatus.needs_review]
            ),
        )
        .all()
    )

    # One matcher per request, reused across every item.
    matcher = build_matcher(db)

    out: list[UnmatchedItemOut] = []
    for item, partner in rows:
        result = matcher.match(item.service_name_raw)
        candidates = [
            MatchCandidate(
                service_id=c.service_id,
                service_name=c.service_name,
                category=c.category,
                score=c.score,
                method=c.method,
            )
            for c in result.candidates
        ]
        out.append(
            UnmatchedItemOut(
                item_id=item.item_id,
                doc_id=item.doc_id,
                partner_id=item.partner_id,
                partner_name=partner.name if partner is not None else None,
                service_name_raw=item.service_name_raw,
                service_code_source=item.service_code_source,
                price_resident_kzt=item.price_resident_kzt,
                match_status=item.match_status,
                match_confidence=item.match_confidence,
                candidates=candidates,
            )
        )

    out.sort(
        key=lambda r: (
            _STATUS_ORDER.get(r.match_status, 2),
            -(r.match_confidence or 0.0),
        )
    )
    return out[page.offset : page.offset + page.limit]


@router.post("/match", response_model=PriceItemOut)
def match_item(body: MatchRequest, db: Session = Depends(get_db)) -> PriceItem:
    """Manually assign (or create) a catalog service for a price item."""
    item = db.get(PriceItem, body.item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Price item not found")

    old_service_id = item.service_id
    action = "match"

    if body.new_service is not None:
        seed_services(
            db,
            [
                {
                    "service_name": body.new_service.service_name,
                    "synonyms": list(body.new_service.synonyms or []),
                    "category": body.new_service.category,
                    "icd_code": body.new_service.icd_code,
                }
            ],
        )
        svc = (
            db.query(Service)
            .filter(Service.service_name == body.new_service.service_name)
            .one()
        )
        service_id = svc.service_id
        action = "create"
    elif body.service_id is not None:
        svc = db.get(Service, body.service_id)
        if svc is None:
            raise HTTPException(status_code=404, detail="Service not found")
        service_id = body.service_id
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either service_id or new_service.",
        )

    item.service_id = service_id
    item.match_status = MatchStatus.matched_manual
    item.match_method = MatchMethod.manual
    item.match_confidence = 1.0
    item.needs_review = False

    db.add(
        MatchEvent(
            item_id=item.item_id,
            old_service_id=old_service_id,
            new_service_id=service_id,
            action=action,
            note=body.note,
            operator=body.operator or "operator",
        )
    )
    db.commit()
    db.refresh(item)
    return item
