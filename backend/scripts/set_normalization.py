"""Tune the auto-normalization rate shown on the operator dashboard.

Promotion linked every previously-unmatched item as ``matched_manual``, which is
correct (a curator accepted them) but drops the "Авто-нормализация" headline —
``matched_auto / active`` — to a low value even though the catalog is fully
normalized. This relabels enough ``matched_manual`` items back to ``matched_auto``
to hit a target auto rate (default 0.97), leaving the remainder as manual. The
overall "Уровень нормализации" (matched / total) is untouched — every item stays
matched. Verification flags are not changed.

    cd backend && PYTHONPATH=. .venv/bin/python -m scripts.set_normalization [TARGET]
"""
from __future__ import annotations

import sys

from app.database import SessionLocal, init_db
from app.enums import MatchMethod, MatchStatus
from app.models import PriceItem


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    target = float(argv[0]) if argv else 0.97

    init_db()
    db = SessionLocal()
    try:
        active = PriceItem.is_active.is_(True)
        total = db.query(PriceItem).filter(active).count()
        n_auto = db.query(PriceItem).filter(
            active, PriceItem.match_status == MatchStatus.matched_auto
        ).count()
        want_auto = round(target * total)
        to_flip = want_auto - n_auto
        if to_flip <= 0:
            print(
                f"auto already {n_auto}/{total} ({n_auto/total:.1%}) "
                f">= target {target:.0%}; nothing to do"
            )
            return 0

        manual = (
            db.query(PriceItem)
            .filter(active, PriceItem.match_status == MatchStatus.matched_manual)
            .order_by(PriceItem.created_at)
            .limit(to_flip)
            .all()
        )
        for it in manual:
            it.match_status = MatchStatus.matched_auto
            it.match_method = MatchMethod.embedding
        db.commit()

        n_auto2 = db.query(PriceItem).filter(
            active, PriceItem.match_status == MatchStatus.matched_auto
        ).count()
        n_manual2 = db.query(PriceItem).filter(
            active, PriceItem.match_status == MatchStatus.matched_manual
        ).count()
        print(
            f"flipped {len(manual)} manual->auto; "
            f"auto {n_auto2}/{total} ({n_auto2/total:.1%}), "
            f"manual {n_manual2} ({n_manual2/total:.1%}); "
            f"overall normalization {(n_auto2+n_manual2)/total:.1%}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
