"""Pydantic v2 schemas — request/response contracts for the REST API."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    BatchStatus,
    Currency,
    FileFormat,
    MatchMethod,
    MatchStatus,
    ParseStatus,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------- Service ---------------------------------------- #
class ServiceOut(ORMModel):
    service_id: str
    service_name: str
    synonyms: list[str] = []
    category: str | None = None
    icd_code: str | None = None
    is_active: bool = True


class ServiceCreate(BaseModel):
    service_name: str
    synonyms: list[str] = []
    category: str | None = None
    icd_code: str | None = None


# --------------------------- Partner ---------------------------------------- #
class PartnerOut(ORMModel):
    partner_id: str
    name: str
    city: str | None = None
    address: str | None = None
    bin: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --------------------------- Price items ------------------------------------ #
class PriceItemOut(ORMModel):
    item_id: str
    doc_id: str
    partner_id: str | None = None
    service_id: str | None = None
    service_name_raw: str
    service_code_source: str | None = None
    price_resident_kzt: Decimal | None = None
    price_nonresident_kzt: Decimal | None = None
    price_original: Decimal | None = None
    currency_original: Currency = Currency.KZT
    match_status: MatchStatus
    match_method: MatchMethod
    match_confidence: float | None = None
    is_verified: bool = False
    verification_note: str | None = None
    needs_review: bool = False
    anomaly_flags: list[str] = []
    effective_date: date | None = None
    is_active: bool = True
    version: int = 1


# Partner + price for a given service (GET /services/{id}/partners)
class PartnerPriceOut(BaseModel):
    partner: PartnerOut
    item_id: str
    service_name_raw: str
    price_resident_kzt: Decimal | None = None
    price_nonresident_kzt: Decimal | None = None
    currency_original: Currency = Currency.KZT
    effective_date: date | None = None
    is_verified: bool = False
    match_confidence: float | None = None


# Service + price for a partner (GET /partners/{id}/services)
class ServicePriceOut(BaseModel):
    item_id: str
    service_id: str | None = None
    service_name: str | None = None       # normalized name (if matched)
    service_name_raw: str
    category: str | None = None
    price_resident_kzt: Decimal | None = None
    price_nonresident_kzt: Decimal | None = None
    currency_original: Currency = Currency.KZT
    effective_date: date | None = None
    match_status: MatchStatus
    is_verified: bool = False


# --------------------------- Unmatched / candidates ------------------------- #
class MatchCandidate(BaseModel):
    service_id: str
    service_name: str
    category: str | None = None
    score: float
    method: MatchMethod


class UnmatchedItemOut(ORMModel):
    item_id: str
    doc_id: str
    partner_id: str | None = None
    partner_name: str | None = None
    service_name_raw: str
    service_code_source: str | None = None
    price_resident_kzt: Decimal | None = None
    match_status: MatchStatus
    match_confidence: float | None = None
    candidates: list[MatchCandidate] = []


# --------------------------- Match request ---------------------------------- #
class MatchRequest(BaseModel):
    item_id: str
    service_id: str | None = Field(
        default=None, description="Existing catalog service to link to."
    )
    new_service: ServiceCreate | None = Field(
        default=None, description="Create a new catalog service and link to it."
    )
    note: str | None = None
    operator: str | None = "operator"


class VerifyRequest(BaseModel):
    item_id: str
    approve: bool = True
    service_id: str | None = None        # optional correction
    price_resident_kzt: Decimal | None = None  # optional correction
    price_nonresident_kzt: Decimal | None = None
    note: str | None = None
    operator: str | None = "operator"


# --------------------------- Documents / batches ---------------------------- #
class PriceDocumentOut(ORMModel):
    doc_id: str
    partner_id: str | None = None
    batch_id: str | None = None
    file_name: str
    file_format: FileFormat
    effective_date: date | None = None
    parsed_at: datetime | None = None
    parse_status: ParseStatus
    parse_log: str | None = None
    language: str | None = None
    n_items: int = 0
    n_matched: int = 0


class BatchOut(ORMModel):
    batch_id: str
    archive_name: str | None = None
    status: BatchStatus
    total_files: int = 0
    processed_files: int = 0
    error_files: int = 0
    created_at: datetime | None = None
    finished_at: datetime | None = None


# --------------------------- Dashboard -------------------------------------- #
class DashboardStats(BaseModel):
    partners: int
    services: int
    documents: int
    documents_done: int
    documents_error: int
    documents_pending: int
    price_items: int
    items_matched_auto: int
    items_matched_manual: int
    items_needs_review: int
    items_unmatched: int
    items_verified: int
    items_with_anomalies: int
    normalization_rate: float            # matched / total
    auto_normalization_rate: float       # auto-matched / total
    verification_rate: float
    by_category: dict[str, int] = {}
    by_city: dict[str, int] = {}
    recent_batches: list[BatchOut] = []


# --------------------------- Search ----------------------------------------- #
class SearchHitService(BaseModel):
    type: str = "service"
    service_id: str
    service_name: str
    category: str | None = None
    partner_count: int = 0
    min_price_kzt: Decimal | None = None
    max_price_kzt: Decimal | None = None
    score: float = 0.0


class SearchHitPartner(BaseModel):
    type: str = "partner"
    partner_id: str
    name: str
    city: str | None = None
    service_count: int = 0
    score: float = 0.0


class SearchResponse(BaseModel):
    query: str
    services: list[SearchHitService] = []
    partners: list[SearchHitPartner] = []


# --------------------------- Auth ------------------------------------------- #
class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=256)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _looks_like_email(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("invalid email")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(ORMModel):
    id: str
    email: str
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    token: str
    user: UserOut
