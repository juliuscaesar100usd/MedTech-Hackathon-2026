"""CLI: end-to-end demo bootstrap (run on first boot / README quickstart).

Usage (from ``backend/``):
    python -m scripts.bootstrap_demo [--quiet]

Steps:
  1. init the database,
  2. (re)generate sample catalog + archive if they are missing,
  3. seed the service catalog,
  4. ingest + synchronously process the sample archive,
  5. print a concise data-quality summary.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select

from app.database import SessionLocal, init_db
from app.enums import MatchStatus, ParseStatus
from app.ingestion import ingest_archive, process_pending
from app.models import PriceDocument, PriceItem, Service
from app.normalization import load_catalog_from_file, seed_services

BACKEND_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = BACKEND_ROOT / "sample_data"
CATALOG_XLSX = SAMPLE_DIR / "service_catalog.xlsx"
ARCHIVE_ZIP = SAMPLE_DIR / "archive.zip"


def _ensure_sample_data(quiet: bool) -> None:
    """Generate the catalog/archive if either is missing."""
    if not CATALOG_XLSX.exists():
        if not quiet:
            print("Sample catalog missing — generating…")
        from scripts.generate_service_catalog import main as gen_catalog

        gen_catalog()
    if not ARCHIVE_ZIP.exists():
        if not quiet:
            print("Sample archive missing — generating…")
        from scripts.generate_sample_archive import main as gen_archive

        gen_archive()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    quiet = "--quiet" in argv

    init_db()
    _ensure_sample_data(quiet)

    # --- seed catalog ----------------------------------------------------- #
    items = load_catalog_from_file(CATALOG_XLSX)
    db = SessionLocal()
    try:
        seed_services(db, items)
        n_services = db.query(Service).count()
        if not quiet:
            print(f"Catalog seeded: {n_services} services.\n")

        # --- ingest + process --------------------------------------------- #
        batch = ingest_archive(db, str(ARCHIVE_ZIP), archive_name=ARCHIVE_ZIP.name)
        if not quiet:
            print(
                f"Ingested '{ARCHIVE_ZIP.name}' "
                f"({batch.total_files} supported files); processing…\n"
            )
        process_pending(db, batch_id=batch.batch_id)

        # --- quality summary ---------------------------------------------- #
        docs = list(
            db.execute(
                select(PriceDocument).where(
                    PriceDocument.batch_id == batch.batch_id
                )
            ).scalars()
        )
        n_docs = len(docs)
        n_done = sum(
            1
            for d in docs
            if d.parse_status in (ParseStatus.done, ParseStatus.needs_review)
        )
        n_error = sum(1 for d in docs if d.parse_status == ParseStatus.error)

        doc_ids = [d.doc_id for d in docs]
        if doc_ids:
            total_items = db.execute(
                select(func.count(PriceItem.item_id)).where(
                    PriceItem.doc_id.in_(doc_ids)
                )
            ).scalar_one()
            n_auto = db.execute(
                select(func.count(PriceItem.item_id)).where(
                    PriceItem.doc_id.in_(doc_ids),
                    PriceItem.match_status.in_(
                        [MatchStatus.matched_auto, MatchStatus.matched_manual]
                    ),
                )
            ).scalar_one()
            n_unmatched = db.execute(
                select(func.count(PriceItem.item_id)).where(
                    PriceItem.doc_id.in_(doc_ids),
                    PriceItem.match_status == MatchStatus.unmatched,
                )
            ).scalar_one()
            n_review = db.execute(
                select(func.count(PriceItem.item_id)).where(
                    PriceItem.doc_id.in_(doc_ids),
                    PriceItem.needs_review.is_(True),
                )
            ).scalar_one()
        else:
            total_items = n_auto = n_unmatched = n_review = 0

        pct_auto = (100.0 * n_auto / total_items) if total_items else 0.0
    finally:
        db.close()

    print("=" * 56)
    print("MedArchive — bootstrap demo quality summary")
    print("=" * 56)
    print(f"  Documents:      {n_docs} total | {n_done} processed | {n_error} error")
    print(f"  Price items:    {total_items}")
    print(f"  Auto-normalized:{n_auto:>5}  ({pct_auto:.1f}% of items)")
    print(f"  Unmatched:      {n_unmatched}")
    print(f"  Needs review:   {n_review}")
    print("=" * 56)

    # Non-zero exit if nothing processed (CI / docker first-boot signal).
    return 0 if n_done > 0 and total_items > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
