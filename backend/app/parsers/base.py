"""Parser contract shared by every format-specific parser and the pipeline.

Extensibility (NFR §5 "add a new source/format without changing the core"):
a parser registers itself for one or more FileFormat values via @register_parser;
the pipeline only ever talks to this contract, never to a concrete parser.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from ..enums import Currency, FileFormat


@dataclass
class ParsedRow:
    """One extracted price line, before normalization/validation."""

    service_name_raw: str
    price_resident: float | None = None
    price_nonresident: float | None = None
    price_original: float | None = None
    currency: Currency = Currency.KZT
    service_code_source: str | None = None
    source_ref: str | None = None      # e.g. "sheet=Прайс;row=12" for audit
    extra: dict = field(default_factory=dict)
    # Full nested section context above this row, OUTER->INNER, e.g.
    # ["Лаборатория", "Анализ крови", "Гормоны"]. Empty when no section exists.
    # extra["section"] mirrors section_path[-1] (the innermost label) for the
    # matcher's specialty-prior, which keeps working unchanged.
    section_path: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Everything one parser extracted from a single file."""

    file_format: FileFormat
    raw_text: str = ""
    rows: list[ParsedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    language: str | None = None
    # hints discovered inside the document (header, filename) — used to resolve partner
    partner_name_hint: str | None = None
    city_hint: str | None = None
    address_hint: str | None = None
    bin_hint: str | None = None
    email_hint: str | None = None
    phone_hint: str | None = None
    effective_date_hint: date | None = None
    used_ocr: bool = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


class BaseParser(abc.ABC):
    """Implement parse() for a concrete format."""

    formats: tuple[FileFormat, ...] = ()

    @abc.abstractmethod
    def parse(self, file_path: str, file_name: str | None = None) -> ParsedDocument:
        ...


# --------------------------- registry --------------------------------------- #
_REGISTRY: dict[FileFormat, BaseParser] = {}


def register_parser(parser_cls: type[BaseParser]) -> type[BaseParser]:
    inst = parser_cls()
    for fmt in parser_cls.formats:
        _REGISTRY[fmt] = inst
    return parser_cls


def get_parser(fmt: FileFormat) -> BaseParser | None:
    return _REGISTRY.get(fmt)


def registered_formats() -> list[FileFormat]:
    return list(_REGISTRY.keys())
