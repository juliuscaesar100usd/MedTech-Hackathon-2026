"""Service-layer helpers used by the API (search + dashboard stats)."""
from __future__ import annotations

from .search_service import search as search
from .stats_service import compute_dashboard as compute_dashboard

__all__ = ["search", "compute_dashboard"]
