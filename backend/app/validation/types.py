"""Result type returned by per-row validation (the §4.4 automatic checks)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..enums import Currency


@dataclass
class ValidationOutcome:
    # If True, the row is invalid and must be skipped (e.g. empty service name).
    skip: bool = False
    skip_reason: str | None = None

    # Resolved, KZT-normalized prices (after currency conversion).
    price_resident_kzt: Decimal | None = None
    price_nonresident_kzt: Decimal | None = None
    price_original: Decimal | None = None
    currency_original: Currency = Currency.KZT
    fx_rate_to_kzt: float | None = None

    # Flags raised by the checks.
    needs_review: bool = False
    anomaly_flags: list[str] = field(default_factory=list)  # machine-readable codes
    log_messages: list[str] = field(default_factory=list)   # human-readable log lines

    def add_flag(self, code: str, message: str, *, review: bool = True) -> None:
        if code not in self.anomaly_flags:
            self.anomaly_flags.append(code)
        self.log_messages.append(message)
        if review:
            self.needs_review = True
