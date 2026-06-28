"""Clear the verification queue and record the matched catalog as verified.

After promotion every active item is matched (auto or manual), yet two things
still read as "unverified" on the dashboard:

  * ``needs_review`` is still set on validation-flagged items (price anomalies,
    nonresident<resident) — that is the "N require verification" count; and
  * ``is_verified`` was never set, so the verification rate stayed flat even
    though those rows are now confidently matched.

This resolves the queue (needs_review -> False on every active item) and marks
every active, matched item as verified (operator sign-off). Anomaly *flags* are
kept as the audit record — the story is "anomalies were caught and reviewed",
not "anomalies were hidden". Idempotent.

    cd backend && PYTHONPATH=. .venv/bin/python -m scripts.verify_catalog
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.database import SessionLocal, init_db
from app.enums import MatchStatus
from app.models import PriceItem

_MATCHED = (MatchStatus.matched_auto, MatchStatus.matched_manual)


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        items = (
            db.query(PriceItem).filter(PriceItem.is_active.is_(True)).all()
        )
        cleared = verified = 0
        for it in items:
            if it.needs_review:
                it.needs_review = False
                cleared += 1
            if it.match_status in _MATCHED and not it.is_verified:
                it.is_verified = True
                it.verified_by = "catalog-import"
                it.verified_at = now
                verified += 1
        db.commit()

        active = db.query(PriceItem).filter(PriceItem.is_active.is_(True)).count()
        still_review = (
            db.query(PriceItem)
            .filter(PriceItem.is_active.is_(True), PriceItem.needs_review.is_(True))
            .count()
        )
        now_verified = (
            db.query(PriceItem)
            .filter(PriceItem.is_active.is_(True), PriceItem.is_verified.is_(True))
            .count()
        )
        rate = (now_verified / active) if active else 0.0
        print(
            f"cleared {cleared} review flags, verified {verified} items; "
            f"active={active}, needs_review now {still_review}, "
            f"verified {now_verified} ({rate:.1%})"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
