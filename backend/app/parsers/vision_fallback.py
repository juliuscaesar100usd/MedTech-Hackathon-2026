"""Claude vision fallback for low-confidence scanned pages (Fix B).

Tesseract is and stays the default OCR engine (see ``pdf_scan``). On skewed or
low-quality scans the geometry-based reconstruction can detach prices from their
service names. For *those* pages only — detected via ``is_low_confidence`` — the
caller renders the page to PNG (PyMuPDF ~150 DPI) and asks the Anthropic vision
model ``claude-sonnet-4-6`` to return ONLY JSON rows. We then parse that JSON into
the same ``ParsedRow`` contract every other parser emits.

Design notes:
  * triggers ONLY on low OCR confidence (many non-dictionary tokens / names without
    an adjacent price) — never on healthy pages,
  * caches results per page-hash (identical re-render → no second API call),
  * bounds API concurrency with a module-level semaphore,
  * degrades gracefully: missing ``anthropic`` package / no API key / API error all
    leave the Tesseract rows untouched (the caller keeps them).

Heavy imports (``anthropic``, ``base64``) are deferred into the call path so this
module stays importable — and unit-testable — without the optional dependency or a
network/API key.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path

from ..enums import Currency
from .base import ParsedRow
from .table_extract import parse_price

# --------------------------------------------------------------------------- #
# Configuration.                                                               #
# --------------------------------------------------------------------------- #
VISION_MODEL = "claude-sonnet-4-6"   # specified by the task; do not "upgrade" silently
VISION_DPI = 150
_MAX_TOKENS = 8000

# Bound how many vision calls may be in flight at once (pages are processed
# sequentially today, but this keeps us safe if the loop is ever parallelised).
_MAX_CONCURRENCY = max(1, int(os.getenv("VISION_MAX_CONCURRENCY", "3") or "3"))
_SEMAPHORE = threading.Semaphore(_MAX_CONCURRENCY)

# Per page-hash cache of extracted rows (avoids a second call for an identical page).
_CACHE: dict[str, list[ParsedRow]] = {}
_CACHE_LOCK = threading.Lock()

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_PROMPT = (
    "You are extracting rows from a scanned medical price list (Russian/Kazakh). "
    "The scan may be skewed, so columns can be misaligned.\n"
    "Return ONLY a JSON array — no prose, no markdown, no code fences. Each element:\n"
    '{"service_name_raw": string, "service_code_source": string|null, '
    '"section": string|null, "prices": [{"label": string, "value": number}], '
    '"unit": string|null}\n'
    "Rules:\n"
    "- Join service names split across multiple lines into a single string.\n"
    "- 'section' is the category heading the row falls under (e.g. 'ПРИЕМ ВРАЧА', "
    "'ЛАБОРАТОРНЫЕ ИССЛЕДОВАНИЯ'), or null if none applies.\n"
    "- 'prices' must include every price column with its column label (e.g. 'РК', "
    "'ближнее', 'дальнее', 'резидент', 'нерезидент'); 'value' is a plain number with "
    "no spaces, separators, or currency symbols.\n"
    "- Ignore page furniture: clinic name, address, БИН/ИИН, phone, e-mail, page "
    "numbers, the column header row itself, and footers.\n"
    "- Omit any row that has no price. Return [] if the page has no priced services."
)


# --------------------------------------------------------------------------- #
# OCR confidence — when to trigger the fallback.                               #
# --------------------------------------------------------------------------- #
def is_low_confidence(data: dict | None, page_rows: list) -> tuple[bool, str]:
    """Decide whether a page's Tesseract output is too weak to trust.

    `data` is the pytesseract ``image_to_data`` DICT for the page (or None).
    Returns ``(low, reason)``. Low when mean word confidence is poor, or when the
    page has many name-like text lines but few of them yielded a priced row
    (the "prices detached from names" failure on skewed scans).
    """
    if not data:
        # No geometry at all: low only if we also failed to reconstruct any row.
        return (len(page_rows) == 0), "no-tsv-data"

    confs: list[int] = []
    line_words: dict[tuple, list[str]] = {}
    n = len(data.get("text", []))
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        try:
            c = int(float(data["conf"][i]))
        except (ValueError, TypeError):
            c = -1
        if c >= 0:
            confs.append(c)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        line_words.setdefault(key, []).append(txt)

    mean_conf = sum(confs) / len(confs) if confs else 0.0
    # "name lines": lines that carry real words (a service name candidate).
    name_lines = [
        ws for ws in line_words.values()
        if any(ch.isalpha() for w in ws for ch in w) and len(" ".join(ws)) >= 4
    ]
    n_names = len(name_lines)
    priced = len(page_rows)
    priced_fraction = (priced / n_names) if n_names else 1.0

    reasons: list[str] = []
    low = False
    if confs and mean_conf < 55:
        low = True
        reasons.append(f"mean_conf={mean_conf:.0f}")
    if n_names >= 6 and priced_fraction < 0.4:
        low = True
        reasons.append(f"priced={priced}/{n_names}")
    if n_names >= 4 and priced == 0:
        low = True
        reasons.append("no-rows")
    if not low:
        reasons.append(f"ok(mean_conf={mean_conf:.0f},priced={priced}/{n_names})")
    return low, ";".join(reasons)


# --------------------------------------------------------------------------- #
# Availability + credentials.                                                  #
# --------------------------------------------------------------------------- #
def _load_api_key() -> str | None:
    """ANTHROPIC_API_KEY from the environment, falling back to a .env file."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    for env_path in (
        _BACKEND_ROOT / ".env",
        _BACKEND_ROOT.parent / ".env",
        Path.cwd() / ".env",
    ):
        try:
            if not env_path.is_file():
                continue
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY") and "=" in line:
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
        except OSError:
            continue
    return None


def vision_available() -> tuple[bool, str | None]:
    """``(True, None)`` if the vision fallback can run, else ``(False, reason)``."""
    if os.getenv("VISION_FALLBACK_ENABLED", "1").lower() in ("0", "false", "no", "off"):
        return False, "disabled via VISION_FALLBACK_ENABLED"
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False, "anthropic package not installed"
    if not _load_api_key():
        return False, "ANTHROPIC_API_KEY not set"
    return True, None


# --------------------------------------------------------------------------- #
# JSON parsing + row mapping.                                                  #
# --------------------------------------------------------------------------- #
def _parse_json_rows(text: str) -> list | None:
    """Pull a JSON array of row objects out of the model's reply, robustly."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    start, end = t.find("["), t.rfind("]")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    try:
        data = json.loads(t)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(data, dict):
        for k in ("rows", "items", "data", "services"):
            if isinstance(data.get(k), list):
                return data[k]
        return [data]
    return data if isinstance(data, list) else None


def _coerce_num(v: object) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    val, _ = parse_price(str(v))
    return val if (val is not None and val > 0) else None


# Price-column label hints (lowercased substrings).
_RES_LABELS = ("рк", "резидент", "граждан", "местн")
_NONRES_LABELS = ("нерезидент", "дальн", "ближн", "иностран", "зарубеж")


def _vision_row_to_parsed(obj: dict, ref: str) -> ParsedRow | None:
    name = str(obj.get("service_name_raw") or "").strip()
    if len(name) < 2 or not any(ch.isalpha() for ch in name):
        return None

    parsed: list[tuple[str, float]] = []
    for p in obj.get("prices") or []:
        if not isinstance(p, dict):
            continue
        val = _coerce_num(p.get("value"))
        if val is None:
            continue
        parsed.append((str(p.get("label") or "").lower(), val))
    if not parsed:
        return None

    res = nonres = None
    for label, val in parsed:
        if res is None and any(k in label for k in _RES_LABELS) and "нерезидент" not in label:
            res = val
        elif nonres is None and any(k in label for k in _NONRES_LABELS):
            nonres = val
    # Positional fallback when labels were unhelpful: first = resident, second = non-resident.
    if res is None:
        res = parsed[0][1]
    if nonres is None and len(parsed) > 1:
        nonres = parsed[1][1]

    extra: dict = {"extraction": "vision"}
    section = obj.get("section")
    if section:
        extra["section"] = str(section).strip()
    unit = obj.get("unit")
    if unit:
        extra["unit"] = str(unit).strip()

    code = obj.get("service_code_source")
    return ParsedRow(
        service_name_raw=name,
        price_resident=res,
        price_nonresident=nonres,
        price_original=res if res is not None else nonres,
        currency=Currency.KZT,
        service_code_source=str(code).strip() if code else None,
        source_ref=ref,
        extra=extra,
    )


# --------------------------------------------------------------------------- #
# API call.                                                                    #
# --------------------------------------------------------------------------- #
def _call_vision(png_bytes: bytes) -> str:
    """Send the page PNG to the Anthropic vision model; return its text reply."""
    import base64

    import anthropic  # local import: optional dependency

    api_key = _load_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    with _SEMAPHORE:
        resp = client.messages.create(
            model=VISION_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }],
        )
    return "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    )


def extract_rows_via_vision(
    png_bytes: bytes, ref: str, caller=None
) -> list[ParsedRow]:
    """Vision-extract priced rows from one rendered page.

    Cached per page-hash. `caller(png_bytes) -> str` is injectable for testing;
    it defaults to the live Anthropic call.
    """
    page_hash = hashlib.sha256(png_bytes).hexdigest()
    with _CACHE_LOCK:
        cached = _CACHE.get(page_hash)
    if cached is not None:
        return [_with_ref(r, ref) for r in cached]

    reply = (caller or _call_vision)(png_bytes)
    raw_rows = _parse_json_rows(reply) or []
    rows: list[ParsedRow] = []
    for i, obj in enumerate(raw_rows):
        if not isinstance(obj, dict):
            continue
        row = _vision_row_to_parsed(obj, f"{ref};vision_row={i}")
        if row is not None:
            rows.append(row)

    with _CACHE_LOCK:
        _CACHE[page_hash] = rows
    return rows


def _with_ref(row: ParsedRow, ref: str) -> ParsedRow:
    """Copy a cached row, re-tagging its source_ref for the current page."""
    base = (row.source_ref or "").split(";vision_row=")
    suffix = f";vision_row={base[1]}" if len(base) > 1 else ""
    return ParsedRow(
        service_name_raw=row.service_name_raw,
        price_resident=row.price_resident,
        price_nonresident=row.price_nonresident,
        price_original=row.price_original,
        currency=row.currency,
        service_code_source=row.service_code_source,
        source_ref=f"{ref}{suffix}",
        extra=dict(row.extra),
    )


def clear_cache() -> None:
    """Drop the per-page-hash cache (used by tests)."""
    with _CACHE_LOCK:
        _CACHE.clear()
