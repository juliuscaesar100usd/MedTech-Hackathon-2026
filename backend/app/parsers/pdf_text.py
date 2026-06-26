"""Text-based PDF parser (pdfplumber tables + PyMuPDF text fallback).

Also exposes `extract_header_hints`, reused by the OCR scan parser, to pull
partner / city / address / BIN / email / phone / effective-date from the
free-text header at the top of a price list.
"""
from __future__ import annotations

import re
import statistics
from datetime import date

import pdfplumber
from dateutil import parser as dateparser

from ..enums import FileFormat
from .base import BaseParser, ParsedDocument, ParsedRow, register_parser
from .table_extract import _section_label, parse_price, rows_from_table

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
_ADDRESS_RE = re.compile(
    r"((?:ул\.?|улица|пр\.?|проспект|мкр\.?|микрорайон|көше|даңғыл)"
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
        m = _CITY_RE.search(head)
        if m:
            doc.city_hint = m.group(1)
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
# Many real price lists are laid out with whitespace columns and NO ruled
# lines, so pdfplumber's table detection (which keys on lines/rects) finds
# nothing. We then reconstruct rows from word geometry: group words into visual
# lines, split each line into CELLS at wide horizontal gaps (so "2 500" stays one
# cell but "2 500    3 625" splits into two price columns), and read the trailing
# numeric cells as prices. Section headers carry down via _section_label so the
# specialty prior fires on PDFs too.
_PDF_LINE_TOL = 3.0   # words within this vertical distance belong to one line (pt)
_MIN_CELL_GAP = 11.0  # absolute floor for a column-separating gap (pt)


def _pdf_lines(words: list[dict]) -> list[list[dict]]:
    ws = sorted(words, key=lambda w: (round(float(w["top"]), 1), float(w["x0"])))
    lines: list[list[dict]] = []
    cur: list[dict] = []
    top: float | None = None
    for w in ws:
        t = float(w["top"])
        if top is None or abs(t - top) <= _PDF_LINE_TOL:
            cur.append(w)
            if top is None:
                top = t
        else:
            lines.append(cur)
            cur = [w]
            top = t
    if cur:
        lines.append(cur)
    return lines


def _cells_by_gap(line: list[dict]) -> list[str]:
    line = sorted(line, key=lambda w: float(w["x0"]))
    widths = [(float(w["x1"]) - float(w["x0"])) / max(1, len(w["text"])) for w in line]
    cw = statistics.median(widths) if widths else 6.0
    thr = max(2.2 * cw, _MIN_CELL_GAP)
    cells: list[str] = []
    cur = [line[0]["text"]]
    prev_x1 = float(line[0]["x1"])
    for w in line[1:]:
        if float(w["x0"]) - prev_x1 > thr:
            cells.append(" ".join(cur))
            cur = [w["text"]]
        else:
            cur.append(w["text"])
        prev_x1 = float(w["x1"])
    cells.append(" ".join(cur))
    return cells


def _row_from_line(cells: list[str], ref: str, section: str | None) -> ParsedRow | None:
    cells = [c.strip() for c in cells if c.strip()]
    if not cells:
        return None
    prices: list[tuple[float, object]] = []
    cut = len(cells)
    for i in range(len(cells) - 1, -1, -1):
        val, cur = parse_price(cells[i])
        if val is None or val <= 0:
            break
        prices.append((val, cur))
        cut = i
    if not prices:
        return None
    name = " ".join(cells[:cut]).strip(" .:-—|\t")
    if len(name) < 3 or not any(ch.isalpha() for ch in name):
        return None
    prices.reverse()
    # Drop a leading qty / row-index column (a tiny integer) when a real price
    # follows it, so "Приём врача  1  1080" -> price 1080, not resident=1.
    while len(prices) > 1 and prices[0][0] < 10 <= prices[1][0]:
        prices.pop(0)
    res, currency = prices[0]
    nonres = prices[1][0] if len(prices) > 1 else None
    return ParsedRow(
        service_name_raw=name,
        price_resident=res,
        price_nonresident=nonres,
        price_original=res,
        currency=currency,  # type: ignore[arg-type]
        source_ref=ref,
        extra={"section": section} if section else {},
    )


def _rows_from_pdf_words(page, ref: str) -> list[ParsedRow]:
    try:
        words = page.extract_words(use_text_flow=False)
    except Exception:
        return []
    rows: list[ParsedRow] = []
    section: str | None = None
    for line in _pdf_lines(words):
        cells = _cells_by_gap(line)
        sec = _section_label(cells)
        if sec is not None:
            section = sec
            continue
        row = _row_from_line(cells, ref, section)
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
                    # Borderless / text-layout page (no ruled table found):
                    # reconstruct rows from word geometry.
                    if not page_rows:
                        page_rows = _rows_from_pdf_words(page, ref=f"page={pno + 1}")
                    doc.rows.extend(page_rows)
        except Exception as exc:  # pragma: no cover - corrupt/locked PDF
            doc.add_warning(f"pdfplumber failed: {exc}")

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
