"""Normalization / matching package (spec §4.3).

Public surface re-exported for the ingestion pipeline and API layers.
"""
from __future__ import annotations

from .catalog import load_catalog_from_file, load_services, seed_services
from .matcher import Matcher, build_matcher
from .text_utils import normalize
from .types import Candidate, MatchResult

__all__ = [
    "Matcher",
    "build_matcher",
    "MatchResult",
    "Candidate",
    "load_catalog_from_file",
    "seed_services",
    "load_services",
    "normalize",
]
