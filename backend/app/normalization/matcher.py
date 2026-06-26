"""Service-name matcher (spec §4.3).

Pipeline per raw name:
  1. empty / too-short -> unmatched (method none, no candidates).
  2. exact normalized hit on a canonical name -> 1.0, exact, matched_auto.
  3. exact normalized hit on a synonym       -> 1.0, synonym, matched_auto.
  4. fuzzy (rapidfuzz) over all catalog texts (+ optional embedding merge).
     Status from the BEST candidate score against the configured thresholds.

All similarities live in [0, 1]. Candidates are deduped per service (best score
kept) and returned best-first.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from ..enums import MatchMethod, MatchStatus
from .catalog import load_services
from .embeddings import EmbeddingIndex
from .text_utils import normalize
from .types import Candidate, MatchResult

# Raw names shorter than this (after normalization) are not worth matching.
_MIN_LEN = 2


@dataclass
class _Row:
    """One catalog text entry feeding the fuzzy index."""

    text: str          # normalized text (name or synonym)
    service_id: str
    is_synonym: bool


def _fuzzy_score(query_norm: str, target_norm: str) -> float:
    """Robust similarity in [0,1] combining token_set_ratio and WRatio."""
    a = fuzz.token_set_ratio(query_norm, target_norm)
    b = fuzz.WRatio(query_norm, target_norm)
    return max(a, b) / 100.0


class Matcher:
    """Holds the catalog + precomputed indices and answers ``match`` queries."""

    def __init__(
        self,
        services: list,
        auto_threshold: float = 0.85,
        review_threshold: float = 0.60,
        embedding_index: EmbeddingIndex | None = None,
    ) -> None:
        self.auto_threshold = auto_threshold
        self.review_threshold = review_threshold
        self.embedding_index = embedding_index

        # Per-service metadata for building Candidate objects.
        self._meta: dict[str, dict] = {}
        # Exact / synonym lookups (normalized key -> service_id).
        self.exact: dict[str, str] = {}
        self.synonyms: dict[str, str] = {}
        # Flat fuzzy index.
        self.fuzzy_rows: list[_Row] = []
        # Parallel arrays for the (optional) embedding index.
        self._emb_texts: list[str] = []
        self._emb_service_ids: list[str] = []

        for svc in services:
            sid = svc.service_id
            self._meta[sid] = {
                "service_name": svc.service_name,
                "category": svc.category,
            }
            name_norm = normalize(svc.service_name)
            if name_norm:
                # First writer wins for exact names (catalog is deduped already).
                self.exact.setdefault(name_norm, sid)
                self.fuzzy_rows.append(_Row(name_norm, sid, is_synonym=False))
                self._emb_texts.append(svc.service_name)
                self._emb_service_ids.append(sid)
            for syn in svc.synonyms or []:
                syn_norm = normalize(syn)
                if not syn_norm:
                    continue
                self.synonyms.setdefault(syn_norm, sid)
                self.fuzzy_rows.append(_Row(syn_norm, sid, is_synonym=True))
                self._emb_texts.append(str(syn))
                self._emb_service_ids.append(sid)

        if self.embedding_index is not None and self.embedding_index.enabled:
            # Build may fail (lib missing / load error); available() guards use.
            self.embedding_index.build(self._emb_texts)

    # ------------------------------------------------------------------ #
    def _candidate(self, sid: str, score: float, method: MatchMethod) -> Candidate:
        m = self._meta[sid]
        return Candidate(
            service_id=sid,
            service_name=m["service_name"],
            category=m["category"],
            score=round(float(score), 4),
            method=method,
        )

    def _status_for(self, score: float) -> MatchStatus:
        if score >= self.auto_threshold:
            return MatchStatus.matched_auto
        if score >= self.review_threshold:
            return MatchStatus.needs_review
        return MatchStatus.unmatched

    # ------------------------------------------------------------------ #
    def match(self, raw_name: str, top_k: int = 5) -> MatchResult:
        norm = normalize(raw_name)

        # 1) empty / too short.
        if len(norm) < _MIN_LEN:
            return MatchResult(
                service_id=None,
                score=None,
                method=MatchMethod.none,
                status=MatchStatus.unmatched,
                candidates=[],
            )

        # 2) exact canonical name.
        sid = self.exact.get(norm)
        if sid is not None:
            cand = self._candidate(sid, 1.0, MatchMethod.exact)
            return MatchResult(
                service_id=sid,
                score=1.0,
                method=MatchMethod.exact,
                status=MatchStatus.matched_auto,
                candidates=[cand],
            )

        # 3) exact synonym.
        sid = self.synonyms.get(norm)
        if sid is not None:
            cand = self._candidate(sid, 1.0, MatchMethod.synonym)
            return MatchResult(
                service_id=sid,
                score=1.0,
                method=MatchMethod.synonym,
                status=MatchStatus.matched_auto,
                candidates=[cand],
            )

        # 4) fuzzy (+ optional embedding merge).
        # best per service: service_id -> (score, method)
        best: dict[str, tuple[float, MatchMethod]] = {}

        for row in self.fuzzy_rows:
            score = _fuzzy_score(norm, row.text)
            prev = best.get(row.service_id)
            if prev is None or score > prev[0]:
                best[row.service_id] = (score, MatchMethod.fuzzy)

        # Merge embeddings (max score per service; embedding wins ties on method
        # only when strictly higher).
        if self.embedding_index is not None and self.embedding_index.available():
            for idx, e_score in self.embedding_index.query(raw_name, top_k=top_k * 4):
                if idx < 0 or idx >= len(self._emb_service_ids):
                    continue
                e_sid = self._emb_service_ids[idx]
                prev = best.get(e_sid)
                if prev is None or e_score > prev[0]:
                    best[e_sid] = (e_score, MatchMethod.embedding)

        if not best:
            return MatchResult(
                service_id=None,
                score=None,
                method=MatchMethod.none,
                status=MatchStatus.unmatched,
                candidates=[],
            )

        ranked = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)
        candidates = [
            self._candidate(sid, sc, method) for sid, (sc, method) in ranked[:top_k]
        ]

        top = candidates[0]
        status = self._status_for(top.score)
        # service_id is the proposed match for matched_auto / needs_review and
        # None for unmatched; candidates are always returned so operators see
        # suggestions even when nothing crosses the review threshold.
        chosen_id = None if status is MatchStatus.unmatched else top.service_id

        return MatchResult(
            service_id=chosen_id,
            score=top.score,
            method=top.method,
            status=status,
            candidates=candidates,
        )


def build_matcher(db: Session, settings=None) -> Matcher:
    """Construct a :class:`Matcher` from the active catalog in ``db``.

    Thresholds and the embeddings flag come from ``settings`` (falls back to the
    app-wide ``settings`` singleton when not provided).
    """
    if settings is None:
        from ..config import settings as _settings

        settings = _settings

    services = load_services(db)

    emb_index: EmbeddingIndex | None = None
    if getattr(settings, "use_embeddings", False):
        emb_index = EmbeddingIndex(
            model_name=getattr(
                settings, "embedding_model", "paraphrase-multilingual-MiniLM-L12-v2"
            ),
            enabled=True,
        )

    return Matcher(
        services=services,
        auto_threshold=getattr(settings, "match_auto_threshold", 0.85),
        review_threshold=getattr(settings, "match_review_threshold", 0.60),
        embedding_index=emb_index,
    )
