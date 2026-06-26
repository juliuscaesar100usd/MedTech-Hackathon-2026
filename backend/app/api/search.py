"""Search router: unified service + partner search."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

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
    return run_search(db, q)
