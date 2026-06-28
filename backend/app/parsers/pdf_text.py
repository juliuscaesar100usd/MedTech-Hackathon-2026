"""Text-based PDF parser (pdfplumber tables + PyMuPDF text fallback).

Also exposes `extract_header_hints`, reused by the OCR scan parser, to pull
partner / city / address / BIN / email / phone / effective-date from the
free-text header at the top of a price list.
"""
from __future__ import annotations

import os
import re
import statistics
from datetime import date
from pathlib import Path

import pdfplumber
from dateutil import parser as dateparser

from ..config import settings
from ..enums import FileFormat
from .base import BaseParser, ParsedDocument, ParsedRow, register_parser
from .table_extract import (
    _CONFUSABLE,
    _CUR_TOKEN_RE,
    _GLYPH_DIGITS,
    SectionHierarchy,
    _section_depth,
    parse_price,
    repair_price_glyphs,
    rows_from_table,
)

try:  # PyMuPDF — used as a text fallback when pdfplumber finds nothing.
    import fitz  # type: ignore
except Exception:  # pragma: no cover - import guard
    fitz = None  # type: ignore


# --------------------------------------------------------------------------- #
# Header-hint regexes.                                                         #
# --------------------------------------------------------------------------- #
_BIN_RE = re.compile(r"\b(?:БИН|ИИН|BIN)\s*[:№#]?\s*(\d{12})\b", re.I)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+7|\b8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b"
)
_PARTNER_KW = (
    "клиник", "центр", "медицин", "тоо", "ао ", "оао", "больниц",
    "госпиталь", "лаборатор", "diagnost", "clinic", "hospital", "медлаб",
    "поликлиник", "стоматолог", "медицинский",
)
_CITY_RE = re.compile(
    r"\b(?:г\.?|город|қала)\s*([А-ЯЁA-Z][а-яёa-z\-]+)", re.I
)
_KNOWN_CITIES = (
    "алматы", "астана", "нур-султан", "нурсултан", "шымкент", "караганда",
    "актобе", "тараз", "павлодар", "усть-каменогорск", "семей", "атырау",
    "костанай", "кызылорда", "уральск", "петропавловск", "актау", "темиртау",
    "туркестан", "кокшетау", "талдыкорган", "экибастуз", "рудный", "жезказган",
)
# Street prefixes: the abbreviations REQUIRE their period (ул. / пр. / мкр.).
# Without it, re.I lets a bare "пр"/"ул" swallow common word-starts in a header
# ("Приложение", "проживающих", "улой…") and store them as a fake address.
_ADDRESS_RE = re.compile(
    r"((?:ул\.|улица|пр\.|проспект|мкр\.|микрорайон|көше|даңғыл)"
    r"[^\n,;]{2,60}(?:[, ]+(?:д\.?|дом|№)?\s*\d+[А-Яа-яA-Za-z/]*)?)",
    re.I,
)
_DATE_PREFIX_RE = re.compile(
    r"(?:прайс[\- ]?лист\s+(?:на|от)|прайс\s+(?:на|от)|действ\w*\s+с|от|на)\s+"
    r"([0-3]?\d[.\-/][01]?\d[.\-/]\d{2,4}|\d{4}[.\-/][01]?\d[.\-/][0-3]?\d)",
    re.I,
)
_BARE_DATE_RE = re.compile(
    r"\b([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}|\d{4}-[01]\d-[0-3]\d)\b"
)


def _first_partner_line(lines: list[str]) -> str | None:
    """Best partner-name guess: a header line with an org keyword, else title."""
    for ln in lines[:25]:
        low = ln.lower()
        if any(k in low for k in _PARTNER_KW) and len(ln) <= 120:
            return ln.strip(" «»\"'")
    # fallback: first non-empty title-ish line (letters present, not too long)
    for ln in lines[:10]:
        s = ln.strip()
        if s and any(ch.isalpha() for ch in s) and len(s) <= 100:
            return s.strip(" «»\"'")
    return None


def _parse_date(s: str) -> date | None:
    for dayfirst in (True, False):
        try:
            return dateparser.parse(s, dayfirst=dayfirst, fuzzy=True).date()
        except (ValueError, OverflowError, TypeError):
            continue
    return None


def extract_header_hints(text: str, doc: ParsedDocument) -> None:
    """Populate doc.*_hint fields from the free-text header `text`."""
    if not text:
        return
    lines = [ln.strip() for ln in text.splitlines()]
    nonempty = [ln for ln in lines if ln]

    if doc.partner_name_hint is None:
        doc.partner_name_hint = _first_partner_line(nonempty)

    head = "\n".join(nonempty[:40])  # search hints only near the top

    if doc.bin_hint is None:
        m = _BIN_RE.search(head)
        if m:
            doc.bin_hint = m.group(1)
    if doc.email_hint is None:
        m = _EMAIL_RE.search(head)
        if m:
            doc.email_hint = m.group(0)
    if doc.phone_hint is None:
        m = _PHONE_RE.search(head)
        if m:
            doc.phone_hint = m.group(0).strip()
    if doc.city_hint is None:
        # Accept a "г./город X" capture ONLY when X is a real KZ city. re.I
        # defeats the capital-letter anchor, so a bare "г" otherwise grabs the
        # next word ("Гражданства" -> "город Ражданства"); whitelisting kills it.
        m = _CITY_RE.search(head)
        if m and m.group(1).lower() in _KNOWN_CITIES:
            doc.city_hint = m.group(1).title()
        else:
            low = head.lower()
            for c in _KNOWN_CITIES:
                if c in low:
                    doc.city_hint = c.title()
                    break
    if doc.address_hint is None:
        m = _ADDRESS_RE.search(head)
        if m:
            doc.address_hint = m.group(1).strip(" ,;")
    if doc.effective_date_hint is None:
        m = _DATE_PREFIX_RE.search(head)
        d = _parse_date(m.group(1)) if m else None
        if d is None:
            m2 = _BARE_DATE_RE.search(head)
            d = _parse_date(m2.group(1)) if m2 else None
        doc.effective_date_hint = d


# --------------------------------------------------------------------------- #
# Word-geometry row extraction (borderless / text-layout PDFs).                #
# --------------------------------------------------------------------------- #
# Many real price lists are laid out with whitespace columns and NO ruled lines,
# so pdfplumber's table detection finds nothing. We reconstruct rows from word
# geometry (PyMuPDF preferred — it decodes broken ToUnicode maps more robustly —
# falling back to pdfplumber words when fitz is unavailable):
#   1. group words into visual lines by y, split each into CELLS at column gaps;
#   2. MERGE an "orphan" price-only line up into the preceding name line (real
#      lists often print the price on its own baseline below the name, which the
#      naive per-line reader dropped — the dominant cause of under-extraction);
#   3. read trailing PRICE-SHAPED cells as prices (repairing digit look-alike
#      glyphs), strip the leading row-index column (by geometry, so real names
#      like "17-ОН прогестерон" survive) and any leading service code;
#   4. carry section banners down so the specialty prior fires on PDFs too.
_PDF_LINE_TOL = 3.0   # words within this vertical distance belong to one line (pt)
_MIN_CELL_GAP = 11.0  # absolute floor for a column-separating gap (pt)
_ORPHAN_MERGE_MAX_DY = 26.0  # max vertical gap to merge an orphan price line (pt)
_INDEX_COL_TOL = 16.0        # a leading int within this of the index column = row №

# A unit-of-measure cell ("1 посещение", "1 процедура", "услуга") — never a price.
_UNIT_CELL_RE = re.compile(
    r"^\s*[1IlОо]?\s*(посещени|услуг|процедур|исследовани|анализ|сеанс|сутк|"
    r"койко[- ]?ден|страниц|шт\.?|штук|манипул|снимок|зуб|поле|точк|курс|набор|"
    r"единиц|комплекс|катетер|ампул|флакон|проб[аы]|пациент|месяц|год|час|раз|"
    r"операци|сегмент|инъекци|уровень|день|кв\.?|пара|доза)\w*\.?\s*$",
    re.I,
)
# A leading service code glued to the name: optional 1-3 letters + digit groups
# with at least one dot/hyphen-joined group ("U1.5", "KR5.3", "B06.127.006",
# "40.080"). The mandatory inner separator keeps lab names like "17-ОН" (letters
# after the hyphen) and "25-ОН витамин Д" safe.
_LEAD_CODE_RE = re.compile(r"^([A-Za-zА-Яа-яЁё]{0,3}\s?\d{1,4}(?:[.\-]\d{1,4})+)\s+(?=\S)")
# A leading pure-numeric lab code (4-6 digits) glued to a name. Real service
# names never start with a 4+ digit run, so this is safe even before a digit-led
# name fragment ("10401 25-ОН витамин Д" -> code 10401 / name "25-ОН витамин Д").
_LEAD_NUMCODE_RE = re.compile(r"^(\d{4,6})\s+(?=\S)")
# A leading row-index integer (1-4 digits) — stripped only when geometry confirms
# the int sits in the far-left index column (see _strip_leading_index).
_LEAD_INDEX_RE = re.compile(r"^(\d{1,4})\s+(?=\S)")
_INT_RE = re.compile(r"\d{1,4}")
# Catalog/lab codes embedded mid-name ("ВОЗ.155.002", "В03.316.002", "Q97.001")
# that the source glues between the name and the price.
_EMBEDDED_CODE_RE = re.compile(
    r"\b(?:В0[0-9]|ВОЗ|Q9[0-9]|СН|B0[0-9])\s*\.\s*\d{2,3}(?:\s*\.\s*\d{2,3})?\b",
    re.I,
)
# PDF section banner lead words (stricter than the shared keyword set, which is
# too greedy for the word-geometry path where real names contain 'прием'/'услуг').
_PDF_SECTION_LEAD_RE = re.compile(
    r"^\s*(раздел|подраздел|категори|блок|глава|часть|отделени|комплекс\s|"
    r"прейскурант|пакет\s+услуг)\b",
    re.I,
)
# A hierarchical section number — "1.", "1.1", "2.2.", "15." — with or without a
# space before the title ("2.2.Выездные услуги"). The mandatory first dot keeps a
# bare row index ("1 Прием") from looking like a heading.
_HIER_NUM_LEAD_RE = re.compile(r"^\s*\d+\.(?:\d+\.?)*\s*[А-Яа-яA-Za-zЁё]")
# A "name" that is only a unit / column-furniture word — the real name was lost
# to wrapping. These are dropped rather than emitted as bogus services.
_FILLER_NAME_RE = re.compile(
    r"^(видеозвонок|консультаци[яи]|операци[яи]|манипуляци[яи]|процедур[аы]|"
    r"посещени[ея]|исследовани[ея]|анализ|сеанс|пакет|услуг[аи]|час|сутки|"
    r"снимок|зуб|койко-день|первичн\w*|повторн\w*|при[её]м)\.?$",
    re.I,
)
# A biospecimen qualifier ('… сыв', '… кровь с ЭДТА') that the lab list prints on
# its own line / after the test name. Stripped from the name tail; a row that is
# ONLY a biospecimen then falls below the min-name length and is dropped.
_BIOSPEC_TRAIL_RE = re.compile(
    r"[\s,]+(сыв\.?|сыворотк[аи]|плазм[аы]|моч[аи]|слюн[аы]|кал|"
    r"кровь(?:\s+с\s+ЭДТА)?|соскоб(?:\s+с)?|капиллярная|венозная)\s*$",
    re.I,
)
# Column-furniture words that sometimes echo at the end of a name.
_ECHO_FURNITURE = {"прием", "приём", "услуга", "услуги", "посещение"}


def _is_unit_cell(text: str) -> bool:
    return bool(_UNIT_CELL_RE.match(text))


def _is_price_shaped(text: str) -> bool:
    """True if `text` is a real price cell (digits/sep/currency only, after glyph
    repair) — so a name cell that merely embeds a number ('до 60 минут') is never
    consumed as a price."""
    rep = repair_price_glyphs(text)
    core = _CUR_TOKEN_RE.sub(" ", rep)
    compact = re.sub(r"[\s.,]", "", core)
    return bool(compact) and compact.isdigit()


def _parse_price_groups(text: str) -> list[float]:
    """Parse one price cell into its distinct prices using thousands grouping.

    The cell is known to be a price position, so EVERY digit look-alike glyph is
    mapped to a digit (incl. pure-glyph groups like 'ООС'->'000', 'II'->'11').
    Then digit groups are folded: a leading 1-3 digit group absorbs each
    following EXACTLY-3-digit group as a thousands run, and anything else starts a
    new price. So '10 800'->[10800], '8 800 II 000'->[8800, 11000],
    '9000 тг 7000 тг'->[9000, 7000], '148 500'->[148500]."""
    mapped = "".join(_GLYPH_DIGITS.get(ch, ch) for ch in _CUR_TOKEN_RE.sub(" ", text))
    out: list[int] = []
    cur: int | None = None
    for tok in re.findall(r"\d+", mapped):
        if cur is None:
            cur = int(tok)
        elif len(tok) == 3:
            cur = cur * 1000 + int(tok)
        else:
            out.append(cur)
            cur = int(tok)
    if cur is not None:
        out.append(cur)
    return [float(v) for v in out if v > 0]


def _prices_in_cell(text: str) -> list[float]:
    """All prices in one cell (thousands-aware, glyph-repaired)."""
    return _parse_price_groups(text)


def _split_trailing_price(name: str) -> tuple[str, list[float]]:
    """Split price(s) glued to the END of a name cell back out.

    Real lists sometimes omit the column gap between the name and its prices, so
    'УЗИ ... сустава 12 ООО' or '... повторный прием 8 800 II 000' arrive as one
    cell. We peel a trailing run of price *fragments* (digits + look-alike
    glyphs) IFF every recovered price is plausible (1000..9,999,999) and a real
    name remains — never touching lab names that end in a code ('CYFRA 21-1',
    'СА 19-9': the hyphen makes them non-fragments)."""
    words = name.split()
    if len(words) < 2:
        return name, []

    def _is_frag(tok: str) -> bool:
        core = _CUR_TOKEN_RE.sub("", tok)
        compact = re.sub(r"[.,]", "", core)
        return bool(compact) and all(
            ch.isdigit() or ch in _CONFUSABLE for ch in compact
        )

    k = len(words)
    while k > 0 and _is_frag(words[k - 1]):
        k -= 1
    if k == len(words) or k == 0:
        return name, []
    head = " ".join(words[:k])
    tail = " ".join(words[k:])
    if sum(ch.isalpha() for ch in head) < 3:
        return name, []
    vals = _parse_price_groups(tail)
    # At most two glued prices (resident / non-resident); each must be plausible.
    if not vals or len(vals) > 2 or not all(1000 <= v <= 9_999_999 for v in vals):
        return name, []
    return head.strip(" .:-—|\t№"), vals


def _strip_leading_code(name: str) -> tuple[str, str | None]:
    """Pull leading service code(s) ('U1.5', '1151', or an OCR-doubled 'U1.1 и
    1.2') off the name, returning the first code found."""
    code: str | None = None
    for _ in range(3):  # peel doubled / OCR-mangled code prefixes
        matched = False
        for rx in (_LEAD_CODE_RE, _LEAD_NUMCODE_RE):
            m = rx.match(name)
            if m:
                rest = name[m.end():].strip()
                if len(rest) >= 3 and any(ch.isalpha() for ch in rest):
                    code = code or m.group(1)
                    name = rest
                    matched = True
                    break
        if not matched:
            break
    # Codes glued mid-name between the title and the price.
    name = _EMBEDDED_CODE_RE.sub(" ", name)
    name = re.sub(r"\s{2,}", " ", name).strip(" .:-—|\t№")
    return name, code


# --------------------------------------------------------------------------- #
# Normalized word model: (x0, top, x1, text) from either fitz or pdfplumber.   #
# --------------------------------------------------------------------------- #
def _fitz_words(page) -> list[tuple[float, float, float, str]]:
    out = []
    for w in page.get_text("words"):
        x0, y0, x1, _y1, txt = w[0], w[1], w[2], w[3], w[4]
        if str(txt).strip():
            out.append((float(x0), float(y0), float(x1), str(txt)))
    return out


def _plumber_words(page) -> list[tuple[float, float, float, str]]:
    try:
        ws = page.extract_words(use_text_flow=False)
    except Exception:
        return []
    return [
        (float(w["x0"]), float(w["top"]), float(w["x1"]), str(w["text"]))
        for w in ws if str(w["text"]).strip()
    ]


def _group_lines(words):
    """Group (x0,top,x1,text) words into visual lines (sorted by y then x)."""
    ws = sorted(words, key=lambda w: (round(w[1], 1), w[0]))
    lines: list[tuple[float, list]] = []
    cur: list = []
    top: float | None = None
    for w in ws:
        if top is None or abs(w[1] - top) <= _PDF_LINE_TOL:
            cur.append(w)
            top = w[1] if top is None else top
        else:
            lines.append((top, cur))
            cur = [w]
            top = w[1]
    if cur:
        lines.append((top, cur))
    return lines


def _split_cells(line_words) -> list[tuple[str, float, float]]:
    """Split one line's words into cells at wide gaps; keep cell x-extent."""
    lw = sorted(line_words, key=lambda w: w[0])
    widths = [(w[2] - w[0]) / max(1, len(w[3])) for w in lw]
    cw = statistics.median(widths) if widths else 6.0
    thr = max(2.2 * cw, _MIN_CELL_GAP)
    cells: list[list] = [[lw[0]]]
    prev_x1 = lw[0][2]
    for w in lw[1:]:
        if w[0] - prev_x1 > thr:
            cells.append([w])
        else:
            cells[-1].append(w)
        prev_x1 = w[2]
    return [
        (" ".join(x[3] for x in c).strip(), c[0][0], c[-1][2]) for c in cells
    ]


def _line_is_price_only(cells) -> bool:
    """A line whose cells are only price/unit fragments (no real name)."""
    real = [c for c in cells if c[0]]
    if not real:
        return False
    if any(any(ch.isalpha() for ch in t) and not _is_unit_cell(t) for t, _, _ in real):
        return False
    return any(_is_price_shaped(t) for t, _, _ in real)


def _index_column_x(celllines) -> float | None:
    """The x0 of the far-left row-index column (min x0 of lines whose first cell
    starts with an integer), or None when there is no index column."""
    xs = [
        cells[0][1]
        for _y, cells in celllines
        if cells and _LEAD_INDEX_RE.match(cells[0][0])
    ]
    return min(xs) if xs else None


def _pdf_section(cells) -> str | None:
    """Strict section-banner detector for the word-geometry path."""
    real = [c for c in cells if c[0]]
    if len(real) != 1:
        return None
    text = real[0][0]
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 3 or len(text) > 70:
        return None
    if _PDF_SECTION_LEAD_RE.match(text) or _HIER_NUM_LEAD_RE.match(text):
        return text.strip(" .:-—|\t№")
    if sum(1 for ch in letters if ch.isupper()) / len(letters) >= 0.7:
        return text.strip(" .:-—|\t№")
    return None


_PDF_INDENT_BUCKET = 18.0  # x0 indentation per nesting level for headers (pt)


def _pdf_header_depth(cells, label: str, left_margin: float) -> int:
    """Rank a section banner's nesting depth from its left-edge indent.

    A header pushed further right (larger x0 vs the page's left margin) nests
    deeper. With no positive indent we fall back to the keyword-class depth.
    """
    real = [c for c in cells if c[0]]
    x0 = real[0][1] if real else left_margin
    bucket = int(round((x0 - left_margin) / _PDF_INDENT_BUCKET))
    return _section_depth(label, bucket if bucket > 0 else None)


def _row_from_cells(cells, ref, section_path, index_x, pending, wrap):
    """Build a ParsedRow from one (orphan-merged) line's cells.

    `pending` is the accumulated name fragment from preceding name-only lines;
    `wrap` is True when a bare row-index line has signalled that the pending name
    continues onto the next priced line (multi-line entries print the index on
    its own baseline between two name fragments). Returns
    ``(row_or_None, new_pending, new_wrap)``.
    """
    cells = [(t.strip(), x0, x1) for (t, x0, x1) in cells if t.strip()]
    if not cells:
        return None, pending, wrap

    first_t, first_x0, _fx1 = cells[0]
    starts_with_index = bool(_LEAD_INDEX_RE.match(first_t)) and (
        index_x is None or first_x0 <= index_x + _INDEX_COL_TOL
    )

    # Trailing price cells (price-shaped; units stop the scan).
    prices: list[float] = []
    cut = len(cells)
    for i in range(len(cells) - 1, -1, -1):
        t = cells[i][0]
        if _is_unit_cell(t) or not _is_price_shaped(t):
            break
        vals = _prices_in_cell(t)
        if not vals:
            break
        prices = vals + prices
        cut = i

    lead = cells[:cut]
    # Assemble the name from the leading cells: drop the index cell (geometry),
    # drop unit cells, keep the rest.
    name_cells: list[str] = []
    for j, (t, x0, _x1) in enumerate(lead):
        if j == 0 and _INT_RE.fullmatch(t) and (
            index_x is None or x0 <= index_x + _INDEX_COL_TOL
        ):
            continue  # row-index column
        if _is_unit_cell(t):
            continue
        name_cells.append(t)
    name = " ".join(name_cells).strip(" .:-—|\t№")
    # A leading integer glued to the name ("680 Прием…") — strip only when that
    # cell physically sits in the index column, so "1 койко-день" survives.
    if name_cells and _LEAD_INDEX_RE.match(name) and lead:
        if index_x is not None and lead[0][1] <= index_x + _INDEX_COL_TOL:
            name = _LEAD_INDEX_RE.sub("", name, count=1).strip()
    # Price(s) glued to the end of the name (no column gap): peel them off and
    # treat them as the leading (resident / non-resident) prices.
    name, glued_prices = _split_trailing_price(name)
    if glued_prices:
        prices = glued_prices + prices
    name, code = _strip_leading_code(name)
    # Drop any leading/trailing currency tokens that leaked into the name and
    # leading list punctuation ('; 32 …', '- …', ': …').
    name = _CUR_TOKEN_RE.sub(" ", name)
    name = re.sub(r"^[\s;:•·\-—,.]+", "", name).strip(" .:-—|\t№")
    name = re.sub(r"\s{2,}", " ", name)
    # Peel trailing biospecimen qualifiers ('Аполипопротеин В сыв' -> '… В').
    for _ in range(2):
        stripped = _BIOSPEC_TRAIL_RE.sub("", name).strip(" .:-—|\t№")
        if stripped == name:
            break
        name = stripped
    # Drop a trailing column-furniture word that merely ECHOES one already in the
    # name ('Прием врача повторный прием' -> 'Прием врача повторный'); only exact
    # duplicates are removed, so a genuine 'Первичный прием' is untouched.
    nw = name.split()
    if len(nw) >= 3 and nw[-1].lower() in _ECHO_FURNITURE:
        if nw[-1].lower() in {w.lower() for w in nw[:-1]}:
            name = " ".join(nw[:-1])

    # A BARE row-index line (just the index, maybe a unit — no name, no price)
    # is a wrap anchor inside a multi-line entry: keep the pending name and tell
    # the next priced line to continue it.
    if starts_with_index and not name and not prices:
        return None, pending, True
    # A line that opens a new numbered row WITH its own name is self-contained and
    # drops any stale pending fragment (so a prior sub-header is never fused on).
    if starts_with_index and name:
        pending = []
        wrap = False

    if not prices:
        # No price here: remember a real name fragment as a continuation for the
        # next priced line; keep the wrap flag so an index between fragments still
        # stitches them.
        if name and len(name) >= 3 and sum(ch.isalpha() for ch in name) >= 3:
            return None, (pending + [name]) if wrap else [name], wrap
        return None, pending, wrap

    # Stitch the pending fragment when the price line continues a wrap, or simply
    # carries no name of its own — never prepend it to an unrelated self-named row.
    if pending and (wrap or not name):
        joined = " ".join(pending)
        name = (joined + " " + name).strip() if name else joined.strip()
    wrap = False
    # Require a real name: at least 3 alphabetic chars (drops bare code fragments
    # like 'U2.1.1' that landed on their own baseline) and not a lone unit word.
    if len(name) < 3 or sum(ch.isalpha() for ch in name) < 3:
        return None, [], False
    if _FILLER_NAME_RE.match(name):
        return None, [], False

    # Drop a leading quantity/row-index that slipped into the price run as a tiny
    # number ('1 5000' -> drop the 1), so resident is the real first price.
    while len(prices) > 1 and prices[0] < 10 <= prices[1]:
        prices.pop(0)
    res = prices[0]
    nonres = prices[1] if len(prices) > 1 else None
    # Reject misparses where the only "price" is a stray index/qty (< 10 KZT).
    if nonres is None and res < 10:
        return None, [], False

    extra: dict = {}
    if section_path:
        extra["section"] = section_path[-1]  # innermost — back-compat
    return (
        ParsedRow(
            service_name_raw=name,
            price_resident=res,
            price_nonresident=nonres,
            price_original=res,
            source_ref=ref,
            service_code_source=code,
            extra=extra,
            section_path=list(section_path),
        ),
        [],
        False,
    )


# --------------------------------------------------------------------------- #
# OCR fallback for pages whose (broken) text layer dropped the price column.    #
# --------------------------------------------------------------------------- #
# Some born-digital price lists have a corrupt/partial text layer: a whole page
# of services renders fine on screen but extracts names with NO prices (the price
# column glyphs decode to nothing). For exactly those pages — detected as "many
# name lines but almost no priced rows" — we rasterize and re-read with Tesseract
# (the visible text), then reuse the same geometry reconstruction. OCR is slow,
# so it fires ONLY on the few broken pages, never on healthy ones.
_OCR_PAGE_DPI = 200


def _name_line_count(words) -> int:
    """How many visual lines carry a real (3+ alpha) service name."""
    n = 0
    for _y, lw in _group_lines(words):
        if any(sum(ch.isalpha() for ch in w[3]) >= 3 for w in lw):
            n += 1
    return n


def _ocr_fallback_enabled() -> bool:
    if os.getenv("OCR_PAGE_FALLBACK", "1").lower() in ("0", "false", "no", "off"):
        return False
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception:
        return False
    tdir = Path(settings.tessdata_prefix)
    return tdir.is_dir() and any(tdir.glob("*.traineddata"))


def _ocr_page_words(page):
    """Rasterize a page and return Tesseract word boxes as normalized words."""
    import pytesseract
    from PIL import Image

    os.environ["TESSDATA_PREFIX"] = str(settings.tessdata_prefix)
    zoom = _OCR_PAGE_DPI / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    cfg = f'--tessdata-dir "{settings.tessdata_prefix}"'
    data = pytesseract.image_to_data(
        img, lang=settings.ocr_langs, config=cfg,
        output_type=pytesseract.Output.DICT,
    )
    sc = 72.0 / _OCR_PAGE_DPI
    out = []
    for i in range(len(data["text"])):
        t = (data["text"][i] or "").strip()
        if t:
            x0 = data["left"][i] * sc
            y0 = data["top"][i] * sc
            x1 = (data["left"][i] + data["width"][i]) * sc
            out.append((x0, y0, x1, t))
    return out


def _rows_from_words(words, ref: str) -> list[ParsedRow]:
    """Reconstruct rows from a page's normalized words."""
    if not words:
        return []
    left_margin = min(w[0] for w in words)
    celllines = [(y, _split_cells(lw)) for y, lw in _group_lines(words)]
    index_x = _index_column_x(celllines)

    # Merge orphan price-only lines up into the nearest preceding name line.
    merged: list[tuple[float, list]] = []
    for y, cells in celllines:
        cells = [c for c in cells if c[0]]
        if not cells:
            continue
        if (merged and _line_is_price_only(cells)
                and (y - merged[-1][0]) <= _ORPHAN_MERGE_MAX_DY
                and not _line_is_price_only(merged[-1][1])):
            merged[-1] = (merged[-1][0], merged[-1][1] + cells)
        else:
            merged.append((y, cells))

    rows: list[ParsedRow] = []
    hierarchy = SectionHierarchy()
    pending: list[str] = []
    wrap = False
    for _y, cells in merged:
        sec = _pdf_section(cells)
        if sec is not None:
            hierarchy.push(sec, _pdf_header_depth(cells, sec, left_margin))
            pending = []
            wrap = False
            continue
        row, pending, wrap = _row_from_cells(
            cells, ref, hierarchy.path(), index_x, pending, wrap
        )
        if row is not None:
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Parser.                                                                      #
# --------------------------------------------------------------------------- #
@register_parser
class PdfTextParser(BaseParser):
    formats = (FileFormat.pdf,)

    def parse(self, file_path: str, file_name: str | None = None) -> ParsedDocument:
        doc = ParsedDocument(file_format=FileFormat.pdf)
        text_parts: list[str] = []
        # Pages that yielded ruled-table rows; the rest go to word-geometry.
        ruled_done: set[int] = set()

        try:
            with pdfplumber.open(file_path) as pdf:
                for pno, page in enumerate(pdf.pages):
                    ptext = page.extract_text() or ""
                    if ptext:
                        text_parts.append(ptext)
                    page_rows: list[ParsedRow] = []
                    for tno, table in enumerate(page.extract_tables() or []):
                        ref = f"page={pno + 1};table={tno + 1}"
                        page_rows.extend(rows_from_table(table, source_ref_prefix=ref))
                    if page_rows:
                        doc.rows.extend(page_rows)
                        ruled_done.add(pno)
                    elif fitz is None:
                        # No fitz: fall back to pdfplumber word geometry.
                        doc.rows.extend(
                            _rows_from_words(
                                _plumber_words(page), ref=f"page={pno + 1}"
                            )
                        )
                        ruled_done.add(pno)
        except Exception as exc:  # pragma: no cover - corrupt/locked PDF
            doc.add_warning(f"pdfplumber failed: {exc}")

        # Borderless pages: reconstruct from PyMuPDF word geometry (clean digits,
        # word boxes) — far more complete than per-line pdfplumber on real lists.
        if fitz is not None:
            ocr_ok = _ocr_fallback_enabled()
            try:
                with fitz.open(file_path) as fdoc:
                    for pno in range(fdoc.page_count):
                        if pno in ruled_done:
                            continue
                        fwords = _fitz_words(fdoc[pno])
                        ref = f"page={pno + 1}"
                        page_rows = _rows_from_words(fwords, ref=ref)
                        # The text layer dropped this page's price column when it
                        # has many service names but almost no priced rows — read
                        # the visible text with OCR and keep whichever is richer.
                        if ocr_ok:
                            n_names = _name_line_count(fwords)
                            if n_names >= 10 and len(page_rows) < max(4, 0.3 * n_names):
                                try:
                                    ocr_rows = _rows_from_words(
                                        _ocr_page_words(fdoc[pno]), ref=f"{ref};ocr"
                                    )
                                except Exception as exc:  # pragma: no cover
                                    ocr_rows = []
                                    doc.add_warning(f"{ref}: OCR fallback error ({exc})")
                                if len(ocr_rows) > len(page_rows):
                                    doc.add_warning(
                                        f"{ref}: text layer dropped prices "
                                        f"({len(page_rows)} rows); used OCR "
                                        f"({len(ocr_rows)} rows)"
                                    )
                                    page_rows = ocr_rows
                        doc.rows.extend(page_rows)
            except Exception as exc:  # pragma: no cover
                doc.add_warning(f"PyMuPDF word geometry failed: {exc}")

        raw_text = "\n".join(text_parts).strip()

        # Fallback to PyMuPDF text if pdfplumber gave us nothing.
        if not raw_text and fitz is not None:
            try:
                with fitz.open(file_path) as fdoc:
                    raw_text = "\n".join(p.get_text() for p in fdoc).strip()
            except Exception as exc:  # pragma: no cover
                doc.add_warning(f"PyMuPDF text fallback failed: {exc}")

        doc.raw_text = raw_text
        if not doc.rows:
            doc.add_warning("No priced rows extracted from PDF (tables or text layout).")
        extract_header_hints(raw_text, doc)
        return doc
