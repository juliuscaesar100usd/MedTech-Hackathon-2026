"""Tests for the MedArchive VALIDATION / CURRENCY / VERSIONING module (spec §4.4).

Everything runs on an isolated in-memory SQLite engine — the real
``backend/medarchive.db`` is never touched.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.enums import Currency, MatchMethod, MatchStatus
from app.models import MatchEvent, Partner, PriceDocument, PriceItem
from app.normalization.types import MatchResult
from app.parsers.base import ParsedRow
from app.validation import (
    convert_to_kzt,
    finalize_document_status,
    get_rate,
    upsert_with_versioning,
    validate_row,
    verify_item,
)


# --------------------------------------------------------------------------- #
# Fixtures: in-memory DB                                                       #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_match(
    service_id: str | None = "svc-1",
    status: MatchStatus = MatchStatus.matched_auto,
    method: MatchMethod = MatchMethod.exact,
    score: float | None = 0.99,
) -> MatchResult:
    return MatchResult(
        service_id=service_id, score=score, method=method, status=status
    )


def _make_partner_and_doc(db: Session, eff: date) -> tuple[Partner, PriceDocument]:
    partner = Partner(name="Клиника А", city="Алматы")
    db.add(partner)
    db.flush()
    doc = PriceDocument(
        partner_id=partner.partner_id,
        file_name="price.xlsx",
        effective_date=eff,
    )
    db.add(doc)
    db.flush()
    return partner, doc


# --------------------------------------------------------------------------- #
# (a) Currency conversion                                                      #
# --------------------------------------------------------------------------- #
def test_kzt_rate_is_identity():
    assert get_rate(Currency.KZT, date(2025, 4, 15)) == 1.0
    kzt, rate = convert_to_kzt(Decimal("1000"), Currency.KZT, date(2025, 4, 15))
    assert kzt == Decimal("1000.00")
    assert rate == 1.0


def test_usd_april_2025_rate():
    # 2025-04-01 USD = 505.0; a mid-April date picks the nearest dated rate <=.
    rate = get_rate("USD", date(2025, 4, 15))
    assert rate == pytest.approx(505.0)
    kzt, used = convert_to_kzt("100", Currency.USD, date(2025, 4, 15))
    assert used == pytest.approx(505.0)
    assert kzt == Decimal("50500.00")


def test_nearest_date_lookup_picks_earlier_rate():
    # Between 2025-04-01 (505) and 2025-07-01 (512): May -> 505.
    assert get_rate("USD", date(2025, 5, 20)) == pytest.approx(505.0)
    # Before the earliest dated rate -> earliest (2023-01-01 = 462).
    assert get_rate("USD", date(2020, 1, 1)) == pytest.approx(462.0)
    # None date -> default map (USD default = 500.0).
    assert get_rate("USD", None) == pytest.approx(500.0)


# --------------------------------------------------------------------------- #
# (b) Per-row validators                                                       #
# --------------------------------------------------------------------------- #
def test_empty_name_skips_row():
    row = ParsedRow(service_name_raw="   ", price_resident=1000)
    out = validate_row(row, date(2024, 1, 1))
    assert out.skip is True
    assert out.skip_reason == "empty_service_name"
    assert out.log_messages


@pytest.mark.parametrize("bad", [-5, 0, None, "abc"])
def test_invalid_price_flags(bad):
    row = ParsedRow(service_name_raw="ОАК", price_resident=bad)
    out = validate_row(row, date(2024, 1, 1))
    assert out.skip is False
    assert "INVALID_PRICE" in out.anomaly_flags
    assert out.needs_review is True


def test_nonresident_lower_than_resident_flags():
    row = ParsedRow(
        service_name_raw="ОАК", price_resident=5000, price_nonresident=4000
    )
    out = validate_row(row, date(2024, 1, 1))
    assert "NONRESIDENT_LT_RESIDENT" in out.anomaly_flags
    assert out.needs_review is True


def test_future_date_flags_warning_only():
    future = date.today() + timedelta(days=30)
    row = ParsedRow(service_name_raw="ОАК", price_resident=5000)
    out = validate_row(row, future)
    assert "FUTURE_DATE" in out.anomaly_flags
    # Spec: warning only — must not force manual review on its own.
    assert out.needs_review is False


def test_usd_row_converts_and_keeps_original():
    row = ParsedRow(
        service_name_raw="МРТ",
        price_resident=100,
        price_original=100,
        currency=Currency.USD,
    )
    out = validate_row(row, date(2025, 4, 15))
    assert out.currency_original == Currency.USD
    assert out.price_original == Decimal("100")
    assert out.fx_rate_to_kzt == pytest.approx(505.0)
    assert out.price_resident_kzt == Decimal("50500.00")


# --------------------------------------------------------------------------- #
# (c) Versioning: anomaly + dedup                                             #
# --------------------------------------------------------------------------- #
def test_price_anomaly_archives_old_and_versions(db: Session):
    # v1: price 5000 on 2024-01-01
    _, doc1 = _make_partner_and_doc(db, date(2024, 1, 1))
    partner_id = doc1.partner_id
    row1 = ParsedRow(service_name_raw="ОАК", price_resident=5000)
    out1 = validate_row(row1, doc1.effective_date)
    item1 = upsert_with_versioning(
        db,
        document=doc1,
        partner_id=partner_id,
        row=row1,
        outcome=out1,
        match=_make_match(),
    )
    db.commit()
    assert item1 is not None
    assert item1.version == 1
    assert "PRICE_ANOMALY" not in item1.anomaly_flags

    # v2: same service, different date, price 9000 (+80% > 50%)
    doc2 = PriceDocument(
        partner_id=partner_id, file_name="price2.xlsx", effective_date=date(2025, 1, 1)
    )
    db.add(doc2)
    db.flush()
    row2 = ParsedRow(service_name_raw="ОАК", price_resident=9000)
    out2 = validate_row(row2, doc2.effective_date)
    item2 = upsert_with_versioning(
        db,
        document=doc2,
        partner_id=partner_id,
        row=row2,
        outcome=out2,
        match=_make_match(),
    )
    db.commit()

    assert item2 is not None
    assert "PRICE_ANOMALY" in item2.anomaly_flags
    assert item2.needs_review is True
    assert item2.version == 2
    assert item2.previous_item_id == item1.item_id

    db.refresh(item1)
    assert item1.is_active is False
    assert item2.is_active is True

    # exactly one active row for this service line
    actives = db.execute(
        select(PriceItem).where(
            PriceItem.partner_id == partner_id,
            PriceItem.service_name_raw == "ОАК",
            PriceItem.is_active.is_(True),
        )
    ).scalars().all()
    assert len(actives) == 1


def test_no_anomaly_under_threshold(db: Session):
    _, doc1 = _make_partner_and_doc(db, date(2024, 1, 1))
    pid = doc1.partner_id
    row1 = ParsedRow(service_name_raw="ЭКГ", price_resident=10000)
    upsert_with_versioning(
        db,
        document=doc1,
        partner_id=pid,
        row=row1,
        outcome=validate_row(row1, doc1.effective_date),
        match=_make_match(),
    )
    db.commit()

    doc2 = PriceDocument(
        partner_id=pid, file_name="p2.xlsx", effective_date=date(2025, 1, 1)
    )
    db.add(doc2)
    db.flush()
    row2 = ParsedRow(service_name_raw="ЭКГ", price_resident=12000)  # +20%
    item2 = upsert_with_versioning(
        db,
        document=doc2,
        partner_id=pid,
        row=row2,
        outcome=validate_row(row2, doc2.effective_date),
        match=_make_match(),
    )
    db.commit()
    assert "PRICE_ANOMALY" not in item2.anomaly_flags


def test_dedup_same_partner_service_date(db: Session):
    _, doc = _make_partner_and_doc(db, date(2024, 6, 1))
    pid = doc.partner_id
    row = ParsedRow(service_name_raw="УЗИ", price_resident=7000)

    first = upsert_with_versioning(
        db,
        document=doc,
        partner_id=pid,
        row=row,
        outcome=validate_row(row, doc.effective_date),
        match=_make_match(),
    )
    db.commit()

    # same partner + service + date inserted again -> dedup
    second = upsert_with_versioning(
        db,
        document=doc,
        partner_id=pid,
        row=row,
        outcome=validate_row(row, doc.effective_date),
        match=_make_match(),
    )
    db.commit()

    db.refresh(first)
    assert first.is_active is False
    assert second.is_active is True
    assert second.version == first.version + 1
    assert second.previous_item_id == first.item_id

    actives = db.execute(
        select(PriceItem).where(
            PriceItem.partner_id == pid,
            PriceItem.service_name_raw == "УЗИ",
            PriceItem.is_active.is_(True),
        )
    ).scalars().all()
    assert len(actives) == 1


def test_skipped_row_returns_none(db: Session):
    _, doc = _make_partner_and_doc(db, date(2024, 1, 1))
    row = ParsedRow(service_name_raw="", price_resident=1000)
    out = validate_row(row, doc.effective_date)
    item = upsert_with_versioning(
        db,
        document=doc,
        partner_id=doc.partner_id,
        row=row,
        outcome=out,
        match=_make_match(),
    )
    assert item is None


def test_match_needs_review_propagates(db: Session):
    _, doc = _make_partner_and_doc(db, date(2024, 1, 1))
    row = ParsedRow(service_name_raw="Новая услуга", price_resident=3000)
    out = validate_row(row, doc.effective_date)
    item = upsert_with_versioning(
        db,
        document=doc,
        partner_id=doc.partner_id,
        row=row,
        outcome=out,
        match=_make_match(service_id=None, status=MatchStatus.needs_review,
                          method=MatchMethod.fuzzy, score=0.7),
    )
    db.commit()
    assert item.needs_review is True
    assert item.match_status == MatchStatus.needs_review


# --------------------------------------------------------------------------- #
# finalize_document_status                                                     #
# --------------------------------------------------------------------------- #
def test_finalize_document_status(db: Session):
    from app.enums import ParseStatus

    _, doc = _make_partner_and_doc(db, date(2024, 1, 1))
    # No items -> error
    assert finalize_document_status(doc, 0, 0) == ParseStatus.error

    # One clean item -> done
    row = ParsedRow(service_name_raw="ОАК", price_resident=5000)
    upsert_with_versioning(
        db,
        document=doc,
        partner_id=doc.partner_id,
        row=row,
        outcome=validate_row(row, doc.effective_date),
        match=_make_match(),
    )
    db.flush()
    assert finalize_document_status(doc, 1, 0) == ParseStatus.done

    # Add an item that needs review -> needs_review
    row2 = ParsedRow(service_name_raw="ОАК", price_resident=-1)  # INVALID_PRICE
    upsert_with_versioning(
        db,
        document=doc,
        partner_id=doc.partner_id,
        row=row2,
        outcome=validate_row(row2, doc.effective_date),
        match=_make_match(),
    )
    db.flush()
    assert finalize_document_status(doc, 2, 0) == ParseStatus.needs_review


# --------------------------------------------------------------------------- #
# (d) Operator verification                                                    #
# --------------------------------------------------------------------------- #
def test_verify_item_approve_clears_review_and_records_event(db: Session):
    _, doc = _make_partner_and_doc(db, date(2024, 1, 1))
    row = ParsedRow(service_name_raw="ОАК", price_resident=-1)  # needs_review
    item = upsert_with_versioning(
        db,
        document=doc,
        partner_id=doc.partner_id,
        row=row,
        outcome=validate_row(row, doc.effective_date),
        match=_make_match(service_id=None, status=MatchStatus.unmatched,
                          method=MatchMethod.none, score=None),
    )
    db.commit()
    assert item.needs_review is True

    verified = verify_item(
        db,
        item.item_id,
        approve=True,
        service_id="svc-corrected",
        price_resident_kzt=Decimal("4500"),
        note="confirmed by operator",
        operator="alice",
    )
    assert verified.is_verified is True
    assert verified.needs_review is False
    assert verified.service_id == "svc-corrected"
    assert verified.match_status == MatchStatus.matched_manual
    assert verified.match_method == MatchMethod.manual
    assert verified.price_resident_kzt == Decimal("4500.00")
    assert verified.verified_by == "alice"
    assert verified.verified_at is not None

    events = db.execute(
        select(MatchEvent).where(MatchEvent.item_id == item.item_id)
    ).scalars().all()
    assert len(events) == 1
    assert events[0].action == "verify"
    assert events[0].new_service_id == "svc-corrected"


def test_verify_item_reject_records_reject_event(db: Session):
    _, doc = _make_partner_and_doc(db, date(2024, 1, 1))
    row = ParsedRow(service_name_raw="ОАК", price_resident=5000)
    item = upsert_with_versioning(
        db,
        document=doc,
        partner_id=doc.partner_id,
        row=row,
        outcome=validate_row(row, doc.effective_date),
        match=_make_match(),
    )
    db.commit()

    verified = verify_item(db, item.item_id, approve=False, note="wrong service")
    assert verified.is_verified is False
    events = db.execute(
        select(MatchEvent).where(MatchEvent.item_id == item.item_id)
    ).scalars().all()
    assert events[0].action == "reject"


def test_verify_item_missing_raises(db: Session):
    with pytest.raises(LookupError):
        verify_item(db, "does-not-exist")
