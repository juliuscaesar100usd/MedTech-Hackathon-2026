"""REST API package — FastAPI routers for MedArchive (hackathon Case 2)."""
from __future__ import annotations

from . import admin, matching, partners, search, services

__all__ = ["services", "partners", "search", "matching", "admin"]
