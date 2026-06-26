"""Result types returned by the normalization/matching engine.

These are the integration contract between the matcher and the ingestion
pipeline / API layer. Do not change field names without updating both sides.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..enums import MatchMethod, MatchStatus


@dataclass
class Candidate:
    service_id: str
    service_name: str
    category: str | None
    score: float          # normalized similarity in [0, 1]
    method: MatchMethod


@dataclass
class MatchResult:
    service_id: str | None          # chosen catalog service, or None
    score: float | None             # similarity of the chosen candidate
    method: MatchMethod             # how it was chosen
    status: MatchStatus             # matched_auto / needs_review / unmatched
    candidates: list[Candidate] = field(default_factory=list)  # ranked, best first
