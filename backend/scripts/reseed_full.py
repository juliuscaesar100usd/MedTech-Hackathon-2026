"""Authoritative FULL (100%, OCR-on) re-seed of data/archive + a saved parse report.

Drops & recreates the demo tables in-place (no file deletion), loads the real
catalog, ingests every file in data/archive/, and processes the whole batch with
the per-page OCR fallback ENABLED (maximum extraction). Then writes a per-file
parse report to docs/PARSE_REPORT.md + docs/parse_report.json so the parsed
information is persisted, and prints a summary table.

    cd backend && PYTHONPATH=. .venv/bin/python -m scripts.reseed_full
"""
from __future__ import annotations

import json
import os
import time
import zipfile
import tempfile
from pathlib import Path

os.environ.setdefault("OCR_PAGE_FALLBACK", "1")  # 100% extraction

from app.database import Base, SessionLocal, engine, init_db
from app.catalog_loader import load_real_catalog
from app.ingestion import ingest_archive, process_pending
from app.models import PriceDocument, PriceItem, Partner

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "data" / "archive"
DOCS = REPO / "docs"


def main() -> int:
    t0 = time.time()
    print(f"FULL reseed (OCR on). archive={ARCHIVE}", flush=True)

    # Clean slate in-place (no file deletion).
    Base.metadata.drop_all(bind=engine)
    init_db()

    db = SessionLocal()
    try:
        counts = load_real_catalog(db)
        print(f"catalog: {counts}", flush=True)

        files = sorted(p for p in ARCHIVE.iterdir() if p.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "archive.zip"
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
                for p in files:
                    z.write(p, arcname=p.name)
            batch = ingest_archive(db, str(zpath), archive_name="data/archive")
            print(f"ingested {len(files)} files; processing (OCR on)...", flush=True)
            summary = process_pending(db, batch_id=batch.batch_id)
        print(f"SUMMARY: {summary}", flush=True)

        # Per-file parse report.
        rows = []
        for d in db.query(PriceDocument).order_by(PriceDocument.file_name).all():
            rows.append({
                "file": d.file_name,
                "format": d.file_format.value if hasattr(d.file_format, "value") else str(d.file_format),
                "status": d.parse_status.value if hasattr(d.parse_status, "value") else str(d.parse_status),
                "items": d.n_items or 0,
                "matched": d.n_matched or 0,
                "partner": (db.get(Partner, d.partner_id).name if d.partner_id else None),
            })
        totals = {
            "files": len(rows),
            "partners": db.query(Partner).count(),
            "price_items": db.query(PriceItem).count(),
            "active_items": db.query(PriceItem).filter(PriceItem.is_active.is_(True)).count(),
            "matched_items": sum(r["matched"] for r in rows),
            "elapsed_sec": round(time.time() - t0, 1),
        }
    finally:
        db.close()

    DOCS.mkdir(exist_ok=True)
    (DOCS / "parse_report.json").write_text(
        json.dumps({"totals": totals, "files": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Markdown report.
    lines = [
        "# MedArchive — Parse Report (data/archive, 100% / OCR-on)",
        "",
        f"- Files parsed: **{totals['files']}**  |  Partners: **{totals['partners']}**",
        f"- Price items: **{totals['price_items']}** (active **{totals['active_items']}**)  |  "
        f"Matched: **{totals['matched_items']}**",
        f"- Elapsed: **{totals['elapsed_sec']}s**",
        "",
        "| File | Format | Status | Items | Matched | Partner |",
        "|---|---|---|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['file']} | {r['format']} | {r['status']} | {r['items']} | "
            f"{r['matched']} | {r['partner'] or '—'} |"
        )
    (DOCS / "PARSE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {DOCS/'PARSE_REPORT.md'} and parse_report.json", flush=True)
    print("REPORT_TOTALS:", json.dumps(totals, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
