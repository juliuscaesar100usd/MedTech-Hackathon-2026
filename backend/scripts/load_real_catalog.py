"""CLI: load the REAL organizer service catalog into the database.

Usage (from ``backend/``):
    python -m scripts.load_real_catalog [<path-to-real_catalog.xlsx>]

Defaults to ``<repo>/data/catalog/real_catalog.xlsx``. Idempotent — safe to
re-run. Loads Service + ServiceSpecialty rows and prints/asserts the counts the
other lanes code against.

DB target is whatever ``DATABASE_URL`` points at; for an isolated lane-1 check:
    DATABASE_URL=sqlite:///./lane1.db python -m scripts.load_real_catalog
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.catalog_loader import REAL_CATALOG_DEFAULT_PATH, load_real_catalog
from app.database import SessionLocal, init_db

# Contract expectations for the real catalog (a fresh DB).
EXPECT_CODED_SERVICES = 511
EXPECT_SPECIALTIES = 122
EXPECT_SERVICE_SPECIALTIES = 1281


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else REAL_CATALOG_DEFAULT_PATH

    if not path.exists():
        print(f"ERROR: catalog file not found: {path}")
        return 1

    init_db()
    db = SessionLocal()
    try:
        counts = load_real_catalog(db, path)
    finally:
        db.close()

    print(f"Loaded real catalog from {path}")
    print(f"  rows read (valid)     : {counts['rows_read']}")
    print(f"  services created      : {counts['services_created']}")
    print(f"  links created         : {counts['links_created']}")
    print("  ---")
    print(f"  Service total         : {counts['services_total']}")
    print(f"    of which coded      : {counts['services_coded']}")
    print(f"    of which code=NULL  : {counts['services_uncoded']}")
    print(f"  ServiceSpecialty rows : {counts['service_specialties']}")
    print(f"  distinct specialties  : {counts['specialties']}")

    checks = [
        ("coded services", counts["services_coded"], EXPECT_CODED_SERVICES),
        ("distinct specialties", counts["specialties"], EXPECT_SPECIALTIES),
        ("service×specialty rows", counts["service_specialties"], EXPECT_SERVICE_SPECIALTIES),
    ]
    ok = True
    print("  ---")
    for label, got, want in checks:
        status = "OK" if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"  [{status}] {label}: {got} (expected {want})")

    if not ok:
        print("ASSERTION FAILED: counts do not match the catalog contract.")
        return 2
    print("All catalog assertions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
