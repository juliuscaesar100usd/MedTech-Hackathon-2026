"""Excel parser for .xlsx (openpyxl) and .xls (pandas) workbooks.

Iterates every sheet. The header row is often not the first row (title/contact
rows precede it), so we scan the top rows with find_header_row before mapping
columns. Each sheet's data rows become ParsedRows tagged with source_ref=sheet.
"""
from __future__ import annotations

from datetime import date, datetime

import openpyxl

from ..enums import FileFormat
from .base import BaseParser, ParsedDocument, register_parser
from .pdf_text import extract_header_hints
from .table_extract import rows_from_table


def _cellval(v: object) -> str:
    """Render an openpyxl/pandas cell value as a trimmed string."""
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


class _BaseExcelParser(BaseParser):
    def _finish(self, doc: ParsedDocument, top_text_parts: list[str]) -> ParsedDocument:
        text = "\n".join(p for p in top_text_parts if p)
        doc.raw_text = text
        extract_header_hints(text, doc)
        if not doc.rows:
            doc.add_warning("No priced rows extracted from workbook.")
        return doc


@register_parser
class XlsxParser(_BaseExcelParser):
    formats = (FileFormat.xlsx, FileFormat.xls)

    def parse(self, file_path: str, file_name: str | None = None) -> ParsedDocument:
        name = (file_name or file_path).lower()
        fmt = FileFormat.xls if name.endswith(".xls") else FileFormat.xlsx
        doc = ParsedDocument(file_format=fmt)
        if fmt is FileFormat.xls:
            return self._parse_xls(file_path, doc)
        return self._parse_xlsx(file_path, doc)

    # ---- .xlsx via openpyxl ------------------------------------------------ #
    def _parse_xlsx(self, file_path: str, doc: ParsedDocument) -> ParsedDocument:
        top_text: list[str] = []
        try:
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        except Exception as exc:
            doc.add_warning(f"openpyxl could not open workbook: {exc}")
            return doc
        try:
            for ws in wb.worksheets:
                table = [
                    [_cellval(c) for c in row]
                    for row in ws.iter_rows(values_only=True)
                ]
                if not table:
                    continue
                top_text.append(ws.title)
                for r in table[:6]:
                    line = " ".join(c for c in r if c)
                    if line:
                        top_text.append(line)
                doc.rows.extend(
                    rows_from_table(table, source_ref_prefix=f"sheet={ws.title}")
                )
        finally:
            wb.close()
        return self._finish(doc, top_text)

    # ---- .xls via pandas --------------------------------------------------- #
    def _parse_xls(self, file_path: str, doc: ParsedDocument) -> ParsedDocument:
        top_text: list[str] = []
        try:
            import pandas as pd  # local import: only needed for legacy .xls
        except Exception as exc:  # pragma: no cover
            doc.add_warning(f"pandas unavailable for .xls: {exc}")
            return doc
        try:
            sheets = pd.read_excel(file_path, sheet_name=None, header=None, dtype=str)
        except Exception as exc:
            doc.add_warning(
                f".xls engine unavailable or read failed ({exc}); install xlrd."
            )
            return doc
        for sheet_name, df in sheets.items():
            table = [[_cellval(v) for v in row] for row in df.values.tolist()]
            if not table:
                continue
            top_text.append(str(sheet_name))
            for r in table[:6]:
                line = " ".join(c for c in r if c)
                if line:
                    top_text.append(line)
            doc.rows.extend(
                rows_from_table(table, source_ref_prefix=f"sheet={sheet_name}")
            )
        return self._finish(doc, top_text)
