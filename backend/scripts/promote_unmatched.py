"""Promote every UNMATCHED and NEEDS_REVIEW price item into a real catalog service.

Both queues hold genuine services from the partners' price lists that the
matcher couldn't place confidently:

* ``unmatched`` — no catalog match at all (``service_id IS NULL``).
* ``needs_review`` — a gray-zone (0.5–0.85) guess that is almost always WRONG
  ("Кариотипирование" -> "HLA-типирование", "Репозиция костей носа" ->
  "Репатриация"). Confirming those would attach prices to the wrong service, so
  we DISCARD the tentative match and key off the raw name instead.

Each distinct service (by normalized name) becomes one presentable
:class:`Service`; duplicates across clinics collapse into a single entry with
several price offers. If a name already exists in the catalog (e.g. promoted in
an earlier pass), items link to it rather than creating a near-duplicate. The
price-list ``section`` becomes the ``category``. Items are linked as
``matched_manual`` (confidence 1.0) and drop out of the verification queue.

    cd backend && PYTHONPATH=. .venv/bin/python -m scripts.promote_unmatched
"""
from __future__ import annotations

from collections import Counter, defaultdict

from app.database import SessionLocal, init_db
from app.enums import MatchMethod, MatchStatus
from app.ingestion.pipeline import reconcile_active_versions
from app.models import PriceItem, Service
from app.normalization import normalize, seed_services

# Statuses that mean "not yet a trustworthy catalog entry".
_PROMOTE = (MatchStatus.unmatched, MatchStatus.needs_review)


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        items = (
            db.query(PriceItem)
            .filter(PriceItem.match_status.in_(_PROMOTE))
            .all()
        )
        if not items:
            print("nothing to promote (no unmatched / needs_review items)")
            return 0

        # Group by normalized name (merge duplicates across clinics), ignoring
        # any existing — and for needs_review, untrustworthy — service_id.
        groups: dict[str, list[PriceItem]] = defaultdict(list)
        for it in items:
            key = normalize(it.service_name_raw or "")
            if key:
                groups[key].append(it)

        # Existing catalog, keyed by normalized name, so a service promoted in an
        # earlier pass (or already in the seed catalog) is reused, not duplicated.
        norm_to_id: dict[str, str] = {}
        for s in db.query(Service).all():
            norm_to_id.setdefault(normalize(s.service_name), s.service_id)

        chosen_name: dict[str, str] = {}
        new_payloads: list[dict] = []
        for key, its in groups.items():
            name = Counter(
                it.service_name_raw.strip() for it in its
            ).most_common(1)[0][0]
            chosen_name[key] = name
            if key in norm_to_id:
                continue  # link to the existing service below
            sections = Counter(
                (it.section or "").strip() for it in its if (it.section or "").strip()
            )
            category = sections.most_common(1)[0][0] if sections else None
            new_payloads.append({"service_name": name, "category": category})

        created = seed_services(db, new_payloads)
        # Refresh the map so the freshly-created services resolve.
        name_to_id = {s.service_name: s.service_id for s in db.query(Service).all()}

        linked = 0
        for key, its in groups.items():
            sid = norm_to_id.get(key) or name_to_id[chosen_name[key]]
            for it in its:
                it.service_id = sid
                it.match_status = MatchStatus.matched_manual
                it.match_method = MatchMethod.manual
                it.match_confidence = 1.0
                it.needs_review = False
                linked += 1
        db.commit()

        reactivated = reconcile_active_versions(db)

        total_services = db.query(Service).count()
        remaining = (
            db.query(PriceItem)
            .filter(PriceItem.match_status.in_(_PROMOTE))
            .count()
        )
        print(
            f"promoted {linked} items from {len(groups)} groups: "
            f"{created} new services, {len(groups) - created} merged into existing; "
            f"reactivated {reactivated}; catalog now {total_services} services; "
            f"queue remaining {remaining}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
