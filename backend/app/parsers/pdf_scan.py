"""Image-based (scanned) PDF parser via Tesseract OCR.

Each page is rasterized with PyMuPDF at settings.ocr_dpi, then OCR'd with
pytesseract. Rows are reconstructed from the OCR **word geometry** (TSV boxes):
words are grouped into lines, and within a line they are split into table CELLS
by horizontal gaps. This is what lets us tell a thousands separator ("2 500",
one cell) apart from two distinct price columns ("2 500" | "3 625", two cells) —
information that is lost the moment the words are flattened into a single string.
A regex fallback handles the rare case where TSV data is unavailable.
"""
from __future__ import annotations

import os
import re

import pytesseract
from PIL import Image

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None  # type: ignore

from ..config import settings
from ..enums import Currency, FileFormat
from .base import BaseParser, ParsedDocument, ParsedRow, register_parser
from .ocr_clean import clean_ocr_text
from .pdf_text import extract_header_hints
from .table_extract import parse_price
from .vision_fallback import (
    VISION_DPI,
    extract_rows_via_vision,
    is_low_confidence,
    vision_available,
)

# Lines whose name part starts with one of these are document metadata, not data.
_HEADER_SKIP_RE = re.compile(
    r"^\s*(бин|прайс|адрес|г\.|город|тел|факс|e-?mail|почта|дата|наименование|"
    r"наимен|услуг|цена|стоимост|тариф|резидент|нерезидент|клиник|медицинск|"
    r"центр|лаборатор|стоматолог|№|код)\b",
    re.I,
)
_DATE_RE = re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")

# Trailing-price regex for the text fallback (no geometry available).
_PRICE_TOKEN_RE = re.compile(
    r"[₸$]?\s*\d[\d  .,   ]*\d?(?:\s*(?:₸|тг|тенге|kzt|usd|руб|rub))?",
    re.I,
)
_LINE_PRICE_RE = re.compile(
    r"^(?P<name>.*?\S)\s{2,}(?P<prices>(?:" + _PRICE_TOKEN_RE.pattern + r"\s*){1,3})\s*$",
    re.I,
)


def _ensure_tessdata_env() -> str:
    """Point Tesseract at the bundled traineddata; return the dir for --tessdata-dir."""
    tdir = str(settings.tessdata_prefix)
    os.environ["TESSDATA_PREFIX"] = tdir
    return tdir


def _ocr_string(img: Image.Image, tessdata_dir: str) -> str:
    config = f'--tessdata-dir "{tessdata_dir}"'
    return pytesseract.image_to_string(img, lang=settings.ocr_langs, config=config)


def _digit_count(text: str) -> int:
    return sum(ch.isdigit() for ch in text)


def _price_of(cell: str) -> tuple[float | None, Currency]:
    """Return (value, currency) if the cell is a plausible price, else (None, KZT).

    Rejects dates, BINs/phones and merged blobs (a real per-service price has at
    most 8 digits, i.e. < 100 000 000 KZT).
    """
    cell = cell.strip()
    if not cell or _DATE_RE.search(cell):
        return None, Currency.KZT
    if _digit_count(cell) > 8:
        return None, Currency.KZT
    value, cur = parse_price(cell)
    if value is None or value <= 0:
        return None, Currency.KZT
    return value, cur


def _cells_from_words(words: list[tuple[int, int, str]]) -> list[str]:
    """Split x-sorted (left, width, text) words into table cells by gap size.

    A gap wider than ~2x the average character width is treated as a column
    boundary; smaller gaps (ordinary inter-word / thousands spaces) keep words
    in the same cell.
    """
    if not words:
        return []
    char_widths = [w / max(len(t), 1) for _, w, t in words if t]
    char_w = sorted(char_widths)[len(char_widths) // 2] if char_widths else 10
    threshold = max(2.0 * char_w, 12)

    cells: list[list[str]] = [[words[0][2]]]
    prev_right = words[0][0] + words[0][1]
    for left, width, text in words[1:]:
        gap = left - prev_right
        if gap > threshold:
            cells.append([text])
        else:
            cells[-1].append(text)
        prev_right = left + width
    return [clean_ocr_text(" ".join(c)).strip() for c in cells]


def _row_from_cells(cells: list[str], ref: str) -> ParsedRow | None:
    """Turn one line's cells into a ParsedRow: leading text = name, trailing
    numeric cells = resident / non-resident prices."""
    cells = [c for c in cells if c]
    if not cells:
        return None

    # Collect contiguous trailing price cells.
    prices: list[tuple[float, Currency]] = []
    cut = len(cells)
    for i in range(len(cells) - 1, -1, -1):
        val, cur = _price_of(cells[i])
        if val is None:
            break
        prices.append((val, cur))
        cut = i
    prices.reverse()  # back to document (left-to-right) order
    if not prices:
        return None

    name = " ".join(cells[:cut]).strip(" .:-—|\t")
    if len(name) < 2 or not any(ch.isalpha() for ch in name):
        return None
    if _HEADER_SKIP_RE.match(name):
        return None

    res_price, currency = prices[0]
    nonres_price = prices[1][0] if len(prices) > 1 else None
    return ParsedRow(
        service_name_raw=name,
        price_resident=res_price,
        price_nonresident=nonres_price,
        price_original=res_price,
        currency=currency,
        source_ref=ref,
    )


def _tsv_data(img: Image.Image, tessdata_dir: str) -> dict | None:
    """Run Tesseract's TSV (word-geometry) pass; return the DICT or None."""
    config = f'--tessdata-dir "{tessdata_dir}"'
    try:
        return pytesseract.image_to_data(
            img, lang=settings.ocr_langs, config=config,
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return None


def _rows_from_data(data: dict | None, ref: str) -> list[ParsedRow]:
    """Group OCR words into lines, then split each line into cells by geometry."""
    if not data:
        return []
    n = len(data["text"])
    lines: dict[tuple, list[tuple[int, int, str]]] = {}
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append((data["left"][i], data["width"][i], txt))

    rows: list[ParsedRow] = []
    for key, words in lines.items():
        words.sort(key=lambda w: w[0])
        cells = _cells_from_words(words)
        row = _row_from_cells(cells, f"{ref};line={key[2]}")
        if row is not None:
            rows.append(row)
    return rows


def _render_png(page, dpi: int = VISION_DPI) -> bytes:
    """Rasterize a PDF page to PNG bytes at `dpi` for the vision fallback."""
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return pix.tobytes("png")


def _parse_line(line: str, ref: str) -> ParsedRow | None:
    """Text-fallback: split a line on runs of 2+ spaces into cells."""
    line = line.rstrip()
    if not line.strip():
        return None
    m = _LINE_PRICE_RE.match(line)
    if not m:
        return None
    name = m.group("name").strip(" .:-—")
    prices = _PRICE_TOKEN_RE.findall(m.group("prices"))
    cells = [name] + [p for p in prices if p.strip()]
    return _row_from_cells(cells, ref)


def _rows_from_text(text: str, ref: str) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    for ln, line in enumerate(text.splitlines()):
        row = _parse_line(line, f"{ref};line={ln}")
        if row is not None:
            rows.append(row)
    return rows


@register_parser
class PdfScanParser(BaseParser):
    formats = (FileFormat.scan_pdf,)

    def parse(self, file_path: str, file_name: str | None = None) -> ParsedDocument:
        doc = ParsedDocument(
            file_format=FileFormat.scan_pdf,
            used_ocr=True,
            language=settings.ocr_langs,
        )
        if fitz is None:
            doc.add_warning("PyMuPDF (fitz) unavailable; cannot rasterize scan PDF.")
            return doc

        tessdata_dir = _ensure_tessdata_env()
        zoom = settings.ocr_dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        text_parts: list[str] = []

        try:
            pdf = fitz.open(file_path)
        except Exception as exc:  # pragma: no cover
            doc.add_warning(f"Could not open scan PDF: {exc}")
            return doc

        with pdf:
            for pno, page in enumerate(pdf):
                try:
                    pix = page.get_pixmap(matrix=matrix)
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                except Exception as exc:  # pragma: no cover
                    doc.add_warning(f"Rasterize page {pno + 1} failed: {exc}")
                    continue

                ref = f"page={pno + 1}"
                page_text = clean_ocr_text(_ocr_string(img, tessdata_dir))
                text_parts.append(page_text)

                # Prefer geometry-based TSV reconstruction; fall back to regex.
                data = _tsv_data(img, tessdata_dir)
                page_rows = _rows_from_data(data, ref)
                if not page_rows:
                    page_rows = _rows_from_text(page_text, ref)

                # Fix B: on low-confidence pages (skewed scan / prices detached
                # from names), retry with the Claude vision model. Tesseract stays
                # the default; vision only runs when both the page is weak AND the
                # fallback is configured (anthropic installed + ANTHROPIC_API_KEY).
                low, reason = is_low_confidence(data, page_rows)
                if low:
                    ok, why = vision_available()
                    if ok:
                        try:
                            vrows = extract_rows_via_vision(_render_png(page), ref)
                        except Exception as exc:  # pragma: no cover - network/API
                            doc.add_warning(
                                f"{ref}: vision fallback error ({exc}); kept OCR rows"
                            )
                            vrows = None
                        if vrows:
                            doc.add_warning(
                                f"{ref}: low OCR confidence ({reason}); used Claude "
                                f"vision fallback ({len(vrows)} rows vs "
                                f"{len(page_rows)} OCR)"
                            )
                            page_rows = vrows
                    else:
                        doc.add_warning(
                            f"{ref}: low OCR confidence ({reason}); vision fallback "
                            f"unavailable ({why}) — kept OCR rows"
                        )
                doc.rows.extend(page_rows)

        doc.raw_text = "\n".join(text_parts).strip()
        if not doc.rows:
            doc.add_warning("OCR produced no priced rows.")
        extract_header_hints(doc.raw_text, doc)
        return doc
