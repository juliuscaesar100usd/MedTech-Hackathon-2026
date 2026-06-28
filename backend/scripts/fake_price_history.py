"""Seed synthetic price history so every service shows a price-over-time chart.

Most (service, partner) pairs come from a single price list = one effective_date,
so their history chart is empty ("История цен пока отсутствует"). This adds two
older archived versions (is_active=0) at year-1 and year-2 with a realistic trend
(mostly gentle inflation, sometimes a drop) so the chart draws a real-looking line.

ONLY pairs that don't already have ≥2 real dates are touched — genuine history is
left intact. Synthetic points are archived versions, so active counts,
normalization, and verification metrics are unaffected. Demo data, clearly labelled
in code; idempotent-ish (re-running skips pairs that now have ≥2 dates).

    cd backend && PYTHONPATH=. .venv/bin/python -m scripts.fake_price_history
"""
from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.database import SessionLocal, init_db
from app.models import PriceItem

random.seed(1337)  # deterministic


def _scale(value, factor: float):
    if value is None:
        return None
    return (Decimal(value) * Decimal(str(factor))).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        # Existing distinct effective dates per (service, partner).
        dates: dict[tuple, set] = defaultdict(set)
        for sid, pid, eff in db.query(
            PriceItem.service_id, PriceItem.partner_id, PriceItem.effective_date
        ).all():
            if sid and eff:
                dates[(sid, pid)].add(eff)

        active = (
            db.query(PriceItem)
            .filter(
                PriceItem.is_active.is_(True),
                PriceItem.service_id.isnot(None),
                PriceItem.price_resident_kzt.isnot(None),
                PriceItem.effective_date.isnot(None),
            )
            .all()
        )

        added = pairs = 0
        for it in active:
            key = (it.service_id, it.partner_id)
            if len(dates[key]) >= 2:  # already has real history
                continue

            # 80% gentle inflation (older = cheaper), 20% a decline (older = pricier).
            if random.random() < 0.80:
                f1 = random.uniform(0.86, 0.94)          # year-1
                f2 = f1 * random.uniform(0.85, 0.93)     # year-2 (further back, lower)
            else:
                f1 = random.uniform(1.06, 1.16)
                f2 = f1 * random.uniform(1.05, 1.14)

            d = it.effective_date
            made = False
            for yr, f in ((d.year - 2, f2), (d.year - 1, f1)):
                nd = date(yr, 1, 1)
                if nd in dates[key] or nd >= d:
                    continue
                db.add(
                    PriceItem(
                        doc_id=it.doc_id,
                        partner_id=it.partner_id,
                        service_id=it.service_id,
                        service_name_raw=it.service_name_raw,
                        service_code_source=it.service_code_source,
                        section=it.section,
                        section_path=it.section_path,
                        price_resident_kzt=_scale(it.price_resident_kzt, f),
                        price_nonresident_kzt=_scale(it.price_nonresident_kzt, f),
                        currency_original=it.currency_original,
                        fx_rate_to_kzt=it.fx_rate_to_kzt,
                        match_status=it.match_status,
                        match_method=it.match_method,
                        match_confidence=it.match_confidence,
                        is_verified=True,
                        needs_review=False,
                        anomaly_flags=[],
                        effective_date=nd,
                        is_active=False,
                        version=1,
                        created_at=datetime(yr, 1, 1, tzinfo=timezone.utc),
                    )
                )
                dates[key].add(nd)
                added += 1
                made = True
            if made:
                pairs += 1
            if added and added % 4000 == 0:
                db.commit()

        db.commit()
        db.execute(__import__("sqlalchemy").text("PRAGMA wal_checkpoint(TRUNCATE)"))
        total = db.query(PriceItem).count()
        print(
            f"added {added} synthetic history points across {pairs} pairs; "
            f"price_items now {total}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
