"""Generate the synthetic service catalog in both supported formats.

Writes:
  * ``backend/sample_data/service_catalog.xlsx`` — header row
    ``[service_name, synonyms, category, icd_code]`` (synonyms ';'-joined),
  * ``backend/sample_data/service_catalog.json`` — a JSON array of objects
    ``{service_name, synonyms:[...], category, icd_code}``.

Both are accepted as-is by ``app.normalization.catalog.load_catalog_from_file``.

Run: ``python -m scripts.generate_service_catalog`` (from ``backend/``).
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook

from ._sampledata_spec import SERVICES

OUT_DIR = Path(__file__).resolve().parent.parent / "sample_data"
XLSX_PATH = OUT_DIR / "service_catalog.xlsx"
JSON_PATH = OUT_DIR / "service_catalog.json"

HEADER = ["service_name", "synonyms", "category", "icd_code"]


def build_records() -> list[dict]:
    return [
        {
            "service_name": s.name,
            "synonyms": list(s.synonyms),
            "category": s.category,
            "icd_code": s.icd_code,
        }
        for s in SERVICES
    ]


def write_xlsx(records: list[dict], path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "catalog"
    ws.append(HEADER)
    for r in records:
        ws.append(
            [
                r["service_name"],
                ";".join(r["synonyms"]),
                r["category"] or "",
                r["icd_code"] or "",
            ]
        )
    wb.save(path)


def write_json(records: list[dict], path: Path) -> None:
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records = build_records()
    write_xlsx(records, XLSX_PATH)
    write_json(records, JSON_PATH)

    n_syn = sum(len(r["synonyms"]) for r in records)
    cats = sorted({r["category"] for r in records})
    print(f"Wrote {XLSX_PATH} ({len(records)} services)")
    print(f"Wrote {JSON_PATH} ({len(records)} services)")
    print(f"Total synonyms: {n_syn}")
    print(f"Categories ({len(cats)}): {', '.join(cats)}")

    # Sanity check: round-trip through the real loader (both formats).
    try:
        from app.normalization.catalog import load_catalog_from_file

        for p in (XLSX_PATH, JSON_PATH):
            loaded = load_catalog_from_file(p)
            assert len(loaded) == len(records), (
                f"loader returned {len(loaded)} != {len(records)} from {p.name}"
            )
            assert all(it["service_name"] for it in loaded)
            assert any(it["synonyms"] for it in loaded)
        print("Loader round-trip OK for both .xlsx and .json")
    except Exception as exc:  # pragma: no cover - sanity aid only
        print(f"WARNING: loader round-trip check skipped/failed: {exc}")


if __name__ == "__main__":
    main()
