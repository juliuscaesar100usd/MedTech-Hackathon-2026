"""DOCX parser with tracked-changes acceptance (§4.2).

Word price lists may contain unaccepted revisions. We MUST work with the final
(accepted) text: every <w:del> (deleted content) is removed entirely, and every
<w:ins> (inserted content) is unwrapped so its runs survive. The cleaned XML is
then loaded into python-docx for table + paragraph extraction.
"""
from __future__ import annotations

import zipfile
from io import BytesIO

from docx import Document
from lxml import etree

from ..enums import FileFormat
from .base import BaseParser, ParsedDocument, register_parser
from .pdf_text import extract_header_hints
from .table_extract import rows_from_table

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DOC_XML = "word/document.xml"


def accept_revisions(path: str) -> bytes:
    """Return the .docx bytes with all tracked changes accepted.

    - <w:del>/<w:delText> removed (deletions vanish),
    - <w:ins> unwrapped (insertions kept),
    - move/format-change markers (<w:moveFrom>, <w:rPrChange>...) handled so the
      final text is clean.
    """
    with zipfile.ZipFile(path, "r") as zin:
        names = zin.namelist()
        contents = {n: zin.read(n) for n in names}

    xml = contents.get(_DOC_XML)
    if xml is None:
        return _repack(contents, names)  # not a Word doc body; pass through

    root = etree.fromstring(xml)

    def w(tag: str) -> str:
        return f"{{{_W_NS}}}{tag}"

    # 1) Drop deleted content + move-source content entirely.
    for tag in ("del", "moveFrom"):
        for el in root.findall(f".//{w(tag)}"):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
    # delText/delInstrText that somehow survived outside a <w:del>
    for tag in ("delText", "delInstrText"):
        for el in root.findall(f".//{w(tag)}"):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)

    # 2) Unwrap inserted/moved-in content: replace the wrapper with its children.
    for tag in ("ins", "moveTo"):
        for el in root.findall(f".//{w(tag)}"):
            parent = el.getparent()
            if parent is None:
                continue
            idx = parent.index(el)
            for child in reversed(list(el)):
                parent.insert(idx, child)
            parent.remove(el)

    # 3) Drop format-/property-change tracking markers (keep current props).
    for tag in ("rPrChange", "pPrChange", "tblPrChange", "trPrChange",
                "tcPrChange", "sectPrChange", "numberingChange"):
        for el in root.findall(f".//{w(tag)}"):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)

    contents[_DOC_XML] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    return _repack(contents, names)


def _repack(contents: dict[str, bytes], order: list[str]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in order:
            zout.writestr(name, contents[name])
    return buf.getvalue()


def _table_to_2d(table) -> list[list[str]]:
    return [[cell.text.strip() for cell in row.cells] for row in table.rows]


@register_parser
class DocxParser(BaseParser):
    formats = (FileFormat.docx,)

    def parse(self, file_path: str, file_name: str | None = None) -> ParsedDocument:
        doc = ParsedDocument(file_format=FileFormat.docx)
        try:
            cleaned = accept_revisions(file_path)
            document = Document(BytesIO(cleaned))
        except Exception as exc:
            doc.add_warning(f"DOCX load failed: {exc}")
            return doc

        for tno, table in enumerate(document.tables):
            doc.rows.extend(
                rows_from_table(_table_to_2d(table), source_ref_prefix=f"table={tno + 1}")
            )

        paras = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        doc.raw_text = "\n".join(paras)
        if not doc.rows:
            doc.add_warning("No tables extracted from DOCX.")
        extract_header_hints(doc.raw_text, doc)
        return doc
