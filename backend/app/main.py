"""MedArchive REST API — FastAPI application entrypoint.

Hackathon Case 2: a back-office platform that ingests clinic price lists
(PDF/scan/XLSX/DOCX inside ZIP archives), normalizes service names against a
reference catalog, validates + versions prices, and exposes everything for
search, comparison, and operator review.

Mounted under ``settings.api_prefix`` (default ``/api``):
  * services  — catalog browse + per-service partner prices
  * partners  — clinic directory + per-partner price lists
  * search    — unified service/partner search
  * matching  — operator review queue + manual matching
  * admin     — uploads, catalog seeding, documents/batches, verification, dashboard
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .api import (
    auth,
    admin,
    assistant,
    matching,
    partners,
    price_history,
    search,
    services,
)
from .config import settings
from .database import init_db

DESCRIPTION = """
**MedArchive** — automated archive & normalization of clinic price lists
(*MedTech Hackathon 2026, Case 2*).

Upload ZIP archives of partner price lists in any format (text PDF, scanned PDF
with OCR, XLSX, DOCX with tracked changes). The platform parses them, resolves
the partner, **normalizes every service name to a reference catalog**, validates
and **versions prices**, and flags anomalies for human review.

This API powers the back office: full-text **search**, partner/service
**comparison**, the **unmatched / verification** operator queues, manual
**matching**, a live **dashboard**, and an **AI assistant** that turns
free-text preferences ("blood test in Almaty under 5000 ₸") into ranked,
filtered catalog results.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    init_db()
    yield


app = FastAPI(
    title="MedArchive API",
    version="1.0.0",
    description=DESCRIPTION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_prefix = settings.api_prefix
app.include_router(auth.router, prefix=_prefix, tags=["auth"])
app.include_router(services.router, prefix=_prefix, tags=["services"])
app.include_router(partners.router, prefix=_prefix, tags=["partners"])
app.include_router(search.router, prefix=_prefix, tags=["search"])
app.include_router(assistant.router, prefix=_prefix, tags=["assistant"])
app.include_router(matching.router, prefix=_prefix, tags=["matching"])
app.include_router(price_history.router, prefix=_prefix, tags=["price-history"])
app.include_router(admin.router, prefix=_prefix, tags=["admin"])


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get(f"{_prefix}/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
