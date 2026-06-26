"""OCR text post-processing.

Tesseract output is noisy: stray whitespace, mixed-script confusions
(O<->0, l/I<->1), and odd glyphs. We normalize whitespace and repair the
*numeric* tokens only, so Cyrillic service names stay intact.
"""
from __future__ import annotations

import re
import unicodedata

# Characters that are visually digits but came out as letters in numeric context.
# Applied ONLY inside tokens we have already decided are numeric.
_DIGIT_FIXES = {
    "O": "0", "o": "0", "О": "0", "о": "0",  # latin/cyrillic O
    "Q": "0",
    "l": "1", "I": "1", "|": "1", "¡": "1",
    "З": "3",  # cyrillic Ze -> 3 (only in numeric tokens)
    "z": "2", "Z": "2",
    "S": "5", "s": "5",
    "B": "8",
    "б": "6",
    "g": "9",
}

# A token that "looks numeric" — mostly digits, possibly with the confusable
# letters above and separators (space/comma/dot). Must contain >=1 real digit.
_NUMERIC_TOKEN_RE = re.compile(
    r"[0-9OoОоQlI|¡ЗzZSsBбg]*[0-9][0-9OoОоQlI|¡ЗzZSsBбg.,  ]*"
)


def _fix_numeric_token(tok: str) -> str:
    """Replace confusable letters with digits inside a numeric-looking token."""
    return "".join(_DIGIT_FIXES.get(ch, ch) for ch in tok)


def _looks_numeric(tok: str) -> bool:
    """True if the token is mostly digits/confusables and holds >=1 real digit."""
    if not any(c.isdigit() for c in tok):
        return False
    relevant = [c for c in tok if not c.isspace() and c not in ".,"]
    if not relevant:
        return False
    digity = sum(1 for c in relevant if c.isdigit() or c in _DIGIT_FIXES)
    return digity / len(relevant) >= 0.6


def fix_numeric_artifacts(text: str) -> str:
    """Repair OCR digit confusions inside numeric tokens, leaving words alone."""
    out: list[str] = []
    for tok in re.split(r"(\s+)", text):
        if tok and not tok.isspace() and _looks_numeric(tok):
            out.append(_fix_numeric_token(tok))
        else:
            out.append(tok)
    return "".join(out)


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces/tabs, trim lines, drop empty leading/trailing lines."""
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        # NBSP / narrow NBSP -> normal space for cleanup; collapse runs.
        line = raw.replace(" ", " ").replace(" ", " ")
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)
    # strip leading/trailing blank lines, collapse 3+ blanks into one
    text = "\n".join(lines).strip("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def clean_ocr_text(text: str) -> str:
    """Full OCR cleanup: unicode-normalize, fix numerics, tidy whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = fix_numeric_artifacts(text)
    text = normalize_whitespace(text)
    return text
