"""Portable full-text-ish search over services + partners.

Works identically on SQLite and PostgreSQL. We do candidate selection and
ranking in Python (rapidfuzz + ``str.lower``) rather than relying on DB-side
``LOWER()``/full-text, because SQLite's ``LOWER()`` is ASCII-only and would
silently drop Cyrillic matches. The reference catalog and partner directory are
small enough that an in-memory scan is the simplest portable choice.
"""
from __future__ import annotations

from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Partner, PriceItem, Service
from ..schemas import SearchHitPartner, SearchHitService, SearchResponse

_CAP = 25
# A hit must clear this fuzzy score to be returned (filters out noise).
_MIN_SCORE = 60.0


def _tokens(q: str) -> list[str]:
    return [t for t in q.lower().split() if t]


def _matches_any_token(text: str | None, tokens: list[str]) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(tok in t for tok in tokens)


def _score(query: str, *texts: str | None) -> float:
    """Best fuzzy score across candidate texts, with prefix/exact boosts."""
    q = query.lower().strip()
    if not q:
        return 0.0
    best = 0.0
    for text in texts:
        if not text:
            continue
        t = text.lower()
        base = max(fuzz.token_set_ratio(q, t), fuzz.partial_ratio(q, t))
        if t == q:
            base = 100.0 + 30.0          # exact wins outright
        elif t.startswith(q):
            base = max(base, 100.0 + 15.0)  # prefix boost
        elif q in t:
            base = max(base, 100.0)         # substring boost
        best = max(best, base)
    return best


def search(db: Session, q: str) -> SearchResponse:
    """Search the catalog + partner directory for ``q``."""
    query = (q or "").strip()
    if not query:
        return SearchResponse(query=q or "", services=[], partners=[])

    tokens = _tokens(query)

    # ----------------------------- services --------------------------------- #
    service_hits: list[SearchHitService] = []
    for svc in db.query(Service).filter(Service.is_active.is_(True)).all():
        texts = [svc.service_name, svc.category, *(svc.synonyms or [])]
        # Cheap token gate keeps obviously-irrelevant rows out before scoring.
        if not any(_matches_any_token(str(t), tokens) for t in texts if t):
            # Still allow strong fuzzy hits on the name (typo tolerance).
            if _score(query, svc.service_name) < 90.0:
                continue
        score = _score(query, *texts)
        if score < _MIN_SCORE:
            continue
        agg = (
            db.query(
                func.count(func.distinct(PriceItem.partner_id)),
                func.min(PriceItem.price_resident_kzt),
                func.max(PriceItem.price_resident_kzt),
            )
            .filter(
                PriceItem.service_id == svc.service_id,
                PriceItem.is_active.is_(True),
            )
            .one()
        )
        partner_count = int(agg[0] or 0)
        min_price, max_price = agg[1], agg[2]
        service_hits.append(
            SearchHitService(
                service_id=svc.service_id,
                service_name=svc.service_name,
                category=svc.category,
                partner_count=partner_count,
                min_price_kzt=Decimal(str(min_price)) if min_price is not None else None,
                max_price_kzt=Decimal(str(max_price)) if max_price is not None else None,
                score=round(score, 2),
            )
        )
    service_hits.sort(key=lambda h: h.score, reverse=True)
    service_hits = service_hits[:_CAP]

    # ----------------------------- partners --------------------------------- #
    partner_hits: list[SearchHitPartner] = []
    for p in db.query(Partner).all():
        if not (_matches_any_token(p.name, tokens) or _matches_any_token(p.city, tokens)):
            if _score(query, p.name) < 90.0:
                continue
        score = _score(query, p.name, p.city)
        if score < _MIN_SCORE:
            continue
        service_count = (
            db.query(func.count(func.distinct(PriceItem.service_id)))
            .filter(
                PriceItem.partner_id == p.partner_id,
                PriceItem.is_active.is_(True),
                PriceItem.service_id.isnot(None),
            )
            .scalar()
        )
        partner_hits.append(
            SearchHitPartner(
                partner_id=p.partner_id,
                name=p.name,
                city=p.city,
                service_count=int(service_count or 0),
                score=round(score, 2),
            )
        )
    partner_hits.sort(key=lambda h: h.score, reverse=True)
    partner_hits = partner_hits[:_CAP]

    return SearchResponse(query=query, services=service_hits, partners=partner_hits)
