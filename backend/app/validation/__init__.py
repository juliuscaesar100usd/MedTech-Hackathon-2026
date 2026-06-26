"""Validation / verification / currency / price-versioning package (spec §4.4).

Public surface re-exported for the ingestion pipeline and API layers.
"""
from __future__ import annotations

from .currency import convert_to_kzt, get_rate
from .types import ValidationOutcome
from .validators import validate_row
from .verification import verify_item
from .versioning import finalize_document_status, upsert_with_versioning

__all__ = [
    "validate_row",
    "convert_to_kzt",
    "get_rate",
    "upsert_with_versioning",
    "finalize_document_status",
    "verify_item",
    "ValidationOutcome",
]
