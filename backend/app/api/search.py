"""Search router: unified service + partner search."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..models import Service
from ..schemas import SearchResponse
from ..services.search_service import search as run_search
from .deps import get_db

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search_endpoint(
    q: str = Query("", description="Free-text query (service name/synonym/category or partner/city)."),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """Search services and partners. Empty ``q`` returns an empty response."""
    resp = run_search(db, q)
    # Enrich service hits with the full category hierarchy (additive; the search
    # service itself stays untouched). One bulk lookup keyed by service_id.
    if resp.services:
        ids = [h.service_id for h in resp.services]
        paths = {
            sid: path
            for sid, path in db.query(Service.service_id, Service.category_path)
            .filter(Service.service_id.in_(ids))
            .all()
        }
        for hit in resp.services:
            hit.category_path = paths.get(hit.service_id)
    return resp
