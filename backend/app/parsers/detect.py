"""File-type detection (magic bytes + extension) and dispatch.

`detect_format` distinguishes the ZIP-based OOXML formats (docx/xlsx) from the
OLE2 legacy .xls and from PDF, and further splits PDFs into text vs scanned by
measuring how much selectable text they contain.
"""
from __future__ import annotations

import os
import zipfile

from ..enums import FileFormat
from .base import ParsedDocument, get_parser

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None  # type: ignore

# Magic-byte signatures.
_PDF_MAGIC = b"%PDF"
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # OLE2 compound file (.xls/.doc)

# Below this avg # of non-space chars per page, treat a PDF as a scan.
_SCAN_TEXT_THRESHOLD = 15


def _read_head(path: str, n: int = 8) -> bytes:
    with open(path, "rb") as f:
        return f.read(n)


def _zip_kind(path: str) -> FileFormat | None:
    """Inspect a ZIP/OOXML container to tell docx from xlsx."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
    except Exception:
        return None
    if "word/document.xml" in names:
        return FileFormat.docx
    if "xl/workbook.xml" in names or any(n.startswith("xl/") for n in names):
        return FileFormat.xlsx
    return None


def _classify_pdf(path: str) -> FileFormat:
    """Text-PDF vs scanned-PDF by average selectable text per page."""
    if fitz is None:
        return FileFormat.pdf  # cannot inspect; assume text
    try:
        with fitz.open(path) as d:
            pages = d.page_count or 1
            total = sum(len("".join(p.get_text().split())) for p in d)
    except Exception:
        return FileFormat.pdf
    return FileFormat.scan_pdf if (total / pages) < _SCAN_TEXT_THRESHOLD else FileFormat.pdf


def detect_format(path: str, filename: str | None = None) -> FileFormat:
    """Return the FileFormat for `path`, using magic bytes first, ext as a tiebreak."""
    ext = os.path.splitext(filename or path)[1].lower()
    try:
        head = _read_head(path)
    except OSError:
        head = b""

    if head.startswith(_PDF_MAGIC):
        return _classify_pdf(path)

    if any(head.startswith(m) for m in _ZIP_MAGIC):
        kind = _zip_kind(path)
        if kind is not None:
            return kind
        if ext == ".docx":
            return FileFormat.docx
        if ext == ".xlsx":
            return FileFormat.xlsx
        return FileFormat.unknown

    if head.startswith(_OLE_MAGIC):
        # OLE2 container: .xls (or legacy .doc which we don't support here).
        return FileFormat.xls if ext != ".doc" else FileFormat.unknown

    # No usable magic — fall back to extension.
    return {
        ".pdf": FileFormat.pdf,
        ".docx": FileFormat.docx,
        ".xlsx": FileFormat.xlsx,
        ".xls": FileFormat.xls,
    }.get(ext, FileFormat.unknown)


def parse_file(path: str, filename: str | None = None) -> ParsedDocument:
    """Detect the format of `path` and dispatch to the registered parser."""
    fmt = detect_format(path, filename)
    parser = get_parser(fmt)
    if parser is None:
        doc = ParsedDocument(file_format=FileFormat.unknown)
        doc.add_warning(f"No parser registered for format '{fmt.value}'.")
        return doc
    return parser.parse(path, filename)
