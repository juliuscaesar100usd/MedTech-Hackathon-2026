"""Tests for the ingestion pipeline (synchronous path) + partner dedup.

Each test stands up its OWN temp-file SQLite engine/Session so it never touches
``backend/medarchive.db``. The pipeline is exercised end-to-end against a tiny
ZIP holding one openpyxl-built workbook of catalog services + prices.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.enums import MatchStatus, ParseStatus
from app.ingestion import ingest_archive, process_pending, resolve_partner
from app.ingestion.partner import filename_hints
from app.models import IngestionBatch, PriceDocument, PriceItem
from app.normalization import seed_services

# Services that exist verbatim in the seeded catalog -> guaranteed exact matches.
CATALOG = [
    {"service_name": "Общий анализ крови", "synonyms": ["ОАК"], "category": "Лаборатория", "icd_code": None},
    {"service_name": "Общий анализ мочи", "synonyms": ["ОАМ"], "category": "Лаборатория", "icd_code": None},
    {"service_name": "Глюкоза крови", "synonyms": [], "category": "Лаборатория", "icd_code": None},
]


@pytest.fixture()
def db(tmp_path):
    """A throwaway temp-file SQLite Session bound to the app's metadata."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_xlsx(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Прайс"
    ws.append(["Клиника Тест-Мед, г. Алматы"])           # title row (noise)
    ws.append(["Наименование услуги", "Цена, тг"])        # header row
    ws.append(["Общий анализ крови", "3 000"])
    ws.append(["Общий анализ мочи", "2 500"])
    ws.append(["Глюкоза крови", "1 800"])
    wb.save(path)


def _make_zip(tmp_path: Path) -> Path:
    xlsx = tmp_path / "Клиника_Тест_прайс_2025-03-10.xlsx"
    _make_xlsx(xlsx)
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(xlsx, arcname=xlsx.name)
    return zip_path


def test_ingest_and_process_end_to_end(db, tmp_path):
    seed_services(db, CATALOG)
    zip_path = _make_zip(tmp_path)

    # --- ingest ---------------------------------------------------------- #
    batch = ingest_archive(db, str(zip_path), archive_name="archive.zip")
    assert batch.batch_id
    assert batch.total_files == 1

    docs = list(
        db.execute(
            select(PriceDocument).where(PriceDocument.batch_id == batch.batch_id)
        ).scalars()
    )
    assert len(docs) == 1
    doc = docs[0]
    assert doc.parse_status == ParseStatus.pending

    # Original bytes were persisted (NFR: never deleted).
    assert doc.stored_path is not None
    assert Path(doc.stored_path).exists()
    assert doc.sha256 and len(doc.sha256) == 64

    # --- process (synchronous) ------------------------------------------ #
    summary = process_pending(db, batch_id=batch.batch_id)
    assert summary["total"] == 1
    assert summary["n_items"] >= 3

    db.refresh(doc)
    assert doc.parse_status in (ParseStatus.done, ParseStatus.needs_review)
    assert doc.n_items >= 3
    assert doc.partner_id is not None

    # Items persisted with partner linkage + at least one auto match.
    items = list(
        db.execute(
            select(PriceItem).where(PriceItem.doc_id == doc.doc_id)
        ).scalars()
    )
    assert len(items) >= 3
    assert all(it.partner_id == doc.partner_id for it in items)
    assert any(it.match_status == MatchStatus.matched_auto for it in items)

    # Effective date came from the filename (2025-03-10).
    assert doc.effective_date is not None
    assert doc.effective_date.isoformat() == "2025-03-10"


def test_resolve_partner_dedup_by_bin(db):
    p1 = resolve_partner(db, name_hint="Клиника Альфа", bin_hint="123456789012")
    # Different name, same valid BIN -> must dedup onto the same partner.
    p2 = resolve_partner(
        db,
        name_hint="ТОО Альфа Клиник",
        bin_hint="123456789012",
        city_hint="Алматы",
    )
    assert p1.partner_id == p2.partner_id
    # Backfill: the city from the second call lands on the existing partner.
    assert p2.city == "Алматы"

    # A different BIN -> a distinct partner.
    p3 = resolve_partner(db, name_hint="Клиника Бета", bin_hint="999988887777")
    assert p3.partner_id != p1.partner_id


def test_resolve_partner_dedup_by_name_without_bin(db):
    a = resolve_partner(db, name_hint="Клиника  Сункар")
    b = resolve_partner(db, name_hint="клиника сункар")  # normalizes equal
    assert a.partner_id == b.partner_id


def test_filename_hints():
    h = filename_hints("Клиника_Сункар_прайс_2025-01-15.pdf")
    assert h["effective_date"].isoformat() == "2025-01-15"
    assert "Сункар" in (h["partner_name"] or "")
    # Noise tokens (прайс) stripped; date removed.
    assert "прайс" not in (h["partner_name"] or "").lower()
    assert "2025" not in (h["partner_name"] or "")
