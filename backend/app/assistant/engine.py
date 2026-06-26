"""Assistant engine — turns parsed preferences into catalog results + a reply.

Pipeline for one chat turn:

  1. Parse the message into :class:`Preferences` (LLM tier if available, else the
     deterministic rule-based parser; the choice is reported back to the UI).
  2. Resolve the requested city against the partner directory so a price filter
     by city only applies when that city actually exists.
  3. Run the existing portable catalog search to find candidate services /
     partners, then pull each service's active priced offers and apply the
     preference filters (budget, resident vs non-resident, city) + ordering.
  4. Compose a natural-language reply (in the user's language) + follow-up
     suggestions.

The engine reuses the battle-tested :mod:`app.services.search_service` for
candidate selection, so it inherits Cyrillic-safe fuzzy matching for free.
"""
from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Partner, PriceItem, Service
from ..services.search_service import search as catalog_search
from .preferences import parse_preferences
from .schemas import (
    AssistantOffer,
    AssistantPartnerResult,
    AssistantReply,
    AssistantServiceResult,
    ChatRequest,
    Preferences,
)

# Cap how many priced offers we surface per matched service.
_OFFERS_PER_SERVICE = 6


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _resolve_city(db: Session, requested: str | None) -> tuple[str | None, str | None]:
    """Map a requested city onto a real ``Partner.city``.

    Returns ``(resolved_city, note)``. If the requested city has no partners we
    drop the filter and return a note so the UI can explain why.
    """
    if not requested:
        return None, None
    want = requested.strip().lower()
    cities = [c[0] for c in db.query(Partner.city).distinct().all() if c[0]]
    for city in cities:
        if city.lower() == want or want in city.lower() or city.lower() in want:
            return city, None
    return None, f"No partners found in “{requested}” — showing all cities."


def _shown_price(item: PriceItem, resident: str) -> Decimal | None:
    """The price to filter/sort on, given the resident preference."""
    res = _to_decimal(item.price_resident_kzt)
    non = _to_decimal(item.price_nonresident_kzt)
    if resident == "nonresident":
        return non if non is not None else res
    return res if res is not None else non


def _build_offers(
    db: Session,
    prefs: Preferences,
    city: str | None,
    service_ids: set[str] | None = None,
) -> dict[str, list]:
    """For each service id, return its filtered offers (one per partner).

    Scoped to ``service_ids`` (the search hits) so we never scan the full
    price-item table for a single chat turn.
    """
    q = (
        db.query(PriceItem, Partner)
        .join(Partner, PriceItem.partner_id == Partner.partner_id)
        .filter(PriceItem.is_active.is_(True), PriceItem.service_id.isnot(None))
    )
    if service_ids:
        q = q.filter(PriceItem.service_id.in_(list(service_ids)))
    rows = q.all()
    by_service: dict[str, dict[str, AssistantOffer]] = {}
    has_price_filter = prefs.max_price_kzt is not None or prefs.min_price_kzt is not None
    for item, partner in rows:
        if city and (partner.city or "").lower() != city.lower():
            continue
        price = _shown_price(item, prefs.resident)
        if has_price_filter:
            if price is None:
                continue
            if prefs.max_price_kzt is not None and price > prefs.max_price_kzt:
                continue
            if prefs.min_price_kzt is not None and price < prefs.min_price_kzt:
                continue
        offer = AssistantOffer(
            item_id=item.item_id,
            partner_id=partner.partner_id,
            partner_name=partner.name,
            city=partner.city,
            price_resident_kzt=_to_decimal(item.price_resident_kzt),
            price_nonresident_kzt=_to_decimal(item.price_nonresident_kzt),
            price_shown_kzt=price,
            currency_original=str(getattr(item.currency_original, "value", item.currency_original)),
            effective_date=item.effective_date,
            is_verified=bool(item.is_verified),
        )
        bucket = by_service.setdefault(item.service_id, {})
        # Keep one offer per partner — the cheapest on the shown price.
        prev = bucket.get(partner.partner_id)
        if prev is None or (
            price is not None
            and (prev.price_shown_kzt is None or price < prev.price_shown_kzt)
        ):
            bucket[partner.partner_id] = offer
    return {sid: list(offers.values()) for sid, offers in by_service.items()}


def _order_offers(offers: list[AssistantOffer], sort: str) -> list[AssistantOffer]:
    reverse = sort == "expensive"
    return sorted(
        offers,
        key=lambda o: (
            o.price_shown_kzt is None,
            -(o.price_shown_kzt or Decimal(0)) if reverse else (o.price_shown_kzt or Decimal(0)),
        ),
    )


def _service_results(
    db: Session, prefs: Preferences, city: str | None
) -> list[AssistantServiceResult]:
    query = prefs.raw_query or " ".join(prefs.services)
    if not query:
        return []
    hits = catalog_search(db, query).services
    if not hits:
        return []
    sids = {str(h.service_id) for h in hits}
    offers_by_service = _build_offers(db, prefs, city, sids)

    results: list[AssistantServiceResult] = []
    for hit in hits:
        sid = str(hit.service_id)
        offers = _order_offers(offers_by_service.get(sid, []), prefs.sort)
        # The assistant only surfaces services we can actually price — a name
        # match with no (in-budget, in-city) offer isn't an answer.
        if not offers:
            continue
        priced = [o.price_shown_kzt for o in offers if o.price_shown_kzt is not None]
        results.append(
            AssistantServiceResult(
                service_id=sid,
                service_name=hit.service_name,
                category=hit.category,
                partner_count=len(offers),
                best_price_kzt=min(priced) if priced else None,
                min_price_kzt=min(priced) if priced else None,
                max_price_kzt=max(priced) if priced else None,
                offers=offers[:_OFFERS_PER_SERVICE],
                score=hit.score,
                match_reason=_match_reason(offers, prefs),
            )
        )

    # Service ordering: by price when the user asked for cheap/expensive,
    # otherwise by search relevance.
    if prefs.sort == "cheapest":
        results.sort(key=lambda r: (r.best_price_kzt is None, r.best_price_kzt or Decimal(0)))
    elif prefs.sort == "expensive":
        results.sort(key=lambda r: (r.max_price_kzt is None, -(r.max_price_kzt or Decimal(0))))
    else:
        results.sort(key=lambda r: r.score, reverse=True)
    return results[: prefs.limit]


def _match_reason(offers: list[AssistantOffer], prefs: Preferences) -> str:
    n = len(offers)
    if n == 0:
        return "no priced offers"
    word = "clinic" if n == 1 else "clinics"
    priced = [o.price_shown_kzt for o in offers if o.price_shown_kzt is not None]
    if priced:
        return f"{n} {word}, from {int(min(priced))} ₸"
    return f"{n} {word}"


def _partner_results(
    db: Session, prefs: Preferences, city: str | None
) -> list[AssistantPartnerResult]:
    out: list[AssistantPartnerResult] = []
    if city:
        # SQLite LOWER() is ASCII-only, so filter Python-side for Cyrillic safety.
        partners = [p for p in db.query(Partner).all() if (p.city or "").lower() == city.lower()]
        for p in partners:
            count = (
                db.query(func.count(func.distinct(PriceItem.service_id)))
                .filter(
                    PriceItem.partner_id == p.partner_id,
                    PriceItem.is_active.is_(True),
                    PriceItem.service_id.isnot(None),
                )
                .scalar()
            )
            out.append(
                AssistantPartnerResult(
                    partner_id=p.partner_id,
                    name=p.name,
                    city=p.city,
                    service_count=int(count or 0),
                )
            )
        out.sort(key=lambda r: r.service_count, reverse=True)
        return out[: prefs.limit]

    query = prefs.raw_query or " ".join(prefs.services)
    if not query:
        return []
    for hit in catalog_search(db, query).partners[: prefs.limit]:
        out.append(
            AssistantPartnerResult(
                partner_id=str(hit.partner_id),
                name=hit.name,
                city=hit.city,
                service_count=hit.service_count or 0,
                score=hit.score or 0.0,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Natural-language reply                                                        #
# --------------------------------------------------------------------------- #
def _reply_lang(message: str, prefs: Preferences) -> str:
    if prefs.language == "en":
        return "en"
    if prefs.language in ("ru", "kk"):
        return "ru"
    return "en" if len(re.findall(r"[a-z]", message, re.I)) > len(
        re.findall(r"[а-яё]", message, re.I)
    ) else "ru"


def _fmt_kzt(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}".replace(",", " ") + " ₸"


def _compose_reply(
    message: str,
    prefs: Preferences,
    services: list[AssistantServiceResult],
    partners: list[AssistantPartnerResult],
    city_note: str | None,
) -> tuple[str, list[str]]:
    lang = _reply_lang(message, prefs)
    ru = lang == "ru"

    def cons() -> str:
        bits = []
        if prefs.city:
            bits.append(("в " + prefs.city) if ru else ("in " + prefs.city))
        if prefs.max_price_kzt is not None:
            bits.append((f"до {_fmt_kzt(prefs.max_price_kzt)}") if ru else (f"under {_fmt_kzt(prefs.max_price_kzt)}"))
        if prefs.min_price_kzt is not None:
            bits.append((f"от {_fmt_kzt(prefs.min_price_kzt)}") if ru else (f"over {_fmt_kzt(prefs.min_price_kzt)}"))
        if prefs.resident == "nonresident":
            bits.append("для нерезидентов" if ru else "for non-residents")
        elif prefs.resident == "resident":
            bits.append("для резидентов" if ru else "for residents")
        return (", " + ", ".join(bits)) if bits else ""

    suggestions = (
        ["МРТ головного мозга", "УЗИ дешевле 10000", "Клиники в Астане"]
        if ru
        else ["MRI brain", "Blood test under 5000", "Clinics in Almaty"]
    )

    if prefs.intent == "unknown":
        msg = (
            "Опишите услугу и бюджет — например: «анализ крови в Алматы дешевле 5000 ₸»."
            if ru
            else "Tell me the service and budget — e.g. “blood test in Almaty under 5000 ₸”."
        )
        return msg, suggestions

    if prefs.intent == "find_partner":
        if not partners:
            msg = (
                f"Клиник по запросу{cons()} не нашлось."
                if ru
                else f"No clinics found{cons()}."
            )
            return msg, suggestions
        names = ", ".join(p.name for p in partners[:3])
        msg = (
            f"Нашёл {len(partners)} клиник{cons()}: {names}."
            if ru
            else f"Found {len(partners)} clinic(s){cons()}: {names}."
        )
        return msg, suggestions

    # find_service / compare
    q = prefs.raw_query or message
    if not services:
        base = (
            f"По запросу «{q}»{cons()} ничего не нашлось."
            if ru
            else f"Nothing matched “{q}”{cons()}."
        )
        hint = (
            " Попробуйте другой термин или ослабьте ограничение по цене."
            if ru
            else " Try a different term or relax the price limit."
        )
        return base + (city_note or "") + hint, suggestions

    top = services[0]
    best_offer = top.offers[0] if top.offers else None
    if best_offer is not None:
        where = best_offer.partner_name + (f" ({best_offer.city})" if best_offer.city else "")
        price = _fmt_kzt(best_offer.price_shown_kzt)
        if ru:
            msg = (
                f"Нашёл {len(services)} услуг(и) по запросу «{q}»{cons()}. "
                f"Самое выгодное: {top.service_name} — от {price} в «{where}»."
            )
        else:
            msg = (
                f"Found {len(services)} service(s) for “{q}”{cons()}. "
                f"Best value: {top.service_name} — from {price} at {where}."
            )
    else:
        msg = (
            f"Нашёл {len(services)} услуг(и) по запросу «{q}»{cons()}."
            if ru
            else f"Found {len(services)} service(s) for “{q}”{cons()}."
        )
    return msg + (city_note or ""), suggestions


# --------------------------------------------------------------------------- #
# Public entrypoint                                                            #
# --------------------------------------------------------------------------- #
def run_assistant(db: Session, request: ChatRequest, settings) -> AssistantReply:
    """Handle one chat turn end-to-end."""
    max_results = getattr(settings, "assistant_max_results", 5)

    # 1) Parse — LLM tier first (if available), else deterministic rules.
    prefs: Preferences | None = None
    used_llm = False
    try:
        from .llm import parse_preferences_llm  # local import: optional dependency

        prefs = parse_preferences_llm(
            request.message, request.history, settings, max_results=max_results
        )
        used_llm = prefs is not None
    except Exception:
        prefs = None
    if prefs is None:
        # The rule-based parser is the always-on fallback; guard it so no input
        # can ever turn a chat turn into an unhandled 500.
        try:
            prefs = parse_preferences(request.message, max_results=max_results)
        except Exception:
            prefs = Preferences(intent="unknown", raw_query="", limit=max_results)

    # 2) Resolve city against the real partner directory.
    city, city_note = _resolve_city(db, prefs.city)
    if city_note:
        prefs.notes.append(city_note)

    # 3) Query the catalog per the resolved intent.
    services: list[AssistantServiceResult] = []
    partners: list[AssistantPartnerResult] = []
    if prefs.intent in ("find_service", "compare"):
        services = _service_results(db, prefs, city)
        # Surface a handful of partners too when the topic looks partner-ish.
    elif prefs.intent == "find_partner":
        partners = _partner_results(db, prefs, city)

    # 4) Compose the natural-language reply.
    reply, suggestions = _compose_reply(
        request.message, prefs, services, partners, city_note
    )

    return AssistantReply(
        reply=reply,
        preferences=prefs,
        services=services,
        partners=partners,
        used_llm=used_llm,
        parser="llm" if used_llm else "rule_based",
        suggestions=suggestions,
    )
