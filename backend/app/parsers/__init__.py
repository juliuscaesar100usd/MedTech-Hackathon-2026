"""MedArchive format parsers.

Importing this package self-registers every concrete parser (via the
@register_parser side effect of importing each module), so the pipeline can
resolve a parser purely through `get_parser(FileFormat)`.
"""
from __future__ import annotations

from ..enums import FileFormat
from .base import (
    BaseParser,
    ParsedDocument,
    ParsedRow,
    get_parser,
    register_parser,
    registered_formats,
)

# Import for self-registration side effects.
from . import docx_parser as docx_parser  # noqa: F401
from . import pdf_scan as pdf_scan  # noqa: F401
from . import pdf_text as pdf_text  # noqa: F401
from . import xlsx_parser as xlsx_parser  # noqa: F401
from .detect import detect_format, parse_file

__all__ = [
    "ParsedDocument",
    "ParsedRow",
    "FileFormat",
    "BaseParser",
    "detect_format",
    "parse_file",
    "get_parser",
    "register_parser",
    "registered_formats",
]
