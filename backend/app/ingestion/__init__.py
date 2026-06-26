"""Ingestion pipeline — the PUBLIC CONTRACT other teams code against.

Flow:
  1. :func:`ingest_archive` — open a clinic price-list ZIP, persist each
     original file (never deleted — NFR), and create a ``pending``
     :class:`PriceDocument` per supported entry under one
     :class:`IngestionBatch`.
  2. :func:`enqueue_batch_processing` — schedule async processing (used by the
     HTTP upload endpoint so the request returns immediately).
  3. :func:`process_document` / :func:`process_pending` — the actual
     parse -> resolve -> match -> validate -> version pipeline (synchronous;
     take an explicit Session so tests inject their own engine).

Originals are stored at ``settings.data_dir/originals/<batch_id>/<safe_name>``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings as default_settings
from ..enums import BatchStatus, ParseStatus
from ..models import IngestionBatch, PriceDocument
from ..parsers import detect_format
from .archive import (
    ArchiveEntry,
    count_supported_entries,
    iter_supported_entries,
    safe_filename,
    sha256_bytes,
)
from .partner import filename_hints, resolve_partner
from .pipeline import process_document, process_pending, reconcile_active_versions
from .worker import enqueue_batch_processing, shutdown, wait_idle


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _unique_path(directory: Path, safe_name: str) -> Path:
    """Return a non-colliding path inside ``directory`` for ``safe_name``."""
    candidate = directory / safe_name
    if not candidate.exists():
        return candidate
    stem, ext = (safe_name.rsplit(".", 1) + [""])[:2]
    sep = "." if ext else ""
    i = 1
    while True:
        candidate = directory / f"{stem}_{i}{sep}{ext}"
        if not candidate.exists():
            return candidate
        i += 1


def ingest_archive(
    db: Session,
    zip_path: str,
    archive_name: str | None = None,
) -> IngestionBatch:
    """Open a ZIP, persist originals, and create the batch + pending documents.

    Returns the committed :class:`IngestionBatch`. Does NOT start processing —
    call :func:`enqueue_batch_processing` (async) or :func:`process_pending`
    (sync) afterwards.
    """
    settings = default_settings
    total = count_supported_entries(zip_path)

    batch = IngestionBatch(
        archive_name=archive_name or Path(zip_path).name,
        status=BatchStatus.processing,
        total_files=total,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    originals_dir = Path(settings.data_dir) / "originals" / batch.batch_id
    originals_dir.mkdir(parents=True, exist_ok=True)

    entry: ArchiveEntry
    for entry in iter_supported_entries(zip_path):
        dest = _unique_path(originals_dir, entry.safe_name)
        # Persist the ORIGINAL bytes verbatim (never deleted — NFR).
        dest.write_bytes(entry.data)

        sha = sha256_bytes(entry.data)
        fmt = detect_format(str(dest), entry.original_name)

        doc = PriceDocument(
            batch_id=batch.batch_id,
            file_name=entry.original_name,
            stored_path=str(dest),
            sha256=sha,
            file_format=fmt,
            parse_status=ParseStatus.pending,
        )
        db.add(doc)

    db.commit()
    db.refresh(batch)
    return batch


__all__ = [
    # public contract
    "ingest_archive",
    "enqueue_batch_processing",
    "process_document",
    "process_pending",
    "reconcile_active_versions",
    "resolve_partner",
    # helpers used by scripts/tests
    "filename_hints",
    "wait_idle",
    "shutdown",
]
