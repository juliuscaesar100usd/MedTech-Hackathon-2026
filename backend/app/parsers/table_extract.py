"""Generic 2D-table -> ParsedRow conversion.

Price lists arrive as tables (from pdfplumber, openpyxl, python-docx, OCR).
This module is format-agnostic: given a list[list[str|None]] it
  1. finds the header row by keyword,
  2. maps columns to semantic fields (name / code / resident / non-resident / currency),
  3. parses messy price cells into (float|None, Currency).
"""
from __future__ import annotations

import re

from ..enums import Currency
from .base import ParsedRow

# --------------------------------------------------------------------------- #
# Header keyword vocabularies (lowercased substrings).                         #
# --------------------------------------------------------------------------- #
_NAME_KW = (
    "наименование", "услуг", "название", "анализ", "исследовани",
    "процедур", "манипул", "service", "name", "атауы", "қызмет",
)
_CODE_KW = ("код", "артикул", "code", "коды", "шифр")
# Non-resident must be checked BEFORE resident (both contain "цена" sometimes).
_NONRES_KW = ("нерезидент", "иностран", "non-resident", "nonresident", "non resident")
_RES_KW = (
    "резидент", "цена", "стоимост", "тариф", "прайс", "сумма",
    "price", "cost", "kzt", "тг", "тенге", "бағас", "құны",
)
_CURRENCY_KW = ("валюта", "currency", "валютасы")

# Citizen-tier price columns (organizer .xls format, e.g. Клиника 7):
# РК / граждане РК (resident) vs ближнее / дальнее зарубежье (non-resident tiers).
_TIER_RK_RE = re.compile(r"\bрк\b|(?<!не)резидент|граждан", re.I)
_TIER_NEAR_RE = re.compile(r"ближн", re.I)
_TIER_FAR_RE = re.compile(r"дальн", re.I)

# A full-width section header row ("ПРИЕМ ВРАЧА", "ЛАБОРАТОРНЫЕ ИССЛЕДОВАНИЯ").
_SECTION_HINT_RE = re.compile(
    r"прием|приём|консультац|осмотр|услуг|анализ|исследован|диагностик|"
    r"процедур|манипул|узи|рентген|лаборатор|терап|хирург|стоматолог|кабинет",
    re.I,
)

# --------------------------------------------------------------------------- #
# Price / currency parsing.                                                    #
# --------------------------------------------------------------------------- #
_NULLISH = {
    "", "-", "—", "–", "−", "n/a", "na", "нет", "договорная", "договорной",
    "по запросу", "уточняйте", "x", "х", "*", ".", "..",
}

_CURRENCY_PATTERNS: tuple[tuple[re.Pattern[str], Currency], ...] = (
    (re.compile(r"₸|тенге|тг\.?|kzt", re.I), Currency.KZT),
    (re.compile(r"\$|usd|долл", re.I), Currency.USD),
    (re.compile(r"₽|руб|rub", re.I), Currency.RUB),
)

# A numeric core: digit groups separated by spaces/NBSP/dots/commas.
_NUMBER_RE = re.compile(r"\d[\d\s.,]*\d|\d")


def detect_currency(text: str, default: Currency = Currency.KZT) -> Currency:
    """Map any currency symbol/word found in `text` to a Currency."""
    if not text:
        return default
    for pat, cur in _CURRENCY_PATTERNS:
        if pat.search(text):
            return cur
    return default


def _to_float(num: str) -> float | None:
    """Interpret a numeric substring like '12 000,50' / '12,000.50' / '12000'."""
    s = re.sub(r"\s", "", num)
    if not s:
        return None
    has_comma, has_dot = "," in s, "." in s
    if has_comma and has_dot:
        # The right-most separator is the decimal point.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        # Comma is decimal only if it splits the trailing 1-2 digits.
        frac = s.split(",")[-1]
        if len(frac) in (1, 2) and s.count(",") == 1:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_dot:
        frac = s.split(".")[-1]
        if not (len(frac) in (1, 2) and s.count(".") == 1):
            s = s.replace(".", "")  # thousands grouping, not decimal
    try:
        return float(s)
    except ValueError:
        return None


def parse_price(text: str | None) -> tuple[float | None, Currency]:
    """Robust price parser.

    Handles '12 000', '12000,00', '12 000 ₸', '15 000 тг', '$120', '120 USD',
    and null-ish placeholders ('—'/'-'/'договорная'/'') -> (None, KZT).
    """
    if text is None:
        return None, Currency.KZT
    raw = str(text).strip()
    if raw.lower() in _NULLISH:
        return None, detect_currency(raw)
    currency = detect_currency(raw)
    m = _NUMBER_RE.search(raw)
    if not m:
        return None, currency
    return _to_float(m.group(0)), currency


# --------------------------------------------------------------------------- #
# Header detection + column mapping.                                           #
# --------------------------------------------------------------------------- #
def _cell(s: object) -> str:
    return "" if s is None else str(s).strip()


def _row_score(row: list[object]) -> int:
    """How 'header-like' is this row? Count distinct semantic keywords hit."""
    joined = " ".join(_cell(c).lower() for c in row)
    score = 0
    if any(k in joined for k in _NAME_KW):
        score += 2  # a name column is the strongest signal
    if any(k in joined for k in _RES_KW + _NONRES_KW):
        score += 1
    if any(k in joined for k in _CODE_KW):
        score += 1
    if any(k in joined for k in _CURRENCY_KW):
        score += 1
    return score


def find_header_row(rows: list[list[object]], scan_limit: int = 20) -> int:
    """Return index of the most header-like row within the first `scan_limit`.

    Returns 0 if nothing scores (caller may treat row 0 as header or skip it).
    """
    best_idx, best_score = -1, 0
    for i, row in enumerate(rows[:scan_limit]):
        if not row or not any(_cell(c) for c in row):
            continue
        sc = _row_score(row)
        if sc > best_score:
            best_idx, best_score = i, sc
    return best_idx if best_idx >= 0 else 0


def _map_columns(header: list[object]) -> dict[str, int]:
    """Map semantic field -> column index using header keywords."""
    cells = [_cell(c).lower() for c in header]
    mapping: dict[str, int] = {}

    def assign(field: str, keywords: tuple[str, ...], taken: set[int]) -> None:
        for i, c in enumerate(cells):
            if i in taken:
                continue
            if any(k in c for k in keywords):
                mapping[field] = i
                taken.add(i)
                return

    taken: set[int] = set()
    assign("name", _NAME_KW, taken)
    assign("code", _CODE_KW, taken)
    assign("nonresident", _NONRES_KW, taken)  # before resident
    assign("resident", _RES_KW, taken)
    assign("currency", _CURRENCY_KW, taken)
    return mapping


def _guess_name_column(rows: list[list[object]]) -> int:
    """Pick the column with the longest average text (fallback when no header)."""
    if not rows:
        return 0
    width = max(len(r) for r in rows)
    best_col, best_len = 0, -1.0
    for col in range(width):
        lengths, alpha = [], 0
        for r in rows:
            v = _cell(r[col]) if col < len(r) else ""
            lengths.append(len(v))
            if any(ch.isalpha() for ch in v):
                alpha += 1
        avg = sum(lengths) / len(lengths) if lengths else 0
        if alpha and avg > best_len:
            best_col, best_len = col, avg
    return best_col


def _map_tiers(header: list[object]) -> dict[str, int]:
    """Detect citizen-tier price columns (РК / ближнее / дальнее зарубежье).

    Returns any of keys 'rk'/'near'/'far' -> column index. Only treated as a tier
    layout when a near- or far-abroad column is present, so an ordinary 'Цена'
    column is still handled by the normal resident/non-resident mapping.
    """
    cells = [_cell(c) for c in header]
    rk = near = far = None
    for i, c in enumerate(cells):
        if near is None and _TIER_NEAR_RE.search(c):
            near = i
            continue
        if far is None and _TIER_FAR_RE.search(c):
            far = i
            continue
        if rk is None and _TIER_RK_RE.search(c):
            rk = i
    if near is None and far is None:
        return {}
    tiers: dict[str, int] = {}
    if rk is not None:
        tiers["rk"] = rk
    if near is not None:
        tiers["near"] = near
    if far is not None:
        tiers["far"] = far
    return tiers


def _section_label(row: list[object]) -> str | None:
    """Return the heading text if `row` is a full-width section header, else None.

    A section row has exactly one non-empty cell, no parseable price, and is
    either uppercase-dominant or matches a known section keyword. (Ordinary
    priced rows always have at least name + price cells, so they never qualify.)
    """
    cells = [_cell(c) for c in row]
    nonempty = [c for c in cells if c]
    if len(nonempty) != 1:
        return None
    text = nonempty[0]
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 3:
        return None
    val, _ = parse_price(text)
    if val is not None:
        return None  # it's a value, not a heading
    upper_ratio = sum(1 for ch in letters if ch.isupper()) / len(letters)
    if upper_ratio >= 0.6 or _SECTION_HINT_RE.search(text):
        return text.strip(" .:-—|\t")
    return None


def rows_from_table(
    table: list[list[object]], source_ref_prefix: str = ""
) -> list[ParsedRow]:
    """Convert a 2D table into ParsedRow objects.

    The header row is auto-detected; data rows below it are parsed. If no header
    is found we still extract using a best-guess name column + first numeric cell
    as the price.
    """
    if not table:
        return []
    # Drop fully-empty rows but remember original indices for source_ref.
    indexed = [(i, r) for i, r in enumerate(table) if r and any(_cell(c) for c in r)]
    if not indexed:
        return []
    clean_rows = [r for _, r in indexed]

    hdr_local = find_header_row(clean_rows)
    header = clean_rows[hdr_local]
    mapping = _map_columns(header)
    tiers = _map_tiers(header)
    has_header = bool(mapping) or bool(tiers)

    # Citizen-tier columns (РК / ближнее / дальнее) drive resident/non-resident.
    if tiers:
        if tiers.get("rk") is not None:
            mapping["resident"] = tiers["rk"]
        nonres_col = tiers.get("far")
        if nonres_col is None:
            nonres_col = tiers.get("near")
        if nonres_col is not None:
            mapping["nonresident"] = nonres_col

    if has_header:
        data = indexed[hdr_local + 1:]
        name_col = mapping.get("name")
        if name_col is None:
            name_col = _guess_name_column([r for _, r in data] or clean_rows)
    else:
        data = indexed  # no header -> every row is data
        name_col = _guess_name_column(clean_rows)
        mapping = {}

    prefix = source_ref_prefix.rstrip(";") if source_ref_prefix else ""
    out: list[ParsedRow] = []
    current_section: str | None = None

    for orig_idx, row in data:
        # Section header rows ("ПРИЕМ ВРАЧА") carry their label onto following rows.
        section = _section_label(row)
        if section is not None:
            current_section = section
            continue

        name = _cell(row[name_col]) if name_col < len(row) else ""
        if not name or not any(ch.isalpha() for ch in name):
            continue  # skip rows without a real service name

        code = None
        if "code" in mapping and mapping["code"] < len(row):
            code = _cell(row[mapping["code"]]) or None

        res_price = res_cur = None
        nonres_price = None
        currency = Currency.KZT

        if "resident" in mapping and mapping["resident"] < len(row):
            res_price, res_cur = parse_price(row[mapping["resident"]])
            currency = res_cur
        if "nonresident" in mapping and mapping["nonresident"] < len(row):
            nonres_price, nr_cur = parse_price(row[mapping["nonresident"]])
            if res_price is None:
                currency = nr_cur

        # Explicit currency column overrides symbol-based detection.
        if "currency" in mapping and mapping["currency"] < len(row):
            cur = detect_currency(_cell(row[mapping["currency"]]), default=currency)
            currency = cur

        # No mapped price column (or header-less): take the first numeric cell
        # that is not the name/code column.
        if res_price is None and nonres_price is None:
            skip = {name_col, mapping.get("code", -1)}
            for ci, cell in enumerate(row):
                if ci in skip:
                    continue
                p, c = parse_price(cell)
                if p is not None:
                    res_price, currency = p, c
                    break

        extra: dict = {}
        if current_section:
            extra["section"] = current_section
        # Keep the extra citizen tiers (near/far abroad) so nothing is lost when
        # they collapse onto the single non-resident field.
        if tiers:
            for label, key in (("price_near_abroad", "near"), ("price_far_abroad", "far")):
                ci = tiers.get(key)
                if ci is not None and ci < len(row):
                    tv, _ = parse_price(row[ci])
                    if tv is not None:
                        extra[label] = tv

        ref = f"{prefix};row={orig_idx}" if prefix else f"row={orig_idx}"
        out.append(
            ParsedRow(
                service_name_raw=name,
                price_resident=res_price,
                price_nonresident=nonres_price,
                price_original=res_price if res_price is not None else nonres_price,
                currency=currency,
                service_code_source=code,
                source_ref=ref,
                extra=extra,
            )
        )
    return out
