"""Per-row automatic validation checks (spec §4.4).

``validate_row`` runs every §4.4 check that can be decided from a single row in
isolation. Dedup and the >50% price-anomaly check need the database and live in
``versioning.py``.

Checks implemented here (action on violation):
  * Service name empty            -> SKIP the row + log               (outcome.skip)
  * Price <= 0 / not a number     -> INVALID_PRICE flag + needs_review
  * Non-resident price < resident -> NONRESIDENT_LT_RESIDENT + review
  * Price date in the future      -> FUTURE_DATE flag + log (warning)
  * Currency != KZT               -> convert to KZT on the price date, keep original
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from ..config import Settings
from ..config import settings as default_settings
from ..enums import Currency
from ..parsers.base import ParsedRow
from . import currency as currency_mod
from .types import ValidationOutcome


def _to_decimal(value: object) -> Decimal | None:
    """Best-effort coercion to a Decimal; None for missing/non-numeric input."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # guard: bool is an int subclass
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def _coerce_currency(raw: object) -> Currency:
    if isinstance(raw, Currency):
        return raw
    try:
        return Currency(str(raw).strip().upper())
    except (ValueError, AttributeError):
        return Currency.KZT


def validate_row(
    row: ParsedRow,
    effective_date: date | None,
    settings: Settings | None = None,
) -> ValidationOutcome:
    """Run the in-row §4.4 checks and return a :class:`ValidationOutcome`."""
    _ = settings or default_settings  # reserved for future thresholds
    outcome = ValidationOutcome()

    # --- Service name not empty -> SKIP the row + log ---------------------- #
    name = (row.service_name_raw or "").strip()
    if not name:
        outcome.skip = True
        outcome.skip_reason = "empty_service_name"
        outcome.log_messages.append("Skipped row: empty service name.")
        return outcome

    # --- Currency resolution ---------------------------------------------- #
    cur = _coerce_currency(row.currency)
    outcome.currency_original = cur

    res = _to_decimal(row.price_resident)
    nonres = _to_decimal(row.price_nonresident)
    orig = _to_decimal(row.price_original)

    if cur == Currency.KZT:
        # Prices are already KZT; no conversion, no original kept.
        outcome.price_resident_kzt = res
        outcome.price_nonresident_kzt = nonres
        outcome.fx_rate_to_kzt = 1.0
        outcome.price_original = None
    else:
        # Convert to KZT on the price date, keep the original amount/currency.
        # The "original" amount preserved is price_original if given, else the
        # resident price in the source currency.
        original_amount = orig if orig is not None else res
        outcome.price_original = original_amount

        res_kzt, rate = currency_mod.convert_to_kzt(res, cur, effective_date)
        outcome.price_resident_kzt = res_kzt if res is not None else None
        if nonres is not None:
            nonres_kzt, _ = currency_mod.convert_to_kzt(nonres, cur, effective_date)
            outcome.price_nonresident_kzt = nonres_kzt
        else:
            outcome.price_nonresident_kzt = None
        outcome.fx_rate_to_kzt = rate
        outcome.log_messages.append(
            f"Converted {original_amount} {cur.value} -> "
            f"{outcome.price_resident_kzt} KZT at rate {rate} "
            f"({effective_date or 'default'})."
        )

    # --- Price > 0 and is a number ---------------------------------------- #
    rk = outcome.price_resident_kzt
    if rk is None or rk <= 0:
        outcome.add_flag(
            "INVALID_PRICE",
            f"Invalid resident price: {row.price_resident!r}.",
            review=True,
        )

    # --- Non-resident price >= resident price ----------------------------- #
    if (
        outcome.price_resident_kzt is not None
        and outcome.price_nonresident_kzt is not None
        and outcome.price_nonresident_kzt < outcome.price_resident_kzt
    ):
        outcome.add_flag(
            "NONRESIDENT_LT_RESIDENT",
            (
                f"Non-resident price ({outcome.price_nonresident_kzt}) is lower "
                f"than resident price ({outcome.price_resident_kzt})."
            ),
            review=True,
        )

    # --- Price date not in the future (warning) --------------------------- #
    if effective_date is not None and effective_date > date.today():
        # Spec: warning. Record the flag + log but do not force manual review.
        outcome.add_flag(
            "FUTURE_DATE",
            f"Effective date {effective_date.isoformat()} is in the future.",
            review=False,
        )

    return outcome
