"""Deterministic, fast text normalization for RU/KZ/EN service names.

Used by every layer of the matcher so that exact/synonym dictionaries and the
fuzzy index all agree on a single canonical form.
"""
from __future__ import annotations

import re
import unicodedata

# Keep Latin (a-z), digits and the whole Cyrillic block (U+0400..U+04FF covers
# Russian *and* Kazakh-specific letters: ә ғ қ ң ө ұ ү һ і). Everything else
# (punctuation, symbols, dashes) acts as a token separator.
_TOKEN_RE = re.compile(r"[a-z0-9Ѐ-ӿ]+", re.IGNORECASE)


def normalize(s: str | None) -> str:
    """Lowercase, NFKC-fold, ё->е, drop punctuation, collapse whitespace.

    Returns a canonical string with single spaces between alphanumeric/Cyrillic
    tokens. Non-string / falsy inputs yield an empty string.
    """
    if not s:
        return ""
    # Unicode normalization first so composed/half-width forms unify.
    s = unicodedata.normalize("NFKC", str(s))
    s = s.lower()
    # ё/Ё -> е (the lowercase already happened, handle the combining form too).
    s = s.replace("ё", "е")  # ё -> е
    # Tokenize on the keep-set; this strips punctuation and collapses runs.
    toks = _TOKEN_RE.findall(s)
    return " ".join(toks)


def tokens(s: str | None) -> list[str]:
    """Return the normalized token list (same alphabet rules as ``normalize``)."""
    norm = normalize(s)
    if not norm:
        return []
    return norm.split(" ")
