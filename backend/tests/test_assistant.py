"""Tests for the AI assistant (chatbot) feature.

Two layers:
  * unit tests for the deterministic rule-based preference parser, and
  * end-to-end tests for ``/assistant/chat`` against a seeded temp DB.

The LLM tier is force-disabled in the endpoint tests (via monkeypatch) so the
suite is deterministic and never makes a network call — even if the developer
happens to have ``ANTHROPIC_API_KEY`` exported.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.assistant.preferences import parse_preferences
from app.database import Base, get_db
from app.enums import MatchMethod, MatchStatus
from app.main import app
from app.models import Partner, PriceDocument, PriceItem, Service


# --------------------------------------------------------------------------- #
# Rule-based parser unit tests                                                 #
# --------------------------------------------------------------------------- #
def test_parse_budget_city_resident():
    p = parse_preferences("Нужен анализ крови в Алматы дешевле 5000 тенге для нерезидента")
    assert p.intent == "find_service"
    assert p.raw_query == "анализ крови"        # currency/filler stripped
    assert p.city == "Алматы"
    assert p.max_price_kzt == Decimal("5000")
    assert p.resident == "nonresident"
    assert p.sort == "cheapest"                  # a budget implies cheapest
    assert p.language == "ru"


def test_parse_price_range():
    p = parse_preferences("покажи топ 3 узи от 2000 до 8000")
    assert p.min_price_kzt == Decimal("2000")
    assert p.max_price_kzt == Decimal("8000")
    assert p.limit == 3
    assert p.raw_query == "узи"


def test_parse_ceiling_not_double_counted():
    # "не дороже" must set ONLY the ceiling, not also a floor via "дороже".
    p = parse_preferences("консультация терапевта не дороже 8000")
    assert p.max_price_kzt == Decimal("8000")
    assert p.min_price_kzt is None


def test_parse_thousands_and_currency_conversion():
    p = parse_preferences("МРТ под 50к")
    assert p.max_price_kzt == Decimal("50000")
    p_usd = parse_preferences("blood test under 100 usd")
    assert p_usd.max_price_kzt == Decimal("50000")   # 100 USD * 500


def test_parse_city_inflection_and_partner_intent():
    p = parse_preferences("клиники в Шымкенте")
    assert p.city == "Шымкент"
    assert p.intent == "find_partner"


def test_parse_english_and_sort():
    p = parse_preferences("cheapest MRI brain in Astana")
    assert p.language == "en"
    assert p.city == "Астана"
    assert p.sort == "cheapest"
    assert "mri" in p.raw_query


def test_parse_greeting_is_unknown():
    assert parse_preferences("привет").intent == "unknown"
    assert parse_preferences("").intent == "unknown"


# --- regression tests for adversarial-review findings --- #
def test_parse_negated_cheaper_is_a_floor():
    # "не дешевле 5000" = "not cheaper than 5000" = a FLOOR, not a ceiling.
    p = parse_preferences("анализ не дешевле 5000")
    assert p.min_price_kzt == Decimal("5000")
    assert p.max_price_kzt is None
    # English mirror.
    pe = parse_preferences("blood test not cheaper than 5000")
    assert pe.min_price_kzt == Decimal("5000")
    assert pe.max_price_kzt is None


def test_parse_negation_particle_not_confused_with_word_tail():
    # "астанЕ" ends in "не" but must NOT defeat the "дешевле" ceiling.
    p = parse_preferences("узи в астане дешевле 8000")
    assert p.city == "Астана"
    assert p.max_price_kzt == Decimal("8000")
    assert p.min_price_kzt is None
    assert "узи" in p.raw_query


def test_parse_city_stem_does_not_match_adjective():
    # "семейный врач" (family doctor) must NOT be read as the city "Семей".
    p = parse_preferences("семейный врач до 5000")
    assert p.city is None
    assert "врач" in p.raw_query
    assert p.max_price_kzt == Decimal("5000")


def test_parse_bare_preposition_not_matched_in_word_tail():
    # "живот" ends in "от" but must NOT trigger a price floor.
    p = parse_preferences("узи живот 3000")
    assert p.min_price_kzt is None
    assert p.max_price_kzt is None
    assert "живот" in p.raw_query


def test_parse_huge_number_does_not_crash():
    # A pathological number must not raise (would otherwise 500 the endpoint).
    p = parse_preferences("blood test under " + ("9" * 40) + " tenge")
    assert p.max_price_kzt is None  # out-of-range magnitude is dropped
    assert "blood" in p.raw_query


# --------------------------------------------------------------------------- #
# Fixtures for endpoint tests                                                  #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_assistant.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    engine.dispose()


@pytest.fixture()
def db(session_factory):
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client(session_factory, monkeypatch):
    # Force the deterministic rule-based parser regardless of environment.
    monkeypatch.setattr("app.assistant.llm.parse_preferences_llm", lambda *a, **k: None)

    def _override():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seed(db):
    s_blood = Service(service_name="Общий анализ крови", synonyms=["ОАК", "CBC"], category="Лаборатория")
    s_urine = Service(service_name="Общий анализ мочи", synonyms=["ОАМ"], category="Лаборатория")
    s_mri = Service(service_name="МРТ головного мозга", synonyms=["MRI brain"], category="Диагностика")
    db.add_all([s_blood, s_urine, s_mri])
    db.flush()

    p_alfa = Partner(name="Клиника Альфа", city="Алматы")
    p_beta = Partner(name="Медцентр Бета", city="Астана")
    db.add_all([p_alfa, p_beta])
    db.flush()

    doc_a = PriceDocument(partner_id=p_alfa.partner_id, file_name="alfa.xlsx")
    doc_b = PriceDocument(partner_id=p_beta.partner_id, file_name="beta.xlsx")
    db.add_all([doc_a, doc_b])
    db.flush()

    def item(doc, partner, svc, res, non=None, status=MatchStatus.matched_auto):
        return PriceItem(
            doc_id=doc.doc_id,
            partner_id=partner.partner_id,
            service_id=svc.service_id,
            service_name_raw=svc.service_name,
            price_resident_kzt=Decimal(str(res)),
            price_nonresident_kzt=Decimal(str(non)) if non is not None else None,
            match_status=status,
            match_method=MatchMethod.exact,
            match_confidence=1.0,
            is_active=True,
        )

    db.add_all([
        # Blood test: Almaty 3000/4500, Astana 2500 (cheapest, no non-resident).
        item(doc_a, p_alfa, s_blood, 3000, 4500),
        item(doc_b, p_beta, s_blood, 2500),
        # Urine: Almaty 2000.
        item(doc_a, p_alfa, s_urine, 2000),
        # MRI: Astana 25000.
        item(doc_b, p_beta, s_mri, 25000, 30000),
    ])
    db.commit()
    return {
        "blood": s_blood.service_id,
        "alfa": p_alfa.partner_id,
        "beta": p_beta.partner_id,
    }


# --------------------------------------------------------------------------- #
# Endpoint tests                                                               #
# --------------------------------------------------------------------------- #
def test_status(client):
    r = client.get("/api/assistant/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert isinstance(body["llm_available"], bool)


def test_chat_budget_filters_offers(client, seed):
    r = client.post("/api/assistant/chat", json={"message": "анализ крови дешевле 2700"})
    assert r.status_code == 200
    body = r.json()
    assert body["used_llm"] is False
    assert body["parser"] == "rule_based"
    assert body["preferences"]["max_price_kzt"] in ("2700", 2700, "2700.00")
    blood = next(s for s in body["services"] if s["service_name"] == "Общий анализ крови")
    # Only the 2500 (Astana) offer clears the 2700 budget.
    assert blood["partner_count"] == 1
    assert float(blood["best_price_kzt"]) == 2500.0
    assert blood["offers"][0]["partner_name"] == "Медцентр Бета"


def test_chat_cheapest_sort_orders_offers(client, seed):
    r = client.post("/api/assistant/chat", json={"message": "самый дешёвый общий анализ крови"})
    body = r.json()
    blood = next(s for s in body["services"] if s["service_name"] == "Общий анализ крови")
    prices = [o["price_shown_kzt"] for o in blood["offers"]]
    assert [float(p) for p in prices] == sorted(float(p) for p in prices)
    assert float(blood["offers"][0]["price_shown_kzt"]) == 2500.0


def test_chat_city_filter(client, seed):
    r = client.post("/api/assistant/chat", json={"message": "анализ крови в Алматы"})
    body = r.json()
    assert body["preferences"]["city"] == "Алматы"
    blood = next(s for s in body["services"] if s["service_name"] == "Общий анализ крови")
    # Only the Almaty offer survives the city filter.
    assert {o["partner_name"] for o in blood["offers"]} == {"Клиника Альфа"}


def test_chat_nonresident_price_shown(client, seed):
    r = client.post("/api/assistant/chat", json={"message": "общий анализ крови в Алматы для нерезидента"})
    body = r.json()
    blood = next(s for s in body["services"] if s["service_name"] == "Общий анализ крови")
    offer = blood["offers"][0]
    # Almaty resident=3000, non-resident=4500 -> shown is the non-resident price.
    assert float(offer["price_shown_kzt"]) == 4500.0


def test_chat_find_partner(client, seed):
    r = client.post("/api/assistant/chat", json={"message": "клиники в Астане"})
    body = r.json()
    assert body["preferences"]["intent"] == "find_partner"
    assert {p["name"] for p in body["partners"]} == {"Медцентр Бета"}


def test_chat_no_results_message(client, seed):
    r = client.post("/api/assistant/chat", json={"message": "анализ крови дешевле 100"})
    body = r.json()
    # Nothing clears a 100 KZT budget.
    assert body["services"] == []
    assert body["reply"]


def test_chat_unknown_prompt(client, seed):
    r = client.post("/api/assistant/chat", json={"message": "привет"})
    body = r.json()
    assert body["preferences"]["intent"] == "unknown"
    assert body["suggestions"]


def test_chat_llm_tier_used_when_available(client, seed, monkeypatch):
    """When the LLM parser returns preferences, the engine reports parser=llm."""
    from app.assistant.schemas import Preferences

    def fake_llm(message, history, settings, *, max_results=5):
        return Preferences(intent="find_service", raw_query="анализ крови",
                           services=["анализ", "крови"], sort="cheapest", limit=5)

    monkeypatch.setattr("app.assistant.llm.parse_preferences_llm", fake_llm)
    r = client.post("/api/assistant/chat", json={"message": "что-нибудь про кровь"})
    body = r.json()
    assert body["used_llm"] is True
    assert body["parser"] == "llm"
    assert any(s["service_name"] == "Общий анализ крови" for s in body["services"])


def test_chat_huge_number_returns_200_not_500(client, seed):
    # A crafted huge number must not produce an unhandled 500 (DoS guard).
    r = client.post(
        "/api/assistant/chat",
        json={"message": "анализ крови дешевле " + ("9" * 40) + " тенге"},
    )
    assert r.status_code == 200
    assert r.json()["preferences"]["max_price_kzt"] is None


def test_chat_rejects_oversized_message(client):
    r = client.post("/api/assistant/chat", json={"message": "x" * 4001})
    assert r.status_code == 422  # schema max_length boundary


def test_chat_rejects_oversized_history(client):
    r = client.post(
        "/api/assistant/chat",
        json={
            "message": "узи",
            "history": [{"role": "user", "content": "y"} for _ in range(31)],
        },
    )
    assert r.status_code == 422  # history max_length=30
