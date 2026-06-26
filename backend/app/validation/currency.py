"""Currency conversion to KZT (spec §4.4: 'Currency != KZT -> convert at the
rate on the price date, keep original').

Rates come from ``backend/app/data/fx_rates.json`` (currency -> {date: rate}),
with a ``default`` fallback map. Lookup picks the nearest dated rate <= the price
date for the currency; if none, the earliest known rate; if the currency is
absent, the ``default`` map; finally 1.0.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from ..config import settings
from ..enums import Currency


def _coerce_currency(currency: str | Currency) -> str:
    """Normalize a Currency enum or raw string to its upper-case code."""
    if isinstance(currency, Currency):
        return currency.value
    return str(currency).strip().upper()


@lru_cache(maxsize=4)
def _load_rates(path_str: str) -> dict:
    """Load and cache the fx-rates JSON keyed by its absolute path string."""
    with open(path_str, encoding="utf-8") as fh:
        return json.load(fh)


def _rates_table() -> dict:
    return _load_rates(str(Path(settings.fx_rates_path)))


def _parse_dated_map(raw: dict) -> list[tuple[date, float]]:
    """Turn a {iso-date: rate} map into a sorted list of (date, rate)."""
    out: list[tuple[date, float]] = []
    for key, val in raw.items():
        try:
            out.append((date.fromisoformat(key), float(val)))
        except (ValueError, TypeError):
            continue
    out.sort(key=lambda t: t[0])
    return out


def get_rate(currency: str | Currency, on_date: date | None = None) -> float:
    """Return the currency->KZT rate effective on ``on_date``.

    - KZT always returns 1.0.
    - Otherwise pick the nearest dated rate <= ``on_date`` for the currency;
      if none qualifies, use the earliest dated rate; if the currency is absent
      from the dated table, fall back to the ``default`` map; finally 1.0.
    - ``on_date`` of None uses the ``default`` map directly.
    """
    code = _coerce_currency(currency)
    if code == Currency.KZT.value:
        return 1.0

    table = _rates_table()
    default_map = table.get("default", {}) or {}

    if on_date is None:
        val = default_map.get(code)
        return float(val) if val is not None else 1.0

    dated = table.get(code)
    if isinstance(dated, dict):
        series = _parse_dated_map(dated)
        if series:
            # nearest dated rate <= on_date
            chosen: float | None = None
            for d, rate in series:
                if d <= on_date:
                    chosen = rate
                else:
                    break
            if chosen is not None:
                return chosen
            # none <= on_date -> earliest known
            return series[0][1]

    # currency absent / empty -> default map
    val = default_map.get(code)
    return float(val) if val is not None else 1.0


def convert_to_kzt(
    amount: Decimal | float | int | str | None,
    currency: str | Currency,
    on_date: date | None = None,
) -> tuple[Decimal, float]:
    """Convert ``amount`` in ``currency`` to KZT on ``on_date``.

    Returns ``(kzt_amount_rounded_to_2dp, rate)``. A None amount yields
    ``(Decimal('0.00'), rate)``.
    """
    rate = get_rate(currency, on_date)
    if amount is None:
        return (Decimal("0.00"), rate)
    amt = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    kzt = (amt * Decimal(str(rate))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return (kzt, rate)
