"""Text-based PDF parser (pdfplumber tables + PyMuPDF text fallback).

Also exposes `extract_header_hints`, reused by the OCR scan parser, to pull
partner / city / address / BIN / email / phone / effective-date from the
free-text header at the top of a price list.
"""
from __future__ import annotations

import re
from datetime import date

import pdfplumber
from dateutil import parser as dateparser

from ..enums import FileFormat
from .base import BaseParser, ParsedDocument, register_parser
from .table_extract import rows_from_table

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
                    for tno, table in enumerate(page.extract_tables() or []):
                        ref = f"page={pno + 1};table={tno + 1}"
                        doc.rows.extend(rows_from_table(table, source_ref_prefix=ref))
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
            doc.add_warning("No tables extracted from PDF.")
        extract_header_hints(raw_text, doc)
        return doc
