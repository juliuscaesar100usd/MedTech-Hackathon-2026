"""CLI: ingest a ZIP archive and process it synchronously (no threads).

Usage (from ``backend/``):
    python -m scripts.run_ingest [<archive.zip>]

Defaults to ``backend/sample_data/archive.zip``. Prints a per-document table
(file, format, status, n_items, n_matched) plus totals.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.ingestion import ingest_archive, process_pending
from app.models import PriceDocument

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARCHIVE = BACKEND_ROOT / "sample_data" / "archive.zip"


def _print_table(rows: list[PriceDocument]) -> None:
    headers = ("FILE", "FORMAT", "STATUS", "ITEMS", "MATCHED")
    name_w = max([len(headers[0])] + [len(r.file_name) for r in rows]) if rows else len(headers[0])
    name_w = min(name_w, 50)
    fmt_w = 9
    st_w = 13
    line = f"{headers[0]:<{name_w}}  {headers[1]:<{fmt_w}}  {headers[2]:<{st_w}}  {headers[3]:>5}  {headers[4]:>7}"
    print(line)
    print("-" * len(line))
    for r in rows:
        name = r.file_name if len(r.file_name) <= name_w else r.file_name[: name_w - 1] + "…"
        fmt = r.file_format.value if hasattr(r.file_format, "value") else str(r.file_format)
        st = r.parse_status.value if hasattr(r.parse_status, "value") else str(r.parse_status)
        print(
            f"{name:<{name_w}}  {fmt:<{fmt_w}}  {st:<{st_w}}  "
            f"{r.n_items or 0:>5}  {r.n_matched or 0:>7}"
        )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    archive = Path(argv[0]) if argv else DEFAULT_ARCHIVE

    if not archive.exists():
        print(f"ERROR: archive not found: {archive}")
        return 1

    init_db()
    db = SessionLocal()
    try:
        batch = ingest_archive(db, str(archive), archive_name=archive.name)
        print(f"Ingested archive '{archive.name}' as batch {batch.batch_id}")
        print(f"Supported files: {batch.total_files}\n")

        summary = process_pending(db, batch_id=batch.batch_id)

        docs = list(
            db.execute(
                select(PriceDocument)
                .where(PriceDocument.batch_id == batch.batch_id)
                .order_by(PriceDocument.file_name)
            ).scalars()
        )
        _print_table(docs)

        print()
        print(
            f"Totals: {summary['total']} docs | done={summary['done']} "
            f"needs_review={summary['needs_review']} error={summary['error']} | "
            f"items={summary['n_items']} matched={summary['n_matched']}"
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
