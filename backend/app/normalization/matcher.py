"""Service-name matcher (spec §4.3) — LANE 2.

Matcher chain per raw name (in strict order):
  1. empty / too-short        -> unmatched (method none, no candidates).
  2. exact normalized name    -> 1.0, exact,   matched_auto.
  3. exact normalized synonym -> 1.0, synonym, matched_auto.
  4. fuzzy (rapidfuzz) over the candidate texts.
  5. embedding (sentence-transformers e5) over the candidate texts; cosine in
     [0,1]. The embedding score overrides the fuzzy score for a service only
     when it is strictly higher, so the winning candidate's ``method`` reflects
     the stage that actually produced it. cosine >= auto_threshold (0.85) =>
     matched_auto with match_method=embedding.

SPECIALTY PRIOR (steps 4-5): when the row carries a ``section`` and that section
fuzzy-maps to a catalog specialty, the candidate set is restricted to the
services that belong to that specialty (via ServiceSpecialty) BEFORE any
fuzzy/embedding scoring. If no specialty can be inferred, all services are
considered (the full 511).

INPUT FILTER: ``Matcher.match_item`` drops section/category-header rows
(null price AND no service code AND a header-looking name) by returning ``None``
so they never pollute matching or the unmatched queue.

All similarities live in [0, 1]. Candidates are deduped per service (best score
kept) and returned best-first.
"""
from __future__ import annotations

import re
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

# Lane-2 standardizes the semantic stage on multilingual-e5-base. An explicit
# EMBEDDING_MODEL override is honored; the old library default is ignored.
DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-base"
_STALE_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# --------------------------------------------------------------------------- #
# Section/category-header heuristic (matcher INPUT filter, requirement 3).      #
# --------------------------------------------------------------------------- #
# Name parts that begin like a heading rather than a priced service line.
_SECTION_HEADER_RE = re.compile(
    r"^(раздел|подраздел|категория|группа услуг|перечень|прейскурант|"
    r"наименование услуг|стоимость услуг|прайс[ -]?лист|тарифы|отделение|"
    r"кабинет|блок|глава)\b",
    re.I,
)
# A bare enumerator heading: "1.", "2)", "IV.", "Раздел 3" (handled above).
_ENUM_HEADER_RE = re.compile(r"^(?:[IVXLCDM]+|\d+)[.)]?(?:\s|$)", re.I)
# Near-exact threshold for "this text *is* a specialty name" header detection.
_SPECIALTY_HEADER_SIM = 0.90


def _fuzzy_score(query_norm: str, target_norm: str) -> float:
    """Robust similarity in [0,1] combining token_set_ratio and WRatio."""
    a = fuzz.token_set_ratio(query_norm, target_norm)
    b = fuzz.WRatio(query_norm, target_norm)
    return max(a, b) / 100.0


def is_section_header(name: str | None, *, has_price: bool, has_code: bool) -> bool:
    """True when a row looks like a section/category header, not a service line.

    Conservative by design: a header must have NO price AND NO source code
    (those two alone strongly imply "not a service line"); on top of that the
    name itself must look like a heading — a known section cue, a trailing
    ``:``, a short ALL-CAPS label, or a bare enumerator.
    """
    if has_price or has_code:
        return False
    raw = (name or "").strip()
    norm = normalize(raw)
    if not norm:
        # Empty/punctuation-only rows are handled by the matcher's min-length
        # gate; they are not meaningful "headers" to surface separately.
        return False
    if _SECTION_HEADER_RE.match(norm):
        return True
    if raw.rstrip().endswith(":"):
        return True
    toks = norm.split(" ")
    letters = [ch for ch in raw if ch.isalpha()]
    # Short ALL-CAPS heading, e.g. "КАРДИОЛОГИЯ", "ЛАБОРАТОРНАЯ ДИАГНОСТИКА".
    # Require >=2 tokens or a long single token so abbreviations like "ОАК"/
    # "ЭКГ" (real services) are not mistaken for headers.
    if letters and all(ch.isupper() for ch in letters) and len(toks) <= 4:
        if len(toks) >= 2 or len(letters) >= 6:
            return True
    if _ENUM_HEADER_RE.match(raw) and len(toks) <= 2:
        return True
    return False


def _item_has_price(item) -> bool:
    """True if any price field on a PriceItem-like object is set."""
    for attr in ("price_resident_kzt", "price_nonresident_kzt", "price_original"):
        val = getattr(item, attr, None)
        if val is not None:
            try:
                if float(val) != 0.0 or attr == "price_original":
                    return True
            except (TypeError, ValueError):
                return True
    return False


def _item_has_code(item) -> bool:
    for attr in ("service_code_source", "service_code", "code"):
        if getattr(item, attr, None):
            return True
    return False


@dataclass
class _Row:
    """One catalog text entry feeding the fuzzy index."""

    text: str          # normalized text (name or synonym)
    service_id: str
    is_synonym: bool


class Matcher:
    """Holds the catalog + precomputed indices and answers ``match`` queries."""

    def __init__(
        self,
        services: list,
        auto_threshold: float = 0.85,
        review_threshold: float = 0.60,
        embedding_index: EmbeddingIndex | None = None,
        service_specialties: dict | None = None,
        specialty_threshold: float = 0.62,
    ) -> None:
        self.auto_threshold = auto_threshold
        self.review_threshold = review_threshold
        self.specialty_threshold = specialty_threshold
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

        # ---- specialty prior structures ---------------------------------- #
        # service_id -> ordered unique specialties.
        self.service_specialties: dict[str, list[str]] = {}
        # specialty (original) -> set of service_ids.
        self._specialty_to_sids: dict[str, set[str]] = {}
        # (normalized specialty, original specialty) — unique, for section fuzzy.
        self._specialty_norms: list[tuple[str, str]] = []
        # memoize section -> inferred specialty (sections repeat heavily).
        self._section_cache: dict[str, str | None] = {}

        for svc in services:
            sid = svc.service_id
            self._meta[sid] = {
                "service_name": svc.service_name,
                # ``category`` is optional under the new schema contract.
                "category": getattr(svc, "category", None),
            }
            name_norm = normalize(svc.service_name)
            if name_norm:
                # First writer wins for exact names (catalog is deduped already).
                self.exact.setdefault(name_norm, sid)
                self.fuzzy_rows.append(_Row(name_norm, sid, is_synonym=False))
                self._emb_texts.append(svc.service_name)
                self._emb_service_ids.append(sid)
            for syn in getattr(svc, "synonyms", None) or []:
                syn_norm = normalize(syn)
                if not syn_norm:
                    continue
                self.synonyms.setdefault(syn_norm, sid)
                self.fuzzy_rows.append(_Row(syn_norm, sid, is_synonym=True))
                self._emb_texts.append(str(syn))
                self._emb_service_ids.append(sid)

        self._emb_count = len(self._emb_texts)
        self._build_specialty_index(service_specialties)

        if self.embedding_index is not None and self.embedding_index.enabled:
            # Build may fail (lib missing / load error); available() guards use.
            self.embedding_index.build(self._emb_texts)

    # ------------------------------------------------------------------ #
    def _build_specialty_index(self, service_specialties: dict | None) -> None:
        if not service_specialties:
            return
        seen_specs: set[str] = set()
        for sid, specs in service_specialties.items():
            sid = str(sid)
            for spec in specs or []:
                spec = (str(spec) or "").strip()
                if not spec:
                    continue
                bucket = self.service_specialties.setdefault(sid, [])
                if spec not in bucket:
                    bucket.append(spec)
                self._specialty_to_sids.setdefault(spec, set()).add(sid)
                if spec not in seen_specs:
                    sn = normalize(spec)
                    if sn:
                        seen_specs.add(spec)
                        self._specialty_norms.append((sn, spec))

    def _infer_specialty(self, section: str | None) -> str | None:
        """Fuzzy-map a section header to the closest catalog specialty."""
        if not section or not self._specialty_norms:
            return None
        sec = normalize(section)
        if not sec:
            return None
        if sec in self._section_cache:
            return self._section_cache[sec]
        best_spec: str | None = None
        best = 0.0
        for sn, orig in self._specialty_norms:
            s = _fuzzy_score(sec, sn)
            if s > best:
                best = s
                best_spec = orig
        result = best_spec if best >= self.specialty_threshold else None
        self._section_cache[sec] = result
        return result

    def _looks_like_specialty(self, name: str | None) -> bool:
        """True if ``name`` is (near-exactly) a catalog specialty label."""
        if not name or not self._specialty_norms:
            return False
        nm = normalize(name)
        if not nm:
            return False
        for sn, _orig in self._specialty_norms:
            if _fuzzy_score(nm, sn) >= _SPECIALTY_HEADER_SIM:
                return True
        return False

    def _allowed_sids(self, section: str | None) -> tuple[set[str] | None, str | None]:
        """Resolve the candidate restriction for a section, if any.

        Returns ``(allowed_service_ids_or_None, inferred_specialty_or_None)``.
        ``None`` for the set means "no restriction — consider all services".
        """
        spec = self._infer_specialty(section)
        if not spec:
            return None, None
        sids = self._specialty_to_sids.get(spec)
        if sids:
            return sids, spec
        return None, spec

    def _resolve_prior(
        self, section: str | None, section_path: list[str] | None
    ) -> tuple[set[str] | None, str | None]:
        """Pick the candidate restriction using the MOST SPECIFIC section first.

        Walks the section nesting innermost→outer (then the bare ``section``),
        returning the first level that maps to a specialty with a non-empty
        candidate set. Strictly additive: with no ``section_path`` this reduces
        to the previous single-``section`` behaviour.
        """
        # Innermost first, then outward, then the bare section (deduped).
        ordered: list[str] = []
        for level in reversed(section_path or []):
            level = (level or "").strip()
            if level and level not in ordered:
                ordered.append(level)
        if section and section not in ordered:
            ordered.append(section)

        last_spec: str | None = None
        for sec in ordered:
            allowed, spec = self._allowed_sids(sec)
            if spec:
                last_spec = spec
            if allowed is not None:
                return allowed, spec
        return None, last_spec

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

    def _unmatched(self) -> MatchResult:
        return MatchResult(
            service_id=None,
            score=None,
            method=MatchMethod.none,
            status=MatchStatus.unmatched,
            candidates=[],
        )

    # ------------------------------------------------------------------ #
    def match(
        self,
        raw_name: str,
        section: str | None = None,
        top_k: int = 5,
        section_path: list[str] | None = None,
    ) -> MatchResult:
        norm = normalize(raw_name)

        # 1) empty / too short.
        if len(norm) < _MIN_LEN:
            return self._unmatched()

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

        # --- specialty prior: narrow candidates BEFORE fuzzy/embedding ---- #
        # Use the MOST SPECIFIC section element first (innermost→outer) when a
        # full section_path is available; falls back to the bare section.
        allowed, _spec = self._resolve_prior(section, section_path)

        # 4) fuzzy over the (restricted) candidate texts.
        # best per service: service_id -> (score, method)
        best: dict[str, tuple[float, MatchMethod]] = {}
        for row in self.fuzzy_rows:
            if allowed is not None and row.service_id not in allowed:
                continue
            score = _fuzzy_score(norm, row.text)
            prev = best.get(row.service_id)
            if prev is None or score > prev[0]:
                best[row.service_id] = (score, MatchMethod.fuzzy)

        # 5) embeddings (max score per service; embedding only overrides the
        #    method when it is *strictly* higher than the fuzzy score).
        if self.embedding_index is not None and self.embedding_index.available():
            # When restricted to a specialty, ask for the whole ranking so the
            # best in-specialty row is never crowded out by out-of-specialty
            # neighbours; otherwise a generous slice is enough.
            k = self._emb_count if allowed is not None else top_k * 4
            for idx, e_score in self.embedding_index.query(raw_name, top_k=k):
                if idx < 0 or idx >= len(self._emb_service_ids):
                    continue
                e_sid = self._emb_service_ids[idx]
                if allowed is not None and e_sid not in allowed:
                    continue
                prev = best.get(e_sid)
                if prev is None or e_score > prev[0]:
                    best[e_sid] = (e_score, MatchMethod.embedding)

        if not best:
            return self._unmatched()

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

    # ------------------------------------------------------------------ #
    def match_item(self, item, top_k: int = 5) -> MatchResult | None:
        """Match a PriceItem-like row, skipping section/category headers.

        Returns ``None`` for header rows (null price AND no code AND a heading-
        looking name, or a no-price/no-code row whose text *is* a specialty
        label) so the caller drops them entirely — they never reach the matcher
        or the unmatched queue. Otherwise returns a normal :class:`MatchResult`,
        using ``item.section`` as the specialty prior.
        """
        name = getattr(item, "service_name_raw", None)
        if name is None:
            name = getattr(item, "name", "") or ""
        has_price = _item_has_price(item)
        has_code = _item_has_code(item)

        if is_section_header(name, has_price=has_price, has_code=has_code):
            return None
        if not has_price and not has_code and self._looks_like_specialty(name):
            return None

        section = getattr(item, "section", None)
        section_path = getattr(item, "section_path", None)
        return self.match(name, section=section, top_k=top_k, section_path=section_path)


def _load_service_specialties(db: Session) -> dict[str, list[str]]:
    """Build ``service_id -> [specialty]`` from ServiceSpecialty, if present.

    Degrades to ``{}`` when the table/model is absent (e.g. before lane 1 lands
    the schema, or on the legacy single-category schema) so the matcher simply
    falls back to considering all services.
    """
    try:
        from ..models import ServiceSpecialty  # type: ignore
    except Exception:
        return {}
    out: dict[str, list[str]] = {}
    try:
        rows = db.query(ServiceSpecialty).all()
    except Exception:
        return {}
    for row in rows:
        sid = getattr(row, "service_id", None)
        spec = getattr(row, "specialty", None)
        if sid is None or not spec:
            continue
        out.setdefault(str(sid), []).append(str(spec))
    return out


def build_matcher(db: Session, settings=None) -> Matcher:
    """Construct a :class:`Matcher` from the active catalog in ``db``.

    Thresholds and the embeddings flag come from ``settings`` (falls back to the
    app-wide ``settings`` singleton when not provided). The semantic stage uses
    multilingual-e5-base with the required ``query:`` / ``passage:`` prompts.
    """
    if settings is None:
        from ..config import settings as _settings

        settings = _settings

    services = load_services(db)
    service_specialties = _load_service_specialties(db)

    emb_index: EmbeddingIndex | None = None
    if getattr(settings, "use_embeddings", False):
        configured = getattr(settings, "embedding_model", None)
        model_name = (
            configured
            if configured and configured != _STALE_DEFAULT_MODEL
            else DEFAULT_EMBEDDING_MODEL
        )
        use_e5 = "e5" in model_name.lower()
        # Keep the cached matrix out of the source tree: prefer the app's
        # storage dir (already gitignored) when available.
        data_dir = getattr(settings, "data_dir", None)
        cache_dir = (data_dir / "emb_cache") if data_dir else None
        emb_index = EmbeddingIndex(
            model_name=model_name,
            enabled=True,
            query_prefix="query: " if use_e5 else "",
            passage_prefix="passage: " if use_e5 else "",
            cache_dir=cache_dir,
            model_cache_dir=getattr(settings, "embeddings_model_cache", None),
            offline=getattr(settings, "embeddings_offline", False),
        )

    return Matcher(
        services=services,
        auto_threshold=getattr(settings, "match_auto_threshold", 0.85),
        review_threshold=getattr(settings, "match_review_threshold", 0.60),
        embedding_index=emb_index,
        service_specialties=service_specialties,
    )
