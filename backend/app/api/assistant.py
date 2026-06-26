"""Assistant router: the AI chatbot endpoint.

``POST /assistant/chat`` takes a free-text message (the user's preferences),
analyses it, and returns matching catalog results plus a natural-language reply.
``GET /assistant/status`` lets the UI probe whether the LLM tier is active.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..assistant import run_assistant
from ..assistant.llm import llm_available
from ..assistant.schemas import AssistantReply, AssistantStatus, ChatRequest
from ..config import settings
from .deps import get_db

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/status", response_model=AssistantStatus)
def assistant_status() -> AssistantStatus:
    """Report whether the assistant is enabled and if the Claude tier is live."""
    return AssistantStatus(
        enabled=bool(settings.assistant_enabled),
        llm_available=llm_available(settings),
        model=settings.assistant_model,
    )


@router.post("/chat", response_model=AssistantReply)
def assistant_chat(payload: ChatRequest, db: Session = Depends(get_db)) -> AssistantReply:
    """Analyse the user's preferences and return the relevant results."""
    return run_assistant(db, payload, settings)
