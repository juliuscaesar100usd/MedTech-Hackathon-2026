"""Shared API dependencies: DB session + pagination."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query

from ..database import get_db  # re-exported for routers

__all__ = ["get_db", "Pagination", "pagination"]

# Caps so a client can never ask for an unbounded result set. The catalog browse
# (Услуги) lists the whole normalized catalog (~7k services after promoting every
# price-list service) on one page, so the ceiling must clear it; 10000 stays a
# sane guard against unbounded queries.
MAX_LIMIT = 10000
DEFAULT_LIMIT = 100


@dataclass
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Max rows to return."),
    offset: int = Query(0, ge=0, description="Rows to skip."),
) -> Pagination:
    """Dependency returning a sane, capped (limit, offset) pair."""
    return Pagination(limit=min(max(limit, 1), MAX_LIMIT), offset=max(offset, 0))
