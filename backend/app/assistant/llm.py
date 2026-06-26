"""Optional LLM tier — uses Claude to extract preferences from messier input.

This is a STRICT ENHANCEMENT over the deterministic rule-based parser in
:mod:`app.assistant.preferences`. It activates only when both are true:

  * the ``anthropic`` SDK is importable, and
  * an Anthropic API key is configured (``ANTHROPIC_API_KEY`` / settings).

On any problem — SDK missing, no key, network/timeout error, malformed tool
call — :func:`parse_preferences_llm` returns ``None`` and the caller falls back
to the rule-based parser. The whole feature therefore works fully offline; the
LLM only adds robustness for conversational or ambiguous phrasing.

Structured extraction is done with **forced tool use** (``tool_choice`` pinned
to a single ``extract_preferences`` tool with ``strict: true``), which is the
most reliable way to get schema-valid JSON back from the Messages API.
"""
from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation

from .schemas import ChatMessage, Preferences

# JSON-Schema for the forced tool call. Mirrors Preferences (the subset the LLM
# should infer). ``additionalProperties: false`` + ``strict`` guarantee the
# returned ``input`` validates exactly.
_TOOL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["find_service", "find_partner", "compare", "unknown"],
            "description": "What the user wants. 'find_partner' when they ask "
            "about clinics/hospitals rather than a specific service.",
        },
        "raw_query": {
            "type": "string",
            "description": "The core medical service or topic to search for, "
            "in the user's language, stripped of price/city/filler words. "
            "Empty string if the user only asks about clinics in general.",
        },
        "city": {
            "type": "string",
            "description": "City name in Russian if mentioned (e.g. 'Алматы', "
            "'Астана', 'Шымкент'), else empty string.",
        },
        "max_price_kzt": {
            "type": "number",
            "description": "Upper price limit converted to Kazakhstani tenge "
            "(KZT). 0 if no ceiling was stated.",
        },
        "min_price_kzt": {
            "type": "number",
            "description": "Lower price limit in KZT. 0 if none.",
        },
        "resident": {
            "type": "string",
            "enum": ["resident", "nonresident", "any"],
            "description": "Whose price the user cares about.",
        },
        "sort": {
            "type": "string",
            "enum": ["cheapest", "expensive", "relevance"],
            "description": "Preferred ordering of results.",
        },
        "limit": {
            "type": "integer",
            "description": "How many results to show (1-20). Default 5.",
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short human-readable crumbs explaining the parse.",
        },
    },
    "required": [
        "intent", "raw_query", "city", "max_price_kzt", "min_price_kzt",
        "resident", "sort", "limit", "notes",
    ],
}

_SYSTEM = (
    "You convert a user's free-text request about medical services in "
    "Kazakhstan into a structured query. The catalog stores prices in "
    "Kazakhstani tenge (KZT). Always respond by calling the "
    "`extract_preferences` tool. Convert any USD/RUB budget to KZT "
    "(roughly 1 USD = 500 KZT, 1 RUB = 5.5 KZT). Keep `raw_query` short and "
    "in the user's original language. Never invent a city or price that the "
    "user did not state."
)


def llm_available(settings) -> bool:
    """True when the LLM tier can be used (SDK importable + key configured)."""
    if not getattr(settings, "assistant_enabled", True):
        return False
    if not getattr(settings, "assistant_llm_configured", False):
        return False
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    return True


def _coerce_decimal(value) -> Decimal | None:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d > 0 else None


def parse_preferences_llm(
    message: str,
    history: list[ChatMessage] | None,
    settings,
    *,
    max_results: int = 5,
) -> Preferences | None:
    """Parse ``message`` into :class:`Preferences` via Claude, or ``None``.

    Returns ``None`` (never raises) whenever the LLM tier is unavailable or the
    call fails, so the caller can transparently fall back to the rule-based
    parser.
    """
    if not message or not llm_available(settings):
        return None
    try:
        import anthropic
    except Exception:
        return None

    api_key = getattr(settings, "anthropic_api_key", None) or os.environ.get(
        "ANTHROPIC_API_KEY"
    )
    if not api_key:
        return None

    # Build the message list: prior turns (for context) + the new request.
    messages = []
    for turn in (history or [])[-6:]:
        role = "assistant" if turn.role == "assistant" else "user"
        if turn.content:
            messages.append({"role": role, "content": turn.content})
    messages.append({"role": "user", "content": message})

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=getattr(settings, "assistant_model", "claude-opus-4-8"),
            max_tokens=1024,
            system=_SYSTEM,
            tools=[
                {
                    "name": "extract_preferences",
                    "description": "Record the structured query parsed from the "
                    "user's request.",
                    "strict": True,
                    "input_schema": _TOOL_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": "extract_preferences"},
            messages=messages,
        )
    except Exception:
        return None

    data = next(
        (b.input for b in response.content if getattr(b, "type", None) == "tool_use"),
        None,
    )
    if not isinstance(data, dict):
        return None

    try:
        prefs = Preferences(
            intent=data.get("intent") or "find_service",
            raw_query=(data.get("raw_query") or "").strip(),
            city=(data.get("city") or "").strip() or None,
            max_price_kzt=_coerce_decimal(data.get("max_price_kzt")),
            min_price_kzt=_coerce_decimal(data.get("min_price_kzt")),
            resident=data.get("resident") or "any",
            sort=data.get("sort") or "relevance",
            limit=max(1, min(20, int(data.get("limit") or max_results))),
            language=None,
            notes=[str(n) for n in (data.get("notes") or []) if n][:6],
        )
    except Exception:
        return None

    prefs.services = [t for t in prefs.raw_query.lower().split() if len(t) > 1]
    if not prefs.raw_query and prefs.intent == "find_service":
        prefs.intent = "find_partner" if prefs.city else "unknown"
    return prefs
