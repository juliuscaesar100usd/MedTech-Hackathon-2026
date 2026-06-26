"""Pydantic contracts for the AI assistant (chatbot) feature.

The assistant takes a free-text message ("preferences"), extracts a structured
:class:`Preferences` object, queries the catalog, and returns matching results
plus a natural-language reply. These schemas are the request/response contract
shared by the parser, the engine, and the REST router.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# What the user is asking for.
Intent = Literal["find_service", "find_partner", "compare", "unknown"]
# How to order the matching offers.
SortOrder = Literal["cheapest", "expensive", "relevance"]
# Whose price to optimise / display.
ResidentPref = Literal["resident", "nonresident", "any"]


class Preferences(BaseModel):
    """Structured preferences extracted from the user's free-text message.

    Every field is optional/defaulted so both the rule-based and the LLM parser
    can emit a partial-but-valid object. ``raw_query`` is the cleaned service
    topic fed to the catalog search; ``notes`` are human-readable crumbs that
    explain how the text was interpreted (surfaced in the UI for transparency).
    """

    intent: Intent = "find_service"
    services: list[str] = Field(default_factory=list)
    category: str | None = None
    city: str | None = None
    partner: str | None = None
    max_price_kzt: Decimal | None = None
    min_price_kzt: Decimal | None = None
    resident: ResidentPref = "any"
    sort: SortOrder = "relevance"
    limit: int = 5
    language: str | None = None          # "ru" | "kk" | "en"
    raw_query: str = ""                   # cleaned free-text used for catalog search
    notes: list[str] = Field(default_factory=list)


class AssistantOffer(BaseModel):
    """One partner's priced offering for a matched service."""

    item_id: str
    partner_id: str
    partner_name: str
    city: str | None = None
    price_resident_kzt: Decimal | None = None
    price_nonresident_kzt: Decimal | None = None
    # The price the offer was filtered/sorted on (resident or non-resident per
    # the user's preference) — the value the UI should emphasise.
    price_shown_kzt: Decimal | None = None
    currency_original: str = "KZT"
    effective_date: date | None = None
    is_verified: bool = False


class AssistantServiceResult(BaseModel):
    """A matched catalog service plus the offers that fit the preferences."""

    type: Literal["service"] = "service"
    service_id: str | None = None
    service_name: str
    category: str | None = None
    partner_count: int = 0
    best_price_kzt: Decimal | None = None
    min_price_kzt: Decimal | None = None
    max_price_kzt: Decimal | None = None
    offers: list[AssistantOffer] = Field(default_factory=list)
    match_reason: str = ""
    score: float = 0.0


class AssistantPartnerResult(BaseModel):
    """A matched partner clinic (for ``find_partner`` intent)."""

    type: Literal["partner"] = "partner"
    partner_id: str
    name: str
    city: str | None = None
    service_count: int = 0
    score: float = 0.0


class ChatMessage(BaseModel):
    """One turn of conversation history sent by the client."""

    role: Literal["user", "assistant"]
    content: str = Field("", max_length=4000)


class ChatRequest(BaseModel):
    """Request body for ``POST /assistant/chat``.

    ``message`` and ``history`` are length-bounded at the schema boundary so a
    public, unauthenticated endpoint can't be abused with oversized payloads.
    """

    message: str = Field(..., max_length=4000, description="The user's free-text preferences.")
    history: list[ChatMessage] = Field(
        default_factory=list,
        max_length=30,
        description="Prior turns, oldest first (used to enrich LLM parsing).",
    )


class AssistantReply(BaseModel):
    """Response body for ``POST /assistant/chat``."""

    reply: str                                       # natural-language answer
    preferences: Preferences                          # parsed (for transparency)
    services: list[AssistantServiceResult] = Field(default_factory=list)
    partners: list[AssistantPartnerResult] = Field(default_factory=list)
    used_llm: bool = False                            # True if Claude parsed it
    parser: Literal["llm", "rule_based"] = "rule_based"
    suggestions: list[str] = Field(default_factory=list)


class AssistantStatus(BaseModel):
    """Response body for ``GET /assistant/status`` (UI capability probe)."""

    enabled: bool
    llm_available: bool
    model: str
