"""Give every uncategorized service a real category (kill the "Без категории" pile).

A service ends up category-less when neither the seed catalog nor its price-list
rows carried a section. We fill it from the most truthful signal available, in
order:

  A. the most common ``section`` across the service's own price items
     (the real price-list heading it appeared under);
  B. its clinical ``specialty`` (Гинеколог, ЛОР, …) when it has no section;
  C. a keyword read of the service name into a broad medical category, with a
     small honest "Прочие медицинские услуги" remainder for the truly generic.

A→B→C means ~75% are categorized straight from data; only the residue leans on
keywords. Idempotent: only rows with an empty category are touched.

    cd backend && PYTHONPATH=. .venv/bin/python -m scripts.categorize_services
"""
from __future__ import annotations

import re
from collections import Counter

from app.database import SessionLocal, init_db
from app.models import PriceItem, Service

# Tier C — name keyword -> category. First hit wins, so order matters (specific
# before generic). Allergen RAST/ImmunoCAP codes ("f37", "w6", "d201") are caught
# by a regex below since they carry no descriptive word.
_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("Стоматология", ("зуб", "стоматолог", "пломб", "кариес", "пульпит", "коронк", "имплант", "цемент")),
    ("Гинекология и акушерство", ("беремен", "роды", "родов", "гинеколог", "плод", "кольпоскоп", "влагалищ", "шейки матки", "пессари")),
    ("Лучевая диагностика", ("узи", "кт ", "мрт", "рентген", "ренген", "маммограф", "денситометр", "флюорограф", "томограф", "сцинтиграф")),
    ("Функциональная диагностика", ("экг", "ээг", "эхокг", "спиромет", "холтер", "аудиомет", "узд", "доплер", "допплер")),
    ("Хирургия", ("резекц", "эктоми", "ампутац", "иссечение", "удаление", "пластика", "вправлен", "устранение", "лапароскоп", "лапаро", "операц", "шунтирован", "анастомоз", "стом", "дренирован", "биопси", "пункц")),
    ("Процедуры и манипуляции", ("инъекц", "вливание", "введение", "прижигание", "тампон", "перевязк", "катетер", "блокада", "капельниц", "зонд", "промывание", "ванночк")),
    ("Физиотерапия и реабилитация", ("массаж", "реабилитац", "физиотерап", "лфк", "тейпирован", "плазмолифт", "терапия")),
    ("Педиатрия", ("ребенок", "ребёнок", "детск", "педиатр")),
    ("Лабораторная диагностика", ("аллерген", "антите", "иммуноглоб", "ige", "igg", "igm", "кров", "моча", "мочи", "сыворотк", "аминотрансфераза", "глюкоз", "гормон", "анализ", "панель", "посев", "пцр", "маркер", "антиген", "цитолог", "гистолог", "соскоб", "мазок")),
]
# An allergen test code like ", f37" / "w6" / "d201" / "i8" / "rPhl p 5".
_ALLERGEN_CODE = re.compile(r"\b[a-z]{1,4}\s?\d{1,3}\b", re.I)
_FALLBACK = "Прочие медицинские услуги"


def _keyword_category(name: str) -> str:
    low = name.lower()
    for cat, words in _KEYWORDS:
        if any(w in low for w in words):
            return cat
    if _ALLERGEN_CODE.search(name):
        return "Лабораторная диагностика"
    return _FALLBACK


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        services = [
            s for s in db.query(Service).all()
            if not (s.category or "").strip()
        ]
        if not services:
            print("nothing to do — every service already has a category")
            return 0

        # Pre-load the two data signals in bulk.
        ids = [s.service_id for s in services]
        sections: dict[str, Counter] = {sid: Counter() for sid in ids}
        for it in db.query(PriceItem).filter(PriceItem.service_id.in_(ids)).all():
            sec = (it.section or "").strip()
            if sec:
                sections[it.service_id][sec] += 1
        specialties: dict[str, Counter] = {sid: Counter() for sid in ids}
        from app.models import ServiceSpecialty  # local import: optional table
        for ss in db.query(ServiceSpecialty).filter(
            ServiceSpecialty.service_id.in_(ids)
        ).all():
            sp = (ss.specialty or "").strip()
            if sp:
                specialties[ss.service_id][sp] += 1

        tally = Counter()
        for s in services:
            if sections[s.service_id]:
                s.category = sections[s.service_id].most_common(1)[0][0]
                tally["A:section"] += 1
            elif specialties[s.service_id]:
                s.category = specialties[s.service_id].most_common(1)[0][0]
                tally["B:specialty"] += 1
            else:
                cat = _keyword_category(s.service_name or "")
                s.category = cat
                tally["C:fallback" if cat == _FALLBACK else "C:keyword"] += 1
        db.commit()

        still = db.query(Service).filter(
            (Service.category.is_(None)) | (Service.category == "")
        ).count()
        cats = db.query(Service.category).filter(
            Service.category.isnot(None), Service.category != ""
        ).distinct().count()
        print(
            "categorized "
            + ", ".join(f"{k}={v}" for k, v in sorted(tally.items()))
            + f"; uncategorized now {still}; distinct categories {cats}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
