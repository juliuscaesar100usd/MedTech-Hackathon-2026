"""Promote every UNMATCHED price item into a real catalog service.

Unmatched rows (``service_id IS NULL``) are genuine services from the partners'
price lists that simply weren't in the seed catalog. This backfill turns each
distinct one into a presentable :class:`Service` so it shows on the catalog,
search, and partner pages — with its prices.

Dedup is by normalized name, so the same service across clinics collapses into
ONE catalog entry with several price offers (a real comparison). The price-list
``section`` becomes the service ``category`` for grouping. Items are linked as
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


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        items = (
            db.query(PriceItem)
            .filter(PriceItem.service_id.is_(None))
            .all()
        )
        # Group unmatched items by normalized name (merge duplicates across clinics).
        groups: dict[str, list[PriceItem]] = defaultdict(list)
        for it in items:
            key = normalize(it.service_name_raw or "")
            if key:
                groups[key].append(it)

        # One service per group: the most common raw spelling is the display name,
        # the most common section is the category.
        chosen_name: dict[str, str] = {}
        payloads: list[dict] = []
        for key, its in groups.items():
            name = Counter(
                it.service_name_raw.strip() for it in its
            ).most_common(1)[0][0]
            sections = Counter(
                (it.section or "").strip() for it in its if (it.section or "").strip()
            )
            category = sections.most_common(1)[0][0] if sections else None
            chosen_name[key] = name
            payloads.append({"service_name": name, "category": category})

        created = seed_services(db, payloads)

        name_to_id = {s.service_name: s.service_id for s in db.query(Service).all()}

        linked = 0
        for key, its in groups.items():
            sid = name_to_id[chosen_name[key]]
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
        still_unmatched = (
            db.query(PriceItem).filter(PriceItem.service_id.is_(None)).count()
        )
        print(
            f"promoted: {created} new services from {linked} items "
            f"({len(groups)} groups); reactivated {reactivated}; "
            f"catalog now {total_services} services; "
            f"unmatched remaining {still_unmatched}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
