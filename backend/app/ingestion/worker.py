"""Background processing for uploaded batches.

The HTTP upload endpoint must return immediately, so actual document processing
runs on a module-level :class:`ThreadPoolExecutor` with a single worker
(``max_workers=1``) — one writer keeps SQLite happy while still draining the
queue asynchronously. Each task owns its own :class:`SessionLocal` (sessions are
not thread-safe), builds the matcher once for the batch, and updates batch
status when done.
"""
from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select

from ..database import SessionLocal
from ..enums import BatchStatus, ParseStatus
from ..models import IngestionBatch, PriceDocument
from .pipeline import process_document, reconcile_active_versions
from ..normalization import build_matcher
from ..config import settings as default_settings

# Single shared executor (one writer thread -> no SQLite write contention).
_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()
# Track in-flight futures so wait_idle() can block on them.
_futures: set[Future] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="ingest"
            )
        return _executor


def _process_batch(batch_id: str) -> None:
    """Worker body: process all pending docs of a batch, then set its status."""
    db = SessionLocal()
    try:
        batch = db.get(IngestionBatch, batch_id)
        if batch is None:
            return
        batch.status = BatchStatus.processing
        db.commit()

        matcher = build_matcher(db, default_settings)

        doc_ids = list(
            db.execute(
                select(PriceDocument.doc_id).where(
                    PriceDocument.batch_id == batch_id,
                    PriceDocument.parse_status == ParseStatus.pending,
                )
            ).scalars()
        )

        errors = 0
        for doc_id in doc_ids:
            try:
                process_document(db, doc_id, matcher=matcher)
            except Exception:  # noqa: BLE001 - failure already recorded on doc
                errors += 1

        # Keep the latest-dated price active per service line across the batch.
        reconcile_active_versions(db)

        # Recompute batch counters from the live document rows (idempotent even
        # if this batch was processed before).
        docs = list(
            db.execute(
                select(PriceDocument).where(PriceDocument.batch_id == batch_id)
            ).scalars()
        )
        processed = sum(
            1
            for d in docs
            if d.parse_status in (ParseStatus.done, ParseStatus.needs_review)
        )
        error_files = sum(1 for d in docs if d.parse_status == ParseStatus.error)

        batch = db.get(IngestionBatch, batch_id)
        if batch is not None:
            batch.processed_files = processed
            batch.error_files = error_files
            if error_files == 0:
                batch.status = BatchStatus.done
            elif processed > 0:
                batch.status = BatchStatus.partial
            else:
                batch.status = BatchStatus.error
            batch.finished_at = _now()
            db.commit()
    finally:
        db.close()


def enqueue_batch_processing(batch_id: str) -> None:
    """Schedule background processing of ``batch_id``'s pending documents.

    Safe to call repeatedly: re-processing only touches docs still ``pending``
    and recomputes batch counters from scratch.
    """
    executor = _get_executor()
    future = executor.submit(_process_batch, batch_id)
    with _lock:
        _futures.add(future)
    future.add_done_callback(lambda f: _futures.discard(f))


def wait_idle(timeout: float | None = None) -> bool:
    """Block until all scheduled background work has drained.

    Returns True if the queue emptied within ``timeout`` (or no timeout given),
    False if it timed out. Used by tests to deterministically await the threaded
    path.
    """
    import concurrent.futures as _cf

    with _lock:
        pending = list(_futures)
    if not pending:
        return True
    done, not_done = _cf.wait(pending, timeout=timeout)
    return not not_done


def shutdown(wait: bool = True) -> None:
    """Shut the executor down (called by CLIs so no thread is left hanging)."""
    global _executor
    with _lock:
        ex = _executor
        _executor = None
    if ex is not None:
        ex.shutdown(wait=wait)
