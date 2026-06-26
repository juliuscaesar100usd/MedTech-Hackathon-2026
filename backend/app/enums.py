"""Enumerations shared across the domain model and API."""
from __future__ import annotations

from enum import Enum


class FileFormat(str, Enum):
    pdf = "pdf"              # text-based PDF (from DOCX etc.)
    scan_pdf = "scan_pdf"    # image-based PDF requiring OCR
    docx = "docx"
    xlsx = "xlsx"
    xls = "xls"
    unknown = "unknown"


class ParseStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    error = "error"
    needs_review = "needs_review"


class MatchStatus(str, Enum):
    matched_auto = "matched_auto"      # similarity >= auto threshold
    matched_manual = "matched_manual"  # operator confirmed/assigned
    needs_review = "needs_review"       # in [review, auto) band
    unmatched = "unmatched"            # below review threshold / no candidate


class MatchMethod(str, Enum):
    exact = "exact"
    synonym = "synonym"
    fuzzy = "fuzzy"
    embedding = "embedding"
    manual = "manual"
    none = "none"


class Currency(str, Enum):
    KZT = "KZT"
    USD = "USD"
    RUB = "RUB"


class BatchStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    partial = "partial"
    error = "error"
