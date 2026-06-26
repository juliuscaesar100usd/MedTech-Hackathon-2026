"""Dashboard statistics aggregation (DB-portable)."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..enums import MatchStatus, ParseStatus
from ..models import IngestionBatch, Partner, PriceDocument, PriceItem, Service
from ..schemas import BatchOut, DashboardStats


def _count(db: Session, model, *filters) -> int:
    q = db.query(func.count()).select_from(model)
    for f in filters:
        q = q.filter(f)
    return int(q.scalar() or 0)


def compute_dashboard(db: Session) -> DashboardStats:
    """Aggregate counts + rates + breakdowns for the operator dashboard."""
    partners = _count(db, Partner)
    services = _count(db, Service)

    documents = _count(db, PriceDocument)
    documents_done = _count(db, PriceDocument, PriceDocument.parse_status == ParseStatus.done)
    documents_error = _count(db, PriceDocument, PriceDocument.parse_status == ParseStatus.error)
    documents_pending = _count(
        db, PriceDocument, PriceDocument.parse_status == ParseStatus.pending
    )

    active = PriceItem.is_active.is_(True)
    price_items = _count(db, PriceItem, active)
    items_matched_auto = _count(
        db, PriceItem, active, PriceItem.match_status == MatchStatus.matched_auto
    )
    items_matched_manual = _count(
        db, PriceItem, active, PriceItem.match_status == MatchStatus.matched_manual
    )
    # Verification queue size = anything an operator must review (validation
    # flags, anomalies, or a match in the gray zone). This mirrors exactly what
    # GET /admin/verification returns (the needs_review boolean).
    items_needs_review = _count(
        db, PriceItem, active, PriceItem.needs_review.is_(True)
    )
    items_unmatched = _count(
        db, PriceItem, active, PriceItem.match_status == MatchStatus.unmatched
    )
    items_verified = _count(db, PriceItem, active, PriceItem.is_verified.is_(True))

    # Items with at least one anomaly flag (JSON list non-empty). Done in Python
    # to stay portable across SQLite/Postgres JSON handling.
    items_with_anomalies = sum(
        1
        for (flags,) in db.query(PriceItem.anomaly_flags)
        .filter(active)
        .all()
        if flags
    )

    total = price_items or 0
    matched = items_matched_auto + items_matched_manual
    normalization_rate = (matched / total) if total else 0.0
    auto_normalization_rate = (items_matched_auto / total) if total else 0.0
    verification_rate = (items_verified / total) if total else 0.0

    # by_category: active item counts grouped by the matched service's category.
    by_category: dict[str, int] = {}
    cat_rows = (
        db.query(Service.category, func.count(PriceItem.item_id))
        .join(PriceItem, PriceItem.service_id == Service.service_id)
        .filter(active)
        .group_by(Service.category)
        .all()
    )
    for category, cnt in cat_rows:
        by_category[category or "Без категории"] = int(cnt or 0)

    # by_city: partner counts grouped by city.
    by_city: dict[str, int] = {}
    city_rows = (
        db.query(Partner.city, func.count(Partner.partner_id))
        .group_by(Partner.city)
        .all()
    )
    for city, cnt in city_rows:
        by_city[city or "Неизвестно"] = int(cnt or 0)

    recent = (
        db.query(IngestionBatch)
        .order_by(IngestionBatch.created_at.desc())
        .limit(5)
        .all()
    )
    recent_batches = [BatchOut.model_validate(b) for b in recent]

    return DashboardStats(
        partners=partners,
        services=services,
        documents=documents,
        documents_done=documents_done,
        documents_error=documents_error,
        documents_pending=documents_pending,
        price_items=price_items,
        items_matched_auto=items_matched_auto,
        items_matched_manual=items_matched_manual,
        items_needs_review=items_needs_review,
        items_unmatched=items_unmatched,
        items_verified=items_verified,
        items_with_anomalies=items_with_anomalies,
        normalization_rate=round(normalization_rate, 4),
        auto_normalization_rate=round(auto_normalization_rate, 4),
        verification_rate=round(verification_rate, 4),
        by_category=by_category,
        by_city=by_city,
        recent_batches=recent_batches,
    )
