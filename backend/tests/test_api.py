"""End-to-end API tests using FastAPI's TestClient.

A throwaway temp-file SQLite engine is created per test session and injected via
``app.dependency_overrides[get_db]`` so the tests never touch
``backend/medarchive.db``. Data is seeded directly through the test session.
"""
from __future__ import annotations

import io
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.enums import MatchMethod, MatchStatus
from app.main import app
from app.models import Partner, PriceDocument, PriceItem, Service


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture()
def session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_api.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    yield TestingSessionLocal
    engine.dispose()


@pytest.fixture()
def db(session_factory):
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client(session_factory):
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
    """Seed services, partners and price items; return key ids."""
    s_blood = Service(
        service_name="Общий анализ крови",
        synonyms=["ОАК", "CBC"],
        category="Лаборатория",
    )
    s_urine = Service(
        service_name="Общий анализ мочи",
        synonyms=["ОАМ"],
        category="Лаборатория",
    )
    s_mri = Service(
        service_name="МРТ головного мозга",
        synonyms=["MRI brain"],
        category="Диагностика",
    )
    db.add_all([s_blood, s_urine, s_mri])
    db.flush()

    p_alpha = Partner(name="Клиника Альфа", city="Алматы")
    p_beta = Partner(name="Медцентр Бета", city="Астана")
    db.add_all([p_alpha, p_beta])
    db.flush()

    doc_a = PriceDocument(partner_id=p_alpha.partner_id, file_name="alpha.xlsx")
    doc_b = PriceDocument(partner_id=p_beta.partner_id, file_name="beta.xlsx")
    db.add_all([doc_a, doc_b])
    db.flush()

    items = [
        # Two partners offer blood test at different prices (sorting check).
        PriceItem(
            doc_id=doc_a.doc_id,
            partner_id=p_alpha.partner_id,
            service_id=s_blood.service_id,
            service_name_raw="Общий анализ крови",
            price_resident_kzt=Decimal("3000"),
            price_nonresident_kzt=Decimal("4000"),
            match_status=MatchStatus.matched_auto,
            match_method=MatchMethod.exact,
            match_confidence=1.0,
            is_active=True,
        ),
        PriceItem(
            doc_id=doc_b.doc_id,
            partner_id=p_beta.partner_id,
            service_id=s_blood.service_id,
            service_name_raw="ОАК",
            price_resident_kzt=Decimal("2500"),
            match_status=MatchStatus.matched_auto,
            match_method=MatchMethod.synonym,
            match_confidence=1.0,
            is_active=True,
        ),
        PriceItem(
            doc_id=doc_a.doc_id,
            partner_id=p_alpha.partner_id,
            service_id=s_urine.service_id,
            service_name_raw="Общий анализ мочи",
            price_resident_kzt=Decimal("2000"),
            match_status=MatchStatus.matched_auto,
            match_method=MatchMethod.exact,
            match_confidence=1.0,
            is_active=True,
        ),
        # Needs review: a near-miss MRI name.
        PriceItem(
            doc_id=doc_b.doc_id,
            partner_id=p_beta.partner_id,
            service_id=s_mri.service_id,
            service_name_raw="МРТ голов мозга",
            price_resident_kzt=Decimal("25000"),
            match_status=MatchStatus.needs_review,
            match_method=MatchMethod.fuzzy,
            match_confidence=0.72,
            needs_review=True,
            anomaly_flags=["price_outlier"],
            is_active=True,
        ),
        # Unmatched item.
        PriceItem(
            doc_id=doc_a.doc_id,
            partner_id=p_alpha.partner_id,
            service_id=None,
            service_name_raw="Консультация невролога повторная",
            price_resident_kzt=Decimal("8000"),
            match_status=MatchStatus.unmatched,
            match_method=MatchMethod.none,
            is_active=True,
        ),
    ]
    db.add_all(items)
    db.commit()

    return {
        "s_blood": s_blood.service_id,
        "s_urine": s_urine.service_id,
        "s_mri": s_mri.service_id,
        "p_alpha": p_alpha.partner_id,
        "p_beta": p_beta.partner_id,
        "review_item": items[3].item_id,
        "unmatched_item": items[4].item_id,
    }


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_services_and_filters(client, seed):
    r = client.get("/api/services")
    assert r.status_code == 200
    assert len(r.json()) == 3

    # category filter (case-insensitive)
    r = client.get("/api/services", params={"category": "лаборатория"})
    names = {s["service_name"] for s in r.json()}
    assert names == {"Общий анализ крови", "Общий анализ мочи"}

    # q filter matches a synonym
    r = client.get("/api/services", params={"q": "оак"})
    out = r.json()
    assert len(out) == 1
    assert out[0]["service_name"] == "Общий анализ крови"


def test_service_partners_sorted(client, seed):
    r = client.get(f"/api/services/{seed['s_blood']}/partners")
    assert r.status_code == 200
    out = r.json()
    assert len(out) == 2
    prices = [float(p["price_resident_kzt"]) for p in out]
    assert prices == sorted(prices)          # cheapest first
    assert prices[0] == 2500.0
    assert out[0]["partner"]["name"] == "Медцентр Бета"

    # 404 for unknown service
    assert client.get("/api/services/does-not-exist/partners").status_code == 404


def test_partners_and_detail_and_services(client, seed):
    r = client.get("/api/partners")
    assert r.status_code == 200
    assert len(r.json()) == 2

    r = client.get("/api/partners", params={"city": "алматы"})
    assert len(r.json()) == 1

    r = client.get(f"/api/partners/{seed['p_alpha']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Клиника Альфа"

    assert client.get("/api/partners/nope").status_code == 404

    r = client.get(f"/api/partners/{seed['p_alpha']}/services")
    assert r.status_code == 200
    svcs = r.json()
    # alpha has 3 active items (blood, urine, unmatched neurologist)
    assert len(svcs) == 3
    # unmatched item has no normalized name but keeps its raw name
    raws = {s["service_name_raw"] for s in svcs}
    assert "Консультация невролога повторная" in raws


def test_search(client, seed):
    r = client.get("/api/search", params={"q": "анализ"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "анализ"
    svc_names = {h["service_name"] for h in body["services"]}
    assert "Общий анализ крови" in svc_names
    # blood test has 2 partners with prices
    blood = next(h for h in body["services"] if h["service_name"] == "Общий анализ крови")
    assert blood["partner_count"] == 2
    assert float(blood["min_price_kzt"]) == 2500.0
    assert float(blood["max_price_kzt"]) == 3000.0

    # partner search
    r = client.get("/api/search", params={"q": "Альфа"})
    pnames = {h["name"] for h in r.json()["partners"]}
    assert "Клиника Альфа" in pnames

    # empty query -> empty response
    r = client.get("/api/search", params={"q": ""})
    assert r.json()["services"] == []
    assert r.json()["partners"] == []


def test_unmatched_with_candidates(client, seed):
    r = client.get("/api/unmatched")
    assert r.status_code == 200
    out = r.json()
    raws = {i["service_name_raw"] for i in out}
    assert "МРТ голов мозга" in raws            # needs_review
    assert "Консультация невролога повторная" in raws  # unmatched
    # needs_review sorts before unmatched
    assert out[0]["match_status"] == "needs_review"
    # the MRI near-miss should surface MRI as a candidate
    mri = next(i for i in out if i["service_name_raw"] == "МРТ голов мозга")
    cand_names = {c["service_name"] for c in mri["candidates"]}
    assert "МРТ головного мозга" in cand_names


def test_match_assigns_service(client, seed):
    r = client.post(
        "/api/match",
        json={"item_id": seed["unmatched_item"], "service_id": seed["s_mri"], "note": "manual"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["service_id"] == seed["s_mri"]
    assert body["match_status"] == "matched_manual"
    assert body["match_method"] == "manual"
    assert body["needs_review"] is False

    # neither service_id nor new_service -> 400
    r = client.post("/api/match", json={"item_id": seed["unmatched_item"]})
    assert r.status_code == 400

    # unknown item -> 404
    r = client.post("/api/match", json={"item_id": "nope", "service_id": seed["s_mri"]})
    assert r.status_code == 404


def test_match_creates_new_service(client, seed, db):
    r = client.post(
        "/api/match",
        json={
            "item_id": seed["unmatched_item"],
            "new_service": {
                "service_name": "Консультация невролога",
                "synonyms": ["невролог"],
                "category": "Консультации",
            },
        },
    )
    assert r.status_code == 200
    new_sid = r.json()["service_id"]
    assert new_sid is not None
    created = db.get(Service, new_sid)
    assert created is not None
    assert created.service_name == "Консультация невролога"


def test_admin_verify(client, seed):
    r = client.post(
        "/api/admin/verify",
        json={"item_id": seed["review_item"], "approve": True, "note": "ok"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_verified"] is True
    assert body["needs_review"] is False

    assert client.post(
        "/api/admin/verify", json={"item_id": "nope", "approve": True}
    ).status_code == 404


def test_admin_verification_queue(client, seed):
    r = client.get("/api/admin/verification")
    assert r.status_code == 200
    out = r.json()
    assert len(out) == 1
    rec = out[0]
    assert rec["service_name_raw"] == "МРТ голов мозга"
    assert rec["partner_name"] == "Медцентр Бета"
    assert rec["service_name"] == "МРТ головного мозга"
    assert rec["anomaly_flags"] == ["price_outlier"]


def test_admin_dashboard(client, seed):
    r = client.get("/api/admin/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert d["partners"] == 2
    assert d["services"] == 3
    assert d["price_items"] == 5
    assert d["items_matched_auto"] == 3
    assert d["items_needs_review"] == 1
    assert d["items_unmatched"] == 1
    assert d["items_with_anomalies"] == 1
    assert 0.0 <= d["normalization_rate"] <= 1.0
    assert "Лаборатория" in d["by_category"]
    assert "Алматы" in d["by_city"]


def test_admin_upload_and_process(client, db, monkeypatch):
    # No-op the background worker (patch both the source and the admin import).
    import app.ingestion as ingestion_pkg
    import app.api.admin as admin_mod

    monkeypatch.setattr(ingestion_pkg, "enqueue_batch_processing", lambda *a, **k: None)
    monkeypatch.setattr(admin_mod, "enqueue_batch_processing", lambda *a, **k: None)

    # Seed a catalog so the uploaded items can match.
    from app.normalization import seed_services

    seed_services(
        db,
        [
            {"service_name": "Общий анализ крови", "synonyms": ["ОАК"], "category": "Лаборатория", "icd_code": None},
            {"service_name": "Глюкоза крови", "synonyms": [], "category": "Лаборатория", "icd_code": None},
        ],
    )

    # Build a tiny in-memory .zip holding one xlsx.
    wb = Workbook()
    ws = wb.active
    ws.append(["Клиника Тест, г. Алматы"])
    ws.append(["Наименование услуги", "Цена, тг"])
    ws.append(["Общий анализ крови", "3 000"])
    ws.append(["Глюкоза крови", "1 800"])
    xlsx_buf = io.BytesIO()
    wb.save(xlsx_buf)
    xlsx_buf.seek(0)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("Клиника_Тест_прайс_2025-03-10.xlsx", xlsx_buf.getvalue())
    zip_buf.seek(0)

    r = client.post(
        "/api/admin/upload",
        files={"file": ("archive.zip", zip_buf, "application/zip")},
    )
    assert r.status_code == 200
    batch_id = r.json()["batch_id"]
    assert batch_id

    # Reject non-zip.
    r = client.post(
        "/api/admin/upload",
        files={"file": ("notes.txt", io.BytesIO(b"hi"), "text/plain")},
    )
    assert r.status_code == 400

    # Now drive the synchronous pipeline on the same test session.
    from app.ingestion import process_pending

    summary = process_pending(db, batch_id=batch_id)
    assert summary["total"] == 1

    doc = (
        db.query(PriceDocument)
        .filter(PriceDocument.batch_id == batch_id)
        .first()
    )
    assert doc is not None
    from app.enums import ParseStatus

    assert doc.parse_status in (ParseStatus.done, ParseStatus.needs_review)
