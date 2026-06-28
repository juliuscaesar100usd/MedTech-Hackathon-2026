"""Regression tests over the REAL organizer archive (data/archive/).

These lock in the parsing-quality work: every real clinic file must extract a
healthy number of priced rows (no silent under-extraction / zero-row files), the
known-clean formats must stay clean, and a sample of hand-verified gold rows must
be reproduced. Gold fixtures live in ``tests/_archive_golds.json`` and were
produced by per-file diagnosis of the real documents.

The suite skips gracefully when the archive, the gold file, or the optional
``xlrd`` engine (needed for the legacy .xls) is unavailable, so it never breaks a
hermetic CI image that ships without the real data.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from app.parsers import parse_file

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "data" / "archive"
GOLDS_PATH = Path(__file__).resolve().parent / "_archive_golds.json"

# Formats that should parse cleanly enough to enforce ZERO forbidden-name hits
# and ALL gold rows (the tabular/office formats; the scanned-quality PDFs carry
# known residual OCR noise and are checked more loosely).
_STRICT_FILES = {
    "Клиника 1 прайс 2024.docx",
    "Клиника 6 прайс 2026.xlsx",
    "Клиника 7_Прайс 2026.xls",
    "Клиника 8 2026.xlsx",
}


def _load_golds() -> dict:
    if not ARCHIVE.is_dir() or not GOLDS_PATH.is_file():
        pytest.skip("real archive or gold fixtures not present")
    return json.loads(GOLDS_PATH.read_text(encoding="utf-8"))


def _require_xls_engine(fname: str) -> None:
    if fname.lower().endswith(".xls"):
        try:
            import xlrd  # noqa: F401
        except Exception:
            pytest.skip("xlrd not installed; legacy .xls cannot be parsed")


_GOLDS = _load_golds() if (ARCHIVE.is_dir() and GOLDS_PATH.is_file()) else {}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _price_matches(row, expected) -> bool:
    if expected is None:
        return True
    for val in (row.price_resident, row.price_original, row.price_nonresident):
        if val is not None and abs(val - expected) < 0.5:
            return True
    return False


@pytest.mark.skipif(not _GOLDS, reason="no gold fixtures / archive")
@pytest.mark.parametrize("fname", sorted(_GOLDS))
def test_archive_file_quality(fname, monkeypatch):
    # Keep the suite fast + deterministic: the per-page OCR fallback (which only
    # fires on broken-text-layer pages) is exercised by the demo, not here; the
    # floors below are all met by the pure text-layer extraction.
    monkeypatch.setenv("OCR_PAGE_FALLBACK", "0")
    g = _GOLDS[fname]
    path = ARCHIVE / fname
    if not path.is_file():
        pytest.skip(f"missing archive file {fname!r}")
    _require_xls_engine(fname)

    doc = parse_file(str(path), fname)
    rows = doc.rows
    names = [r.service_name_raw for r in rows]

    # 1) No silent under-extraction. Stay at/above a safe floor of the per-file
    #    true-row estimate (guards the xls 0-row failure + PDF wrap losses).
    floor = max(1, math.floor(0.85 * g["min_rows"]))
    assert len(rows) >= floor, (
        f"{fname}: only {len(rows)} rows (floor {floor}, true~{g['estimated_true_rows']})"
    )

    # 2) Almost no junk: a resident price below 5 KZT is a misparsed index/qty.
    junk = [r for r in rows if r.price_resident is not None and 0 < r.price_resident < 5]
    assert len(junk) <= 2, f"{fname}: {len(junk)} junk (<5 KZT) rows, e.g. {junk[:2]}"

    # 3) Hand-verified gold rows must be reproduced (name + price).
    by_norm = {}
    for r in rows:
        by_norm.setdefault(_norm(r.service_name_raw), r)
    gold = g.get("must_appear_rows") or []
    present = 0
    for m in gold:
        en = _norm(m["expected_name"])
        cands = [r for k, r in by_norm.items() if en[:24] and (en[:24] in k or k in en)]
        if any(_price_matches(r, m.get("res")) for r in cands):
            present += 1
    if gold:
        need = len(gold) if fname in _STRICT_FILES else math.ceil(0.5 * len(gold))
        assert present >= need, (
            f"{fname}: only {present}/{len(gold)} gold rows reproduced (need {need})"
        )

    # 4) Known-clean formats must have NO forbidden-pattern names.
    if fname in _STRICT_FILES:
        for pat in g.get("forbidden_name_patterns") or []:
            try:
                rx = re.compile(pat)
            except re.error:
                continue
            bad = [nm for nm in names if rx.search(nm)]
            assert not bad, f"{fname}: forbidden /{pat}/ matched {bad[:3]}"


def test_legacy_xls_not_zero_rows():
    """The legacy .xls (Клиника 7) must not silently yield zero rows."""
    xls = ARCHIVE / "Клиника 7_Прайс 2026.xls"
    if not xls.is_file():
        pytest.skip("xls archive file not present")
    _require_xls_engine(xls.name)
    doc = parse_file(str(xls), xls.name)
    assert len(doc.rows) > 2500, f"xls parsed only {len(doc.rows)} rows"
