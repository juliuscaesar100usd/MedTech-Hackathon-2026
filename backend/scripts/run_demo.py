"""End-to-end DEMO on the REAL organizer archive (data/archive/).

Loads the real service catalog, ingests every real clinic file, runs the full
pipeline (parse -> normalize -> validate -> version), and LEAVES THE DB SEEDED
(the app's default DB) so `make run` serves the result live.

    python -m scripts.run_demo

Embeddings load OFFLINE from the baked cache when present (see
scripts/bake_embedding_model.py); otherwise the matcher degrades to the lexical
chain automatically, so the demo still completes.
"""
from __future__ import annotations

import os
import tempfile
import time
import zipfile
from pathlib import Path

from app.config import settings
from app.database import Base, SessionLocal, engine, init_db
from app.catalog_loader import load_real_catalog
from app.enums import MatchStatus, ParseStatus
from app.ingestion import ingest_archive, process_pending
from app.models import PriceDocument, PriceItem

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = REPO_ROOT / "data" / "archive"


def _zip_archive_dir(dst: Path) -> int:
    files = sorted(p for p in ARCHIVE_DIR.iterdir() if p.is_file())
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, arcname=p.name)
    return len(files)


def main() -> int:
    if not ARCHIVE_DIR.is_dir() or not any(ARCHIVE_DIR.iterdir()):
        print(f"ERROR: real archive not found at {ARCHIVE_DIR}")
        return 1

    t0 = time.time()
    print(f"DB: {settings.database_url}")
    print(f"Embeddings: {'ON' if settings.use_embeddings else 'OFF'} "
          f"(offline={settings.embeddings_offline})")

    # Rebuild the schema from scratch. create_all() never ALTERs an existing
    # table, so a pre-existing medarchive.db would be missing the new hierarchy
    # columns (Service.category_path / PriceItem.section_path). drop_all +
    # create_all guarantees the live demo DB has them. The demo reseeds all data
    # below, so wiping the old rows is intended.
    import app.models  # noqa: F401  (register mappers before drop/create)

    print("Rebuilding schema (drop_all + create_all) so new columns exist…")
    Base.metadata.drop_all(bind=engine)
    init_db()
    db = SessionLocal()
    try:
        print("\n[1/3] Loading real catalog…")
        counts = load_real_catalog(db)
        print(f"      {counts['services_coded']} coded services / "
              f"{counts['specialties']} specialties / {counts['service_specialties']} links")

        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "real_archive.zip"
            n = _zip_archive_dir(zpath)
            print(f"\n[2/3] Ingesting {n} real clinic files from data/archive/ …")
            batch = ingest_archive(db, str(zpath), archive_name="data/archive")
            print("\n[3/3] Processing (parse → normalize → validate → version)…")
            process_pending(db, batch_id=batch.batch_id)

        docs = db.query(PriceDocument).all()
        items = db.query(PriceItem).all()
        active = [i for i in items if i.is_active]
        auto = sum(
            1 for i in active
            if i.match_status in (MatchStatus.matched_auto, MatchStatus.matched_manual)
        )
        errs = sum(1 for d in docs if d.parse_status == ParseStatus.error)
    finally:
        db.close()

    dt = time.time() - t0
    print("\n" + "=" * 60)
    print("MedArchive — REAL-data demo seeded")
    print("=" * 60)
    print(f"  Docs:            {len(docs)}  ({errs} error)")
    print(f"  Price items:     {len(items)}  ({len(active)} active)")
    print(f"  Auto-normalized: {auto}/{len(active)} = "
          f"{(auto / len(active) * 100) if active else 0:.1f}% (active)")
    print(f"  Elapsed:         {dt:.0f}s")
    print("  DB is seeded — run `make run` to serve it live.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
