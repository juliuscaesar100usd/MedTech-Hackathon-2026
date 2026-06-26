"""Domain model — implements the entities from the ТЗ (§3) plus the supporting
tables needed for the ingestion queue, matching queue and price versioning.

UUIDs are stored as 36-char strings and JSON via the portable SQLAlchemy JSON
type so the exact same schema runs on SQLite (dev) and PostgreSQL (prod).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .enums import (
    BatchStatus,
    Currency,
    FileFormat,
    MatchMethod,
    MatchStatus,
    ParseStatus,
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# §3.4 Service (target reference catalogue)
# --------------------------------------------------------------------------- #
class Service(Base):
    __tablename__ = "services"

    service_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    service_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    synonyms: Mapped[list] = mapped_column(JSON, default=list)         # list[str]
    category: Mapped[str | None] = mapped_column(String(128), index=True)
    icd_code: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    items: Mapped[list["PriceItem"]] = relationship(back_populates="service")


# --------------------------------------------------------------------------- #
# §3.1 Partner
# --------------------------------------------------------------------------- #
class Partner(Base):
    __tablename__ = "partners"

    partner_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(128), index=True)
    address: Mapped[str | None] = mapped_column(String(512))
    bin: Mapped[str | None] = mapped_column(String(12), index=True)  # for dedup
    contact_email: Mapped[str | None] = mapped_column(String(256))
    contact_phone: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    documents: Mapped[list["PriceDocument"]] = relationship(back_populates="partner")
    items: Mapped[list["PriceItem"]] = relationship(back_populates="partner")


# --------------------------------------------------------------------------- #
# Ingestion batch (a single uploaded ZIP archive)
# --------------------------------------------------------------------------- #
class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"

    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    archive_name: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[BatchStatus] = mapped_column(String(16), default=BatchStatus.pending)
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    processed_files: Mapped[int] = mapped_column(Integer, default=0)
    error_files: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    documents: Mapped[list["PriceDocument"]] = relationship(back_populates="batch")


# --------------------------------------------------------------------------- #
# §3.2 PriceDocument (also serves as the processing queue row)
# --------------------------------------------------------------------------- #
class PriceDocument(Base):
    __tablename__ = "price_documents"

    doc_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    partner_id: Mapped[str | None] = mapped_column(
        ForeignKey("partners.partner_id"), index=True
    )
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingestion_batches.batch_id"), index=True
    )
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_format: Mapped[FileFormat] = mapped_column(String(16), default=FileFormat.unknown)
    stored_path: Mapped[str | None] = mapped_column(String(1024))  # original kept for re-processing
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime)
    parse_status: Mapped[ParseStatus] = mapped_column(
        String(16), default=ParseStatus.pending, index=True
    )
    parse_log: Mapped[str | None] = mapped_column(Text)
    raw_content: Mapped[str | None] = mapped_column(Text)  # extracted text for audit
    language: Mapped[str | None] = mapped_column(String(16))
    n_items: Mapped[int] = mapped_column(Integer, default=0)
    n_matched: Mapped[int] = mapped_column(Integer, default=0)
    partner_confidence: Mapped[float | None] = mapped_column(Float)

    partner: Mapped["Partner"] = relationship(back_populates="documents")
    batch: Mapped["IngestionBatch"] = relationship(back_populates="documents")
    items: Mapped[list["PriceItem"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


# --------------------------------------------------------------------------- #
# §3.3 PriceItem  (+ matching + versioning fields)
# --------------------------------------------------------------------------- #
class PriceItem(Base):
    __tablename__ = "price_items"

    item_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(ForeignKey("price_documents.doc_id"), index=True)
    partner_id: Mapped[str | None] = mapped_column(
        ForeignKey("partners.partner_id"), index=True
    )  # denormalised for speed

    service_name_raw: Mapped[str] = mapped_column(String(1024), nullable=False)
    service_code_source: Mapped[str | None] = mapped_column(String(128))
    service_id: Mapped[str | None] = mapped_column(
        ForeignKey("services.service_id"), index=True
    )

    # Prices
    price_resident_kzt: Mapped[float | None] = mapped_column(Numeric(14, 2))
    price_nonresident_kzt: Mapped[float | None] = mapped_column(Numeric(14, 2))
    price_original: Mapped[float | None] = mapped_column(Numeric(14, 2))
    currency_original: Mapped[Currency] = mapped_column(String(8), default=Currency.KZT)
    fx_rate_to_kzt: Mapped[float | None] = mapped_column(Float)

    # Matching
    match_status: Mapped[MatchStatus] = mapped_column(
        String(20), default=MatchStatus.unmatched, index=True
    )
    match_method: Mapped[MatchMethod] = mapped_column(String(16), default=MatchMethod.none)
    match_confidence: Mapped[float | None] = mapped_column(Float)

    # Verification
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    verification_note: Mapped[str | None] = mapped_column(String(1024))
    verified_by: Mapped[str | None] = mapped_column(String(128))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Validation
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    anomaly_flags: Mapped[list] = mapped_column(JSON, default=list)  # list[str]

    # Lifecycle / versioning  (price history kept indefinitely)
    effective_date: Mapped[date | None] = mapped_column(Date, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    previous_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("price_items.item_id")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    document: Mapped["PriceDocument"] = relationship(back_populates="items")
    partner: Mapped["Partner"] = relationship(back_populates="items")
    service: Mapped["Service"] = relationship(back_populates="items")

    __table_args__ = (
        Index("ix_priceitem_active_service", "service_id", "is_active"),
        Index("ix_priceitem_dedup", "partner_id", "service_name_raw", "effective_date"),
    )


# Lightweight audit of every manual match/verify action (operator traceability)
class MatchEvent(Base):
    __tablename__ = "match_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(ForeignKey("price_items.item_id"), index=True)
    old_service_id: Mapped[str | None] = mapped_column(String(36))
    new_service_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(32))  # match / verify / reject / create
    note: Mapped[str | None] = mapped_column(String(1024))
    operator: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
