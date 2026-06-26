"""AI assistant (chatbot) package.

Parses free-text user preferences into a structured query and returns the
relevant catalog results. Offline-first (deterministic rule-based parser) with
an optional Claude tier for messier / conversational input.
"""
from __future__ import annotations

from .engine import run_assistant
from .preferences import parse_preferences
from .schemas import (
    AssistantReply,
    AssistantStatus,
    ChatMessage,
    ChatRequest,
    Preferences,
)

__all__ = [
    "run_assistant",
    "parse_preferences",
    "AssistantReply",
    "AssistantStatus",
    "ChatMessage",
    "ChatRequest",
    "Preferences",
]
