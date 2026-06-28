"""Tidy category labels so the catalog reads like a real taxonomy.

Section-derived categories carry price-list noise: enumerations ("23. Услуги
Check up центра", "1.1 Блок хирургии", "Раздел 7.Оториноларингология") and stray
fragments ("НДС)" left from "…(без НДС)"). This strips the leading numbering and,
for labels that are still junk (a fragment / too few letters), re-derives a broad
category from the service name via the same keyword map used elsewhere.

Pure label cleanup — no item is re-matched. Idempotent.

    cd backend && PYTHONPATH=. .venv/bin/python -m scripts.clean_categories
"""
from __future__ import annotations

import re

from app.database import SessionLocal, init_db
from app.models import Service
from scripts.categorize_services import _keyword_category

# Leading enumeration: optional section word, then a 1.2.3-style number run.
_NUMBERING = re.compile(
    r"^\s*(?:раздел|блок|глава|пункт|часть)?\s*№?\s*\d+(?:[.\-/]\d+)*\.?\s*",
    re.I,
)


def _is_junk(label: str) -> bool:
    s = label.strip()
    if s.count(")") > s.count("("):  # unbalanced close paren -> fragment
        return True
    return len(re.findall(r"[А-Яа-яA-Za-z]", s)) < 3  # too few letters


def _clean(label: str, name: str) -> str:
    s = _NUMBERING.sub("", label).strip(" .:-—").strip()
    if not s or _is_junk(s):
        return _keyword_category(name)
    # Sentence-case-ish: keep as-is but normalize internal whitespace.
    return re.sub(r"\s{2,}", " ", s)


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        changed = 0
        for s in db.query(Service).all():
            cur = (s.category or "").strip()
            if not cur:
                continue
            new = _clean(cur, s.service_name or "")
            if new != cur:
                s.category = new
                changed += 1
        db.commit()
        cats = (
            db.query(Service.category)
            .filter(Service.category.isnot(None), Service.category != "")
            .distinct()
            .count()
        )
        print(f"relabeled {changed} services; distinct categories now {cats}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
