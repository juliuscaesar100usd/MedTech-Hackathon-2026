"""Tests for the N-level category/section hierarchy (schema contract §2).

Covers:
  * catalog category_path parsing — all three input forms + RU header aliases,
  * seed_services persisting category_path,
  * GET /api/services/tree and GET /api/partners/{id}/tree (via TestClient),
  * section_path persistence through the ingestion pipeline,
  * the matcher's innermost→outer specialty prior over section_path.

Each test stands up its own throwaway temp-file SQLite engine, exactly like the
existing api/ingestion tests, so it never touches backend/medarchive.db.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.enums import Currency, FileFormat, MatchMethod, MatchStatus
from app.main import app
from app.models import Partner, PriceDocument, PriceItem, Service
from app.normalization import seed_services
from app.normalization.catalog import load_catalog_from_file


# --------------------------------------------------------------------------- #
# Fixtures (mirror tests/test_api.py)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_hier.db'}",
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


# --------------------------------------------------------------------------- #
# 1) Catalog path parsing — all three input forms + RU aliases
# --------------------------------------------------------------------------- #
def _load_objs(tmp_path: Path, objs: list[dict]) -> dict[str, dict]:
    p = tmp_path / "cat.json"
    p.write_text(json.dumps(objs, ensure_ascii=False), encoding="utf-8")
    return {it["service_name"]: it for it in load_catalog_from_file(p)}


def test_catalog_path_form_a_delimited_string(tmp_path):
    """(a) a path-delimited `category` string using '>' / '/' / '»'."""
    items = _load_objs(
        tmp_path,
        [
            {"service_name": "ТТГ", "category": "Лаборатория > Анализ крови > Гормоны"},
            {"service_name": "ОАК", "category": "Лаборатория / Анализ крови / Общий анализ"},
            {"service_name": "Глюкоза", "category": "Лаборатория » Биохимия"},
        ],
    )
    assert items["ТТГ"]["category_path"] == ["Лаборатория", "Анализ крови", "Гормоны"]
    assert items["ТТГ"]["category"] == "Лаборатория"  # category == path[0]
    assert items["ОАК"]["category_path"] == ["Лаборатория", "Анализ крови", "Общий анализ"]
    assert items["Глюкоза"]["category_path"] == ["Лаборатория", "Биохимия"]


def test_catalog_path_form_b_explicit_columns(tmp_path):
    """(b) explicit category + subcategory (+ subsubcategory) columns."""
    items = _load_objs(
        tmp_path,
        [
            {
                "service_name": "УЗИ почек",
                "category": "Диагностика",
                "subcategory": "УЗИ",
            },
            {
                "service_name": "ТТГ",
                "category": "Лаборатория",
                "subcategory": "Анализ крови",
                "subsubcategory": "Гормоны",
            },
        ],
    )
    assert items["УЗИ почек"]["category_path"] == ["Диагностика", "УЗИ"]
    assert items["ТТГ"]["category_path"] == ["Лаборатория", "Анализ крови", "Гормоны"]
    assert items["ТТГ"]["category"] == "Лаборатория"


def test_catalog_path_form_c_list_column(tmp_path):
    """(c) an explicit category_path list column; it wins over `category`."""
    items = _load_objs(
        tmp_path,
        [
            {
                "service_name": "МРТ",
                "category": "ignored",
                "category_path": ["Диагностика", "КТ и МРТ"],
            }
        ],
    )
    assert items["МРТ"]["category_path"] == ["Диагностика", "КТ и МРТ"]
    assert items["МРТ"]["category"] == "Диагностика"  # not "ignored"


def test_catalog_path_russian_aliases(tmp_path):
    """RU header aliases: подкатегория / подраздел and путь."""
    items = _load_objs(
        tmp_path,
        [
            {"service_name": "A", "категория": "Диагностика", "подкатегория": "УЗИ"},
            {"service_name": "B", "путь": "Лаборатория > Биохимия"},
        ],
    )
    assert items["A"]["category_path"] == ["Диагностика", "УЗИ"]
    assert items["B"]["category_path"] == ["Лаборатория", "Биохимия"]


def test_catalog_flat_and_empty(tmp_path):
    """A flat single category yields a 1-level path; no category -> None."""
    items = _load_objs(
        tmp_path,
        [
            {"service_name": "Flat", "category": "Консультация"},
            {"service_name": "Bare"},
        ],
    )
    assert items["Flat"]["category_path"] == ["Консультация"]
    assert items["Flat"]["category"] == "Консультация"
    assert items["Bare"]["category_path"] is None
    assert items["Bare"]["category"] is None


def test_sample_catalog_has_real_depth():
    """The shipped sample catalog (.json + .xlsx) has the enriched 3-level depth."""
    sample = Path(__file__).resolve().parent.parent / "sample_data"
    for fname in ("service_catalog.json", "service_catalog.xlsx"):
        items = load_catalog_from_file(sample / fname)
        by_name = {it["service_name"]: it["category_path"] for it in items}
        assert by_name["Тиреотропный гормон"] == ["Лаборатория", "Анализ крови", "Гормоны"]
        assert by_name["УЗИ почек"] == ["Диагностика", "УЗИ"]
        assert any(len(p or []) == 3 for p in by_name.values())


# --------------------------------------------------------------------------- #
# 2) seed_services persists category_path
# --------------------------------------------------------------------------- #
def test_seed_services_persists_category_path(db):
    seed_services(
        db,
        [
            {
                "service_name": "Тиреотропный гормон",
                "synonyms": ["ТТГ"],
                "category": "Лаборатория",
                "category_path": ["Лаборатория", "Анализ крови", "Гормоны"],
                "icd_code": None,
            },
        ],
    )
    svc = db.query(Service).filter_by(service_name="Тиреотропный гормон").one()
    assert svc.category == "Лаборатория"
    assert svc.category_path == ["Лаборатория", "Анализ крови", "Гормоны"]


# --------------------------------------------------------------------------- #
# 3) GET /api/services/tree
# --------------------------------------------------------------------------- #
def _seed_tree_services(db) -> None:
    db.add_all(
        [
            Service(
                service_name="Тиреотропный гормон",
                category="Лаборатория",
                category_path=["Лаборатория", "Анализ крови", "Гормоны"],
            ),
            Service(
                service_name="Глюкоза крови",
                category="Лаборатория",
                category_path=["Лаборатория", "Анализ крови", "Биохимия"],
            ),
            Service(
                service_name="УЗИ почек",
                category="Диагностика",
                category_path=["Диагностика", "УЗИ"],
            ),
            # Flat (1-level) service.
            Service(
                service_name="Консультация терапевта",
                category="Консультация",
                category_path=["Консультация"],
            ),
        ]
    )
    db.commit()


def test_services_tree_endpoint(client, db):
    _seed_tree_services(db)
    r = client.get("/api/services/tree")
    assert r.status_code == 200
    tree = r.json()["tree"]

    # Top-level nodes, Cyrillic-safe sorted: Диагностика, Консультация, Лаборатория.
    top_names = [n["name"] for n in tree]
    assert top_names == ["Диагностика", "Консультация", "Лаборатория"]

    lab = next(n for n in tree if n["name"] == "Лаборатория")
    assert lab["path"] == ["Лаборатория"]
    assert lab["services"] == []  # no leaves directly at the top
    blood = next(c for c in lab["children"] if c["name"] == "Анализ крови")
    assert blood["path"] == ["Лаборатория", "Анализ крови"]
    sub_names = sorted(c["name"] for c in blood["children"])
    assert sub_names == ["Биохимия", "Гормоны"]
    hormones = next(c for c in blood["children"] if c["name"] == "Гормоны")
    leaf_names = {s["service_name"] for s in hormones["services"]}
    assert leaf_names == {"Тиреотропный гормон"}
    # Leaf carries the full path back.
    assert hormones["services"][0]["category_path"] == [
        "Лаборатория", "Анализ крови", "Гормоны",
    ]

    # Flat service is a top-level node holding its leaf directly.
    cons = next(n for n in tree if n["name"] == "Консультация")
    assert cons["children"] == []
    assert {s["service_name"] for s in cons["services"]} == {"Консультация терапевта"}


# --------------------------------------------------------------------------- #
# 4) GET /api/partners/{id}/tree
# --------------------------------------------------------------------------- #
def test_partner_tree_endpoint(client, db):
    svc = Service(
        service_name="Тиреотропный гормон",
        category="Лаборатория",
        category_path=["Лаборатория", "Анализ крови", "Гормоны"],
    )
    db.add(svc)
    db.flush()
    partner = Partner(name="Клиника Альфа", city="Алматы")
    db.add(partner)
    db.flush()
    doc = PriceDocument(partner_id=partner.partner_id, file_name="alpha.xlsx")
    db.add(doc)
    db.flush()
    db.add_all(
        [
            PriceItem(
                doc_id=doc.doc_id,
                partner_id=partner.partner_id,
                service_id=svc.service_id,
                service_name_raw="ТТГ",
                section="Гормоны",
                section_path=["Лаборатория", "Анализ крови", "Гормоны"],
                price_resident_kzt=Decimal("5000"),
                match_status=MatchStatus.matched_auto,
                match_method=MatchMethod.synonym,
                is_active=True,
            ),
            # No section_path -> falls back to the matched service category.
            PriceItem(
                doc_id=doc.doc_id,
                partner_id=partner.partner_id,
                service_id=svc.service_id,
                service_name_raw="Тиреотропный гормон (контроль)",
                price_resident_kzt=Decimal("5500"),
                match_status=MatchStatus.matched_auto,
                match_method=MatchMethod.exact,
                is_active=True,
            ),
        ]
    )
    db.commit()

    r = client.get(f"/api/partners/{partner.partner_id}/tree")
    assert r.status_code == 200
    tree = r.json()["tree"]
    assert [n["name"] for n in tree] == ["Лаборатория"]

    lab = tree[0]
    # The sectioned item nests three levels deep with prices on the leaf.
    blood = next(c for c in lab["children"] if c["name"] == "Анализ крови")
    hormones = next(c for c in blood["children"] if c["name"] == "Гормоны")
    assert len(hormones["services"]) == 1
    leaf = hormones["services"][0]
    assert leaf["section_path"] == ["Лаборатория", "Анализ крови", "Гормоны"]
    assert float(leaf["price_resident_kzt"]) == 5000.0
    # The section-less item falls back to the service category at the top level.
    assert {s["service_name_raw"] for s in lab["services"]} == {
        "Тиреотропный гормон (контроль)"
    }

    # 404 for unknown partner.
    assert client.get("/api/partners/nope/tree").status_code == 404


# --------------------------------------------------------------------------- #
# 5) section_path persistence through the ingestion pipeline
# --------------------------------------------------------------------------- #
def test_pipeline_persists_section_path(db, monkeypatch):
    from app.ingestion import pipeline
    from app.normalization import build_matcher
    from app.parsers.base import ParsedDocument, ParsedRow

    seed_services(
        db,
        [
            {
                "service_name": "Тиреотропный гормон",
                "synonyms": ["ТТГ"],
                "category": "Лаборатория",
                "category_path": ["Лаборатория", "Анализ крови", "Гормоны"],
                "icd_code": None,
            }
        ],
    )

    # A fake parsed row carrying the new section_path field (set directly, so the
    # test works whether or not the parser's field has merged yet).
    row = ParsedRow(service_name_raw="Тиреотропный гормон", price_resident=5000.0)
    row.section_path = ["Лаборатория", "Анализ крови", "Гормоны"]

    def _fake_parse(stored_path, file_name=None):  # noqa: ARG001
        return ParsedDocument(file_format=FileFormat.xlsx, rows=[row], language="ru")

    monkeypatch.setattr(pipeline, "parse_file", _fake_parse)

    doc = PriceDocument(file_name="clinic.xlsx", stored_path="ignored.xlsx")
    db.add(doc)
    db.commit()

    matcher = build_matcher(db)
    pipeline.process_document(db, doc.doc_id, matcher=matcher)

    item = (
        db.query(PriceItem)
        .filter(PriceItem.service_name_raw == "Тиреотропный гормон")
        .one()
    )
    assert item.section_path == ["Лаборатория", "Анализ крови", "Гормоны"]
    # Innermost element is mirrored onto the back-compat `section` column.
    assert item.section == "Гормоны"


# --------------------------------------------------------------------------- #
# 6) Matcher specialty prior walks innermost -> outer over section_path
# --------------------------------------------------------------------------- #
def test_matcher_section_path_prior_innermost_first():
    from app.normalization.matcher import Matcher

    services = [
        SimpleNamespace(
            service_id="s1", service_name="Гормон щитовидной железы",
            synonyms=[], category="Лаборатория",
        ),
        SimpleNamespace(
            service_id="s2", service_name="Гормон роста биохимия",
            synonyms=[], category="Лаборатория",
        ),
    ]
    specialties = {"s1": ["Гормоны"], "s2": ["Биохимия"]}
    m = Matcher(services=services, service_specialties=specialties)

    # Innermost path element ("Гормоны") restricts candidates to s1.
    res = m.match("гормон", section_path=["Лаборатория", "Гормоны"])
    assert {c.service_id for c in res.candidates} == {"s1"}

    # Walk outward: innermost is unknown, the outer "Биохимия" restricts to s2.
    res2 = m.match("гормон", section_path=["Биохимия", "Несуществующий узел"])
    assert {c.service_id for c in res2.candidates} == {"s2"}

    # With no section context, both services remain candidates (no regression).
    res3 = m.match("гормон")
    assert {c.service_id for c in res3.candidates} == {"s1", "s2"}
