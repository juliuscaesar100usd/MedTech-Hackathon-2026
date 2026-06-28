"""CLI: seed the target service catalog into the database.

Usage (from ``backend/``):
    python -m scripts.seed_catalog [<path-to-catalog.xlsx|json>]

Defaults to ``backend/sample_data/service_catalog.xlsx`` when no path is given.
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.database import SessionLocal, init_db
from app.models import Service
from app.normalization import load_catalog_from_file, seed_services

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = BACKEND_ROOT / "sample_data" / "service_catalog.xlsx"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else DEFAULT_CATALOG

    if not path.exists():
        print(f"ERROR: catalog file not found: {path}")
        return 1

    init_db()
    items = load_catalog_from_file(path)
    db = SessionLocal()
    try:
        n = seed_services(db, items)
        services = db.query(Service).all()
        total = len(services)
        n_syn = sum(len(s.synonyms or []) for s in services)
        # Hierarchy depth summary (the optional N-level category support).
        depths = [len(s.category_path or []) for s in services]
        max_depth = max(depths) if depths else 0
        n_nested = sum(1 for d in depths if d >= 2)
    finally:
        db.close()

    print(f"Loaded {len(items)} catalog records from {path.name}")
    print(f"Seeded/updated {n} services (total in DB: {total}; synonyms: {n_syn})")
    print(f"Category hierarchy: max depth {max_depth}; {n_nested} multi-level services")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
