"""Partner resolution + filename-hint extraction.

``resolve_partner`` is the single place that dedups clinics: by BIN when a valid
12-digit БИН is known, otherwise by normalized name. It also backfills empty
contact/location fields on a previously-created partner as later documents
reveal more detail.

``filename_hints`` salvages a clinic name and effective date from the file name
itself (Kazakhstan price lists are routinely named e.g.
``Клиника_Сункар_прайс_2025-01-15.pdf``) — used to fill gaps the document
parser could not.
"""
from __future__ import annotations

import os
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Partner
from ..normalization import normalize

_DEFAULT_PARTNER_NAME = "Неизвестный партнёр"

# Tokens that are clearly *not* part of a clinic's name in a filename.
_NOISE_TOKENS = {
    "прайс", "прайслист", "price", "pricelist",
    "скан", "scan", "правки", "правка", "лист",
    "обновление", "update", "new", "final", "версия", "version",
    "v1", "v2", "v3", "copy", "копия",
    "год", "года", "year",  # trails a year ("прайс 2025 год") — not a clinic name
}

# yyyy-mm-dd / yyyy.mm.dd / yyyy_mm_dd
_DATE_ISO = re.compile(r"(20\d{2})[._-](\d{1,2})[._-](\d{1,2})")
# dd.mm.yyyy / dd-mm-yyyy / dd_mm_yyyy
_DATE_DMY = re.compile(r"(\d{1,2})[._-](\d{1,2})[._-](20\d{2})")
# A bare 4-digit year, the common case in KZ price lists ("Клиника 1 2026.pdf",
# "прайс 2025 год"). Anchored so it never eats a digit out of a longer run. Maps
# to Jan 1 of that year — enough to order yearly price lists on a timeline.
_DATE_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")

_BIN_RE = re.compile(r"\b(\d{12})\b")


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _extract_date(stem: str) -> date | None:
    """Pull the first plausible date out of a filename stem."""
    m = _DATE_ISO.search(stem)
    if m:
        dt = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if dt:
            return dt
    m = _DATE_DMY.search(stem)
    if m:
        dt = _safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if dt:
            return dt
    # Year only ("Клиника 1 2026") -> Jan 1 of that year.
    m = _DATE_YEAR.search(stem)
    if m:
        dt = _safe_date(int(m.group(1)), 1, 1)
        if dt:
            return dt
    return None


def _guess_name(stem: str) -> str | None:
    """Guess a clinic name from a filename stem by stripping noise + dates."""
    # Drop any date substrings (incl. a bare year) so their digits do not survive
    # as a token — otherwise the year would read as a clinic number.
    cleaned = _DATE_ISO.sub(" ", stem)
    cleaned = _DATE_DMY.sub(" ", cleaned)
    cleaned = _DATE_YEAR.sub(" ", cleaned)
    # Split on the common filename separators.
    raw_tokens = re.split(r"[\s._\-]+", cleaned)
    kept: list[str] = []
    for tok in raw_tokens:
        t = tok.strip()
        if not t:
            continue
        if t.lower() in _NOISE_TOKENS:
            continue
        # Drop long numeric leftovers (stray counters), but KEEP a short clinic
        # number ("Клиника 1" vs "Клиника 2" are different partners).
        if t.isdigit() and len(t) > 2:
            continue
        kept.append(t)
    if not kept:
        return None
    name = " ".join(kept).strip()
    return name or None


def filename_hints(file_name: str | None) -> dict:
    """Extract ``{"partner_name", "effective_date"}`` hints from a filename.

    Either value may be ``None`` when nothing could be inferred.
    """
    if not file_name:
        return {"partner_name": None, "effective_date": None}
    stem = os.path.splitext(os.path.basename(file_name))[0]
    return {
        "partner_name": _guess_name(stem),
        "effective_date": _extract_date(stem),
    }


def _valid_bin(value: str | None) -> str | None:
    """Return a clean 12-digit BIN, or None."""
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits if len(digits) == 12 else None


def _backfill(partner: Partner, *, city, address, email, phone, bin_) -> bool:
    """Fill empty partner fields from new hints. Returns True if anything set."""
    changed = False
    if not partner.city and city:
        partner.city = city
        changed = True
    if not partner.address and address:
        partner.address = address
        changed = True
    if not partner.contact_email and email:
        partner.contact_email = email
        changed = True
    if not partner.contact_phone and phone:
        partner.contact_phone = phone
        changed = True
    if not partner.bin and bin_:
        partner.bin = bin_
        changed = True
    return changed


def resolve_partner(
    db: Session,
    *,
    name_hint: str | None,
    city_hint: str | None = None,
    address_hint: str | None = None,
    bin_hint: str | None = None,
    email_hint: str | None = None,
    phone_hint: str | None = None,
) -> Partner:
    """Find or create the :class:`Partner` for a document's hints.

    Dedup priority:
      1. by a valid 12-digit БИН (strongest identity), else
      2. by normalized name.

    On a hit, empty contact/location fields are backfilled from the new hints.
    Commits the session before returning so the partner has a stable id.
    """
    bin_ = _valid_bin(bin_hint)
    name = (name_hint or "").strip() or _DEFAULT_PARTNER_NAME
    name_norm = normalize(name)

    existing: Partner | None = None

    # 1) BIN match (most reliable).
    if bin_:
        existing = db.execute(
            select(Partner).where(Partner.bin == bin_)
        ).scalars().first()

    # 2) Fall back to a normalized-name match.
    if existing is None and name_norm:
        for cand in db.execute(select(Partner)).scalars():
            if normalize(cand.name) == name_norm:
                existing = cand
                break

    if existing is not None:
        if _backfill(
            existing,
            city=city_hint,
            address=address_hint,
            email=email_hint,
            phone=phone_hint,
            bin_=bin_,
        ):
            db.commit()
        return existing

    partner = Partner(
        name=name,
        city=city_hint,
        address=address_hint,
        bin=bin_,
        contact_email=email_hint,
        contact_phone=phone_hint,
        is_active=True,
    )
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner
