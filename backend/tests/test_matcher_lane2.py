"""LANE 2 unit test for the normalization matcher.

Self-contained: a handful of fake Service + ServiceSpecialty rows and ~6 raw
names, on an isolated ``lane2.db`` SQLite file. It never touches the real
archive or the real catalog. It confirms the whole chain fires:

    exact -> synonym -> fuzzy -> embedding   (+ specialty prior, + header skip)

The embedding stage is exercised with a deterministic stub / fake encoder so the
test stays fast and offline (no torch, no model download).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.enums import MatchMethod, MatchStatus
from app.normalization.embeddings import EmbeddingIndex
from app.normalization.matcher import (
    Matcher,
    build_matcher,
    is_section_header,
)
from app.normalization.text_utils import normalize

LANE2_DB = Path(__file__).resolve().parent.parent / "lane2.db"


# --------------------------------------------------------------------------- #
# Fake catalog rows (duck-typed Service) + ServiceSpecialty mapping.           #
# --------------------------------------------------------------------------- #
@dataclass
class FakeService:
    service_id: str
    service_name: str
    synonyms: list = field(default_factory=list)
    category: str | None = None


@dataclass
class FakeItem:
    """Duck-typed PriceItem for match_item / header-skip checks."""

    service_name_raw: str
    price_resident_kzt: float | None = None
    price_nonresident_kzt: float | None = None
    price_original: float | None = None
    service_code_source: str | None = None
    section: str | None = None


CATALOG: list[FakeService] = [
    FakeService("s-ekg", "Электрокардиография", ["ЭКГ", "ЭКГ с расшифровкой"]),
    FakeService("s-echo", "Эхокардиография", ["ЭхоКГ", "УЗИ сердца"]),
    FakeService("s-cardio-cons", "Консультация врача-кардиолога", ["прием кардиолога"]),
    FakeService("s-neuro-cons", "Консультация врача-невролога", ["прием невролога"]),
    FakeService("s-eeg", "Электроэнцефалография", ["ЭЭГ"]),
    FakeService("s-oak", "Общий анализ крови", ["ОАК", "анализ крови общий"]),
]

# The 1281-style service x specialty rows, in miniature.
SERVICE_SPECIALTIES: dict[str, list[str]] = {
    "s-ekg": ["Кардиология"],
    "s-echo": ["Кардиология"],
    "s-cardio-cons": ["Кардиология"],
    "s-neuro-cons": ["Неврология"],
    "s-eeg": ["Неврология"],
    "s-oak": ["Лабораторная диагностика"],
}


# --------------------------------------------------------------------------- #
# Embedding test doubles (no torch).                                           #
# --------------------------------------------------------------------------- #
class StubEmbeddingIndex:
    """Returns hand-picked cosine hits for specific raw names.

    Implements the slice of EmbeddingIndex that Matcher uses: ``enabled``,
    ``build``, ``available``, ``query``.
    """

    enabled = True

    def __init__(self, hits: list[tuple[str, str, float]]) -> None:
        # hits: (raw_text, target_catalog_text, cosine_score)
        self._hits = hits
        self._texts: list[str] = []
        self._built = False

    def build(self, texts: list[str]) -> bool:
        self._texts = list(texts)
        self._built = True
        return True

    def available(self) -> bool:
        return self._built

    def query(self, text: str, top_k: int = 5) -> list[tuple[int, float]]:
        nt = normalize(text)
        out: list[tuple[int, float]] = []
        for raw, target, score in self._hits:
            if normalize(raw) != nt:
                continue
            tnorm = normalize(target)
            for i, t in enumerate(self._texts):
                if normalize(t) == tnorm:
                    out.append((i, score))
                    break
        out.sort(key=lambda x: -x[1])
        return out[:top_k]


def _fake_vec(text: str, dim: int = 256):
    """Deterministic bag-of-tokens embedding (shared by the fake encoder)."""
    import numpy as np

    vec = np.zeros(dim, dtype="float32")
    for tok in normalize(text).split(" "):
        if not tok:
            continue
        h = int(hashlib.sha1(tok.encode("utf-8")).hexdigest(), 16) % dim
        vec[h] += 1.0
    return vec


class FakeSentenceModel:
    """Stands in for SentenceTransformer; records what it was asked to encode."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, inputs, convert_to_numpy=True, show_progress_bar=False):
        import numpy as np

        self.calls.append(list(inputs))
        return np.array([_fake_vec(s) for s in inputs], dtype="float32")


# --------------------------------------------------------------------------- #
# Fixtures.                                                                     #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def stub_embeddings() -> StubEmbeddingIndex:
    # An English raw name: lexically it shares NOTHING with the Cyrillic catalog
    # (fuzzy ~0), but multilingual-e5 maps it to the echocardiography service.
    # Only the embedding stage can catch it.
    return StubEmbeddingIndex(
        hits=[("cardiac ultrasound", "Эхокардиография", 0.95)]
    )


@pytest.fixture()
def matcher(stub_embeddings: StubEmbeddingIndex) -> Matcher:
    return Matcher(
        services=CATALOG,
        embedding_index=stub_embeddings,
        service_specialties=SERVICE_SPECIALTIES,
    )


@pytest.fixture()
def lexical_matcher() -> Matcher:
    """Same catalog, no embedding stage (for before/after contrast)."""
    return Matcher(services=CATALOG, service_specialties=SERVICE_SPECIALTIES)


# --------------------------------------------------------------------------- #
# 1. exact / synonym fire.                                                      #
# --------------------------------------------------------------------------- #
def test_exact_fires(matcher: Matcher):
    res = matcher.match("Общий анализ крови")
    assert res.status is MatchStatus.matched_auto
    assert res.method is MatchMethod.exact
    assert res.score == 1.0
    assert res.service_id == "s-oak"


def test_synonym_fires(matcher: Matcher):
    res = matcher.match("ОАК")
    assert res.status is MatchStatus.matched_auto
    assert res.method is MatchMethod.synonym
    assert res.service_id == "s-oak"


# --------------------------------------------------------------------------- #
# 2. fuzzy fires (neither exact nor synonym).                                   #
# --------------------------------------------------------------------------- #
def test_fuzzy_fires(matcher: Matcher):
    res = matcher.match("Электрокардиография с нагрузкой")
    assert res.method is MatchMethod.fuzzy
    assert res.status in (MatchStatus.matched_auto, MatchStatus.needs_review)
    assert res.candidates[0].service_id == "s-ekg"


# --------------------------------------------------------------------------- #
# 3. embedding fires where fuzzy cannot.                                        #
# --------------------------------------------------------------------------- #
def test_embedding_fires(matcher: Matcher, lexical_matcher: Matcher):
    raw = "cardiac ultrasound"
    res = matcher.match(raw)
    assert res.method is MatchMethod.embedding, "embedding stage should win"
    assert res.status is MatchStatus.matched_auto
    assert res.service_id == "s-echo"
    assert res.score >= 0.85

    # Without embeddings the same raw name does NOT auto-match -> proves the
    # embedding stage is what made the difference.
    res2 = lexical_matcher.match(raw)
    assert res2.method is not MatchMethod.embedding
    assert res2.status is not MatchStatus.matched_auto


# --------------------------------------------------------------------------- #
# 4. specialty prior narrows candidates BEFORE scoring.                         #
# --------------------------------------------------------------------------- #
def test_specialty_inference(matcher: Matcher):
    assert matcher._infer_specialty("Неврология") == "Неврология"
    assert matcher._infer_specialty("Кардиология (взрослая)") == "Кардиология"
    # Unrelated section -> nothing inferred -> fall back to all services.
    assert matcher._infer_specialty("Зубная фея") is None


def test_specialty_prior_restricts_candidates(matcher: Matcher):
    NEURO = {"s-neuro-cons", "s-eeg"}

    # No section -> candidates span multiple specialties (no restriction).
    res_all = matcher.match("консультация врача")
    ids_all = {c.service_id for c in res_all.candidates}
    assert "s-cardio-cons" in ids_all and "s-neuro-cons" in ids_all

    # With a neurology section -> candidate set restricted to neurology only.
    res_neuro = matcher.match("консультация врача", section="Неврология")
    ids_neuro = {c.service_id for c in res_neuro.candidates}
    assert ids_neuro <= NEURO, f"leaked out-of-specialty candidates: {ids_neuro}"
    assert "s-cardio-cons" not in ids_neuro
    assert res_neuro.candidates[0].service_id == "s-neuro-cons"


# --------------------------------------------------------------------------- #
# 5. section/category-header rows are skipped at matcher INPUT.                 #
# --------------------------------------------------------------------------- #
def test_is_section_header_heuristic():
    assert is_section_header("РАЗДЕЛ 1. ЛАБОРАТОРНЫЕ ИССЛЕДОВАНИЯ",
                             has_price=False, has_code=False)
    assert is_section_header("Консультации:", has_price=False, has_code=False)
    assert is_section_header("ЛАБОРАТОРНАЯ ДИАГНОСТИКА",
                             has_price=False, has_code=False)
    # A real service with a price is never a header, even if the name is short.
    assert not is_section_header("ОАК", has_price=True, has_code=False)
    # No price but a code present -> a real (coded) line, not a header.
    assert not is_section_header("Кардиология", has_price=False, has_code=True)


def test_match_item_skips_headers(matcher: Matcher):
    headers = [
        FakeItem("Кардиология"),                       # bare specialty label
        FakeItem("РАЗДЕЛ 1. ЛАБОРАТОРНЫЕ ИССЛЕДОВАНИЯ"),
        FakeItem("Консультации:"),
    ]
    for h in headers:
        assert matcher.match_item(h) is None, f"header not skipped: {h.service_name_raw}"

    # A priced row that *looks* like a category name is still matched, not
    # skipped (the null-price gate protects real services).
    priced = FakeItem("Кардиология", price_resident_kzt=5000.0)
    assert matcher.match_item(priced) is not None

    # A normal priced service is matched and carries its section as the prior.
    real = FakeItem(
        "Общий анализ крови",
        price_resident_kzt=1500.0,
        section="Лабораторная диагностика",
    )
    res = matcher.match_item(real)
    assert res is not None
    assert res.service_id == "s-oak"
    assert res.method is MatchMethod.exact


# --------------------------------------------------------------------------- #
# 6. EmbeddingIndex: e5 prefixes + uniquely-named disk cache (fake encoder).    #
# --------------------------------------------------------------------------- #
def test_embedding_index_prefixes_and_cache(tmp_path: Path):
    texts = [s.service_name for s in CATALOG]

    # First build encodes with the model and writes a uniquely-named cache file.
    idx = EmbeddingIndex("intfloat/multilingual-e5-base-FAKE",
                         enabled=True, cache_dir=tmp_path)
    idx._model = FakeSentenceModel()
    assert idx.build(texts) is True
    assert idx.available()
    # Catalog texts were encoded with the "passage: " prefix.
    assert idx._model.calls and all(
        s.startswith("passage: ") for s in idx._model.calls[0]
    )
    assert idx.cache_path is not None and idx.cache_path.exists()
    assert not idx.loaded_from_cache

    # Second index, same model + texts + cache dir -> loads from disk, the
    # (fake) model is NOT invoked for the build.
    idx2 = EmbeddingIndex("intfloat/multilingual-e5-base-FAKE",
                          enabled=True, cache_dir=tmp_path)
    fake2 = FakeSentenceModel()
    idx2._model = fake2
    assert idx2.build(texts) is True
    assert idx2.loaded_from_cache is True
    assert fake2.calls == []  # build served entirely from cache

    # Query encodes the raw name with the "query: " prefix and ranks the right
    # catalog row first.
    hits = idx2.query("эхокардиография", top_k=3)
    assert fake2.calls and fake2.calls[0][0].startswith("query: ")
    assert hits, "expected at least one cosine hit"
    top_idx, top_score = hits[0]
    assert texts[top_idx] == "Эхокардиография"
    assert 0.0 <= top_score <= 1.0


# --------------------------------------------------------------------------- #
# 7. build_matcher path on lane2.db (graceful with no ServiceSpecialty table).  #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def lane2_session() -> Session:
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(LANE2_DB) + suffix)
        if p.exists():
            p.unlink()
    engine = create_engine(f"sqlite:///{LANE2_DB}", future=True)
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine, future=True)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_build_matcher_on_lane2_db(lane2_session: Session):
    from app.normalization.catalog import seed_services

    seed_services(
        lane2_session,
        [{"service_name": "Общий анализ крови", "synonyms": ["ОАК"]}],
    )
    # Embeddings default off; ServiceSpecialty model absent -> empty prior.
    m = build_matcher(lane2_session)
    res = m.match("ОАК")
    assert res.status is MatchStatus.matched_auto
    assert res.method is MatchMethod.synonym


# --------------------------------------------------------------------------- #
# Human-readable summary (visible with `pytest -s`).                            #
# --------------------------------------------------------------------------- #
def test_print_summary(matcher: Matcher):
    cases = [
        ("Общий анализ крови", None),
        ("ОАК", None),
        ("Электрокардиография с нагрузкой", None),
        ("cardiac ultrasound", None),
        ("консультация врача", "Неврология"),
        ("консультация врача", None),
    ]
    print("\n--- LANE 2 matcher fixture output ---")
    print(f"{'raw':<34} {'section':<14} {'method':<10} {'status':<13} top")
    for raw, section in cases:
        r = matcher.match(raw, section=section)
        top = r.candidates[0].service_name if r.candidates else "-"
        sc = f"{r.score:.3f}" if r.score is not None else "  -  "
        print(f"{raw:<34} {str(section):<14} {r.method.value:<10} "
              f"{r.status.value:<13} {sc}  {top}")
    print("Header skips:")
    for name in ["Кардиология", "РАЗДЕЛ 1. ЛАБОРАТОРНЫЕ ИССЛЕДОВАНИЯ", "Консультации:"]:
        skipped = matcher.match_item(FakeItem(name)) is None
        print(f"  {name:<40} skipped={skipped}")
