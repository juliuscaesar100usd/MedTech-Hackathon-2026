"""Tests for the MedArchive NORMALIZATION / MATCHING module (spec §4.3).

Everything runs on an isolated in-memory SQLite engine — the real
``backend/medarchive.db`` is never touched. A small but realistic RU/KZ service
catalog (with synonyms) is seeded, the matcher is built, and we assert the
exact / synonym / fuzzy / unmatched behaviours plus the §5 auto-match target.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.enums import MatchMethod, MatchStatus
from app.normalization import (
    build_matcher,
    load_services,
    normalize,
    seed_services,
)

# --------------------------------------------------------------------------- #
# Seed catalog: 8 services, several with RU/KZ synonyms.                       #
# --------------------------------------------------------------------------- #
CATALOG: list[dict] = [
    {
        "service_name": "Общий анализ крови",
        "synonyms": ["ОАК", "анализ крови общий", "ОАК (CBC)"],
        "category": "Лабораторная диагностика",
    },
    {
        "service_name": "УЗИ органов брюшной полости",
        "synonyms": ["УЗИ брюшной полости", "УЗИ ОБП"],
        "category": "Функциональная диагностика",
    },
    {
        "service_name": "Консультация врача-терапевта",
        "synonyms": ["прием терапевта", "консультация терапевта"],
        "category": "Консультации",
    },
    {
        "service_name": "Биохимический анализ крови",
        "synonyms": ["биохимия крови", "БХ крови"],
        "category": "Лабораторная диагностика",
    },
    {
        "service_name": "Электрокардиография",
        "synonyms": ["ЭКГ", "ЭКГ с расшифровкой"],
        "category": "Функциональная диагностика",
    },
    {
        "service_name": "Магнитно-резонансная томография головного мозга",
        "synonyms": ["МРТ головного мозга", "МРТ головы"],
        "category": "Лучевая диагностика",
    },
    {
        "service_name": "Консультация врача-кардиолога",
        "synonyms": ["прием кардиолога", "консультация кардиолога"],
        "category": "Консультации",
    },
    {
        "service_name": "Рентгенография органов грудной клетки",
        "synonyms": ["рентген грудной клетки", "флюорография ОГК", "ренген ОГК"],
        "category": "Лучевая диагностика",
    },
]


@pytest.fixture()
def db() -> Session:
    """Hermetic in-memory SQLite session; never touches medarchive.db."""
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine, future=True)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def matcher(db: Session):
    n = seed_services(db, CATALOG)
    assert n == len(CATALOG)
    assert len(load_services(db)) == len(CATALOG)
    # Embeddings stay off (sentence-transformers not installed): pure lexical.
    return build_matcher(db)


# --------------------------------------------------------------------------- #
# text_utils unit checks.                                                      #
# --------------------------------------------------------------------------- #
def test_normalize_basic():
    assert normalize("  Общий   АНАЛИЗ  крови!! ") == "общий анализ крови"
    assert normalize("ёлка") == "елка"               # ё -> е
    assert normalize("ЭКГ (с расшифровкой)") == "экг с расшифровкой"
    assert normalize("") == ""
    assert normalize(None) == ""


# --------------------------------------------------------------------------- #
# Core matching behaviours.                                                    #
# --------------------------------------------------------------------------- #
def test_exact_match(matcher):
    res = matcher.match("Общий анализ крови")
    assert res.status is MatchStatus.matched_auto
    assert res.method is MatchMethod.exact
    assert res.score == 1.0
    assert res.service_id is not None
    assert res.candidates and res.candidates[0].service_name == "Общий анализ крови"


def test_exact_match_is_case_and_space_insensitive(matcher):
    res = matcher.match("  общий   анализ КРОВИ ")
    assert res.status is MatchStatus.matched_auto
    assert res.method is MatchMethod.exact
    assert res.score == 1.0


def test_synonym_match(matcher):
    res = matcher.match("ОАК")
    assert res.status is MatchStatus.matched_auto
    assert res.method is MatchMethod.synonym
    assert res.score == 1.0
    assert res.candidates[0].service_name == "Общий анализ крови"


def test_synonym_match_kaz_style_abbrev(matcher):
    res = matcher.match("УЗИ ОБП")
    assert res.status is MatchStatus.matched_auto
    assert res.method is MatchMethod.synonym
    assert res.candidates[0].service_name == "УЗИ органов брюшной полости"


def test_fuzzy_typo_resolves_to_correct_service(matcher):
    # Extra qualifier on a known name -> should still map to ОАК service.
    res = matcher.match("Общий анализ крови (расширенный)")
    assert res.status in (MatchStatus.matched_auto, MatchStatus.needs_review)
    assert res.service_id is not None
    assert res.candidates[0].service_name == "Общий анализ крови"


def test_fuzzy_partial_consultation(matcher):
    res = matcher.match("Консультация терапевта первичная")
    assert res.status in (MatchStatus.matched_auto, MatchStatus.needs_review)
    assert res.candidates[0].service_name == "Консультация врача-терапевта"


def test_fuzzy_typo_real_misspelling(matcher):
    # "ренген" is a common misspelling of "рентген".
    res = matcher.match("ренген органов грудной клетки")
    assert res.status in (MatchStatus.matched_auto, MatchStatus.needs_review)
    assert res.candidates[0].service_name == "Рентгенография органов грудной клетки"


def test_nonsense_is_unmatched(matcher):
    res = matcher.match("ремонт автомобиля")
    assert res.status is MatchStatus.unmatched
    assert res.service_id is None


def test_empty_and_short_unmatched(matcher):
    for raw in ["", "   ", "!", "—"]:
        res = matcher.match(raw)
        assert res.status is MatchStatus.unmatched
        assert res.method is MatchMethod.none
        assert res.candidates == []


def test_unmatched_below_review_still_returns_suggestions(matcher):
    # Loosely related text: below review threshold -> unmatched, but the weak
    # candidates are still surfaced for the manual queue (service_id stays None).
    res = matcher.match("ремонт автомобиля")
    assert res.status is MatchStatus.unmatched
    assert res.service_id is None
    # Below-threshold candidates are still surfaced for the manual queue; they
    # must be ranked best-first and all sit below the review threshold.
    assert res.candidates, "expected weak suggestions even when unmatched"
    scores = [c.score for c in res.candidates]
    assert scores == sorted(scores, reverse=True)
    assert all(c.score < matcher.review_threshold for c in res.candidates)


def test_candidates_ranked_best_first(matcher):
    res = matcher.match("анализ крови биохимический")
    assert len(res.candidates) >= 2
    scores = [c.score for c in res.candidates]
    assert scores == sorted(scores, reverse=True)
    # Candidates are deduped per service.
    ids = [c.service_id for c in res.candidates]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- #
# §5 quality target: auto-match rate over realistic raw names.                #
# --------------------------------------------------------------------------- #
REALISTIC_RAW: list[tuple[str, str]] = [
    ("Общий анализ крови", "Общий анализ крови"),
    ("ОАК", "Общий анализ крови"),
    ("анализ крови общий", "Общий анализ крови"),
    ("УЗИ брюшной полости", "УЗИ органов брюшной полости"),
    ("прием терапевта", "Консультация врача-терапевта"),
    ("консультация терапевта", "Консультация врача-терапевта"),
    ("ЭКГ", "Электрокардиография"),
    ("ЭКГ с расшифровкой", "Электрокардиография"),
    ("МРТ головного мозга", "Магнитно-резонансная томография головного мозга"),
    ("биохимия крови", "Биохимический анализ крови"),
]


def test_auto_match_rate_meets_target(matcher):
    auto = 0
    correct = 0
    for raw, expected in REALISTIC_RAW:
        res = matcher.match(raw)
        if res.status is MatchStatus.matched_auto:
            auto += 1
            if res.candidates and res.candidates[0].service_name == expected:
                correct += 1
    rate = auto / len(REALISTIC_RAW)
    # §5 target: >= 0.70 auto-match rate.
    assert rate >= 0.70, f"auto-match rate too low: {rate:.2f}"
    # Auto matches that fire should also be correct.
    assert correct == auto, "an auto-match pointed at the wrong service"
