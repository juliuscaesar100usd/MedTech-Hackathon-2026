"""Integration test: reconcile_active_versions picks the latest-dated price as
active regardless of the order documents were processed (real-archive safety)."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.enums import MatchStatus
from app.ingestion import reconcile_active_versions
from app.models import Partner, PriceDocument, PriceItem


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _item(doc, partner, name, price, eff, version, active):
    return PriceItem(
        doc_id=doc.doc_id, partner_id=partner.partner_id,
        service_name_raw=name, price_resident_kzt=price,
        effective_date=eff, version=version, is_active=active,
        match_status=MatchStatus.matched_auto, service_id="svc-1",
    )


def test_latest_date_becomes_active_after_out_of_order_processing(db):
    p = Partner(name="Клиника А")
    d = PriceDocument(file_name="x", partner_id=None)
    db.add_all([p, d]); db.flush()
    d.partner_id = p.partner_id

    # Simulate out-of-order ingestion: the NEWEST date was processed first and
    # then archived by an OLDER-dated document (the bug reconcile fixes).
    newest = _item(d, p, "Общий анализ крови", 3000, date(2025, 6, 1), 1, active=False)
    middle = _item(d, p, "Общий анализ крови", 2700, date(2025, 1, 1), 2, active=False)
    oldest = _item(d, p, "Общий анализ крови", 2500, date(2024, 1, 1), 3, active=True)
    db.add_all([newest, middle, oldest]); db.commit()

    changed = reconcile_active_versions(db)
    assert changed >= 1

    actives = db.query(PriceItem).filter(PriceItem.is_active.is_(True)).all()
    assert len(actives) == 1
    assert actives[0].effective_date == date(2025, 6, 1)   # newest date wins
    assert float(actives[0].price_resident_kzt) == 3000.0
    # History preserved: all three rows still exist.
    assert db.query(PriceItem).count() == 3


def test_single_version_untouched(db):
    p = Partner(name="Клиника Б")
    d = PriceDocument(file_name="y")
    db.add_all([p, d]); db.flush()
    d.partner_id = p.partner_id
    only = _item(d, p, "ЭКГ", 4000, date(2025, 3, 1), 1, active=True)
    db.add(only); db.commit()
    assert reconcile_active_versions(db) == 0
    assert only.is_active is True
