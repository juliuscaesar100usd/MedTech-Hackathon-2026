"""Generate the processing-quality report (ТЗ §7).

Reads the populated database, measures extraction timing per format (NFR §5),
prints a summary and writes docs/REPORT.md. Run AFTER bootstrap_demo / run_ingest.

    python -m scripts.quality_report
"""
from __future__ import annotations

import os
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.enums import FileFormat, MatchStatus, ParseStatus
from app.models import Partner, PriceDocument, PriceItem, Service
from app.parsers import detect_format, parse_file

REPORT_PATH = Path(settings.fx_rates_path).parents[2].parent / "docs" / "REPORT.md"
SAMPLE_ARCHIVE = Path(settings.data_dir).parent / "sample_data" / "archive.zip"


def _measure_extraction_timing() -> dict:
    """Time parse_file per file in the sample archive (extraction is the NFR cost)."""
    results: list[tuple[str, FileFormat, int, float]] = []
    if not SAMPLE_ARCHIVE.exists():
        return {"results": results}
    import tempfile

    with zipfile.ZipFile(SAMPLE_ARCHIVE) as z, tempfile.TemporaryDirectory() as tmp:
        for name in z.namelist():
            if name.endswith("/"):
                continue
            p = os.path.join(tmp, os.path.basename(name))
            with open(p, "wb") as f:
                f.write(z.read(name))
            fmt = detect_format(p, os.path.basename(name))
            if fmt == FileFormat.unknown:
                continue
            t = time.time()
            doc = parse_file(p, os.path.basename(name))
            dt = time.time() - t
            results.append((os.path.basename(name), fmt, len(doc.rows), dt))
    return {"results": results}


def collect() -> dict:
    db = SessionLocal()
    try:
        docs = db.query(PriceDocument).all()
        partners = db.query(Partner).all()
        services = db.query(Service).all()
        all_items = db.query(PriceItem).all()
        active = [i for i in all_items if i.is_active]

        by_format = Counter(d.file_format for d in docs)
        by_status = Counter(d.parse_status for d in docs)

        per_format_items: dict = defaultdict(lambda: {"docs": 0, "items": 0, "matched": 0})
        for d in docs:
            per_format_items[d.file_format]["docs"] += 1
        for i in active:
            d = next((x for x in docs if x.doc_id == i.doc_id), None)
            fmt = d.file_format if d else FileFormat.unknown
            per_format_items[fmt]["items"] += 1
            if i.match_status in (MatchStatus.matched_auto, MatchStatus.matched_manual):
                per_format_items[fmt]["matched"] += 1

        ms = Counter(i.match_status for i in active)
        total = len(active) or 1
        matched = ms[MatchStatus.matched_auto] + ms[MatchStatus.matched_manual]

        flag_counter: Counter = Counter()
        for i in active:
            for fl in (i.anomaly_flags or []):
                flag_counter[fl] += 1

        # Versioning example: a service line with >1 version for the same partner.
        version_chains: dict = defaultdict(list)
        for i in all_items:
            version_chains[(i.partner_id, i.service_name_raw)].append(i)
        history_examples = [
            sorted(v, key=lambda x: (x.version, str(x.effective_date)))
            for k, v in version_chains.items()
            if len(v) > 1
        ]

        currency_examples = [
            i for i in active if i.currency_original and i.currency_original != "KZT"
        ][:5]

        unmatched_examples = [
            i for i in active if i.match_status == MatchStatus.unmatched
        ][:8]

        return dict(
            docs=docs, partners=partners, services=services,
            all_items=all_items, active=active,
            by_format=by_format, by_status=by_status,
            per_format_items=per_format_items, ms=ms, total=total, matched=matched,
            flag_counter=flag_counter, history_examples=history_examples,
            currency_examples=currency_examples, unmatched_examples=unmatched_examples,
            timing=_measure_extraction_timing(),
        )
    finally:
        db.close()


def render(c: dict) -> str:
    active, total, matched, ms = c["active"], c["total"], c["matched"], c["ms"]
    norm = matched / total
    auto = ms[MatchStatus.matched_auto] / total
    verified = sum(1 for i in active if i.is_verified)
    review = sum(1 for i in active if i.needs_review)

    L: list[str] = []
    L.append("# Отчёт о качестве обработки — MedArchive\n")
    L.append("> Сгенерировано `python -m scripts.quality_report` по реальным результатам "
             "разбора демонстрационного архива (`backend/sample_data/archive.zip`).\n")

    L.append("## 1. Сводка\n")
    L.append("| Метрика | Значение |")
    L.append("| --- | --- |")
    L.append(f"| Партнёров (клиник) | {len(c['partners'])} |")
    L.append(f"| Услуг в справочнике | {len(c['services'])} |")
    L.append(f"| Документов обработано | {len(c['docs'])} |")
    L.append(f"| Позиций прайса (активных) | {len(active)} |")
    L.append(f"| Позиций всего (с архивными версиями) | {len(c['all_items'])} |")
    L.append(f"| **Нормализовано (всего)** | **{matched}/{total} = {norm*100:.1f}%** |")
    L.append(f"| Авто-нормализация | {ms[MatchStatus.matched_auto]}/{total} = {auto*100:.1f}% |")
    L.append(f"| Ручное сопоставление | {ms[MatchStatus.matched_manual]} |")
    L.append(f"| В очереди верификации (needs_review) | {review} |")
    L.append(f"| В очереди несопоставленных (unmatched) | {ms[MatchStatus.unmatched]} |")
    L.append(f"| Верифицировано оператором | {verified} |")
    L.append("")
    target = "✅ ВЫПОЛНЕНО" if auto >= 0.70 else "⚠️ ниже цели"
    L.append(f"> Цель ТЗ §5 (≥70% авто-нормализации для MVP): **{auto*100:.1f}%** — {target}\n")

    L.append("## 2. Извлечение данных по форматам\n")
    L.append("| Формат | Документов | Позиций | Сопоставлено | % |")
    L.append("| --- | --- | --- | --- | --- |")
    for fmt, st in sorted(c["per_format_items"].items(), key=lambda x: str(x[0])):
        items = st["items"]
        pct = (st["matched"] / items * 100) if items else 0.0
        L.append(f"| {getattr(fmt,'value',fmt)} | {st['docs']} | {items} | {st['matched']} | {pct:.1f}% |")
    L.append("")
    L.append("Статусы обработки документов: " +
             ", ".join(f"{getattr(k,'value',k)}={v}" for k, v in c["by_status"].items()) + "\n")

    L.append("## 3. Производительность извлечения (НФТ §5)\n")
    res = c["timing"]["results"]
    if res:
        L.append("| Файл | Формат | Позиций | Время извлечения |")
        L.append("| --- | --- | --- | --- |")
        for name, fmt, nrows, dt in res:
            L.append(f"| {name} | {getattr(fmt,'value',fmt)} | {nrows} | {dt:.2f} с |")
        text_times = [dt for _, fmt, _, dt in res if fmt != FileFormat.scan_pdf]
        ocr_times = [dt for _, fmt, _, dt in res if fmt == FileFormat.scan_pdf]
        L.append("")
        if text_times:
            L.append(f"- Макс. время текстового документа: **{max(text_times):.2f} с** "
                     f"(лимит ТЗ: 60 с) — {'✅' if max(text_times) <= 60 else '⚠️'}")
        if ocr_times:
            L.append(f"- Макс. время скана (OCR): **{max(ocr_times):.2f} с** "
                     f"(лимит ТЗ: 180 с) — {'✅' if max(ocr_times) <= 180 else '⚠️'}")
    L.append("")

    L.append("## 4. Валидация и аномалии (ТЗ §4.4)\n")
    if c["flag_counter"]:
        L.append("| Флаг | Количество |")
        L.append("| --- | --- |")
        for fl, n in c["flag_counter"].most_common():
            L.append(f"| {fl} | {n} |")
    else:
        L.append("_Флагов не зафиксировано._")
    L.append("")

    L.append("## 5. Версионирование цен (история)\n")
    if c["history_examples"]:
        ch = c["history_examples"][0]
        nm = ch[0].service_name_raw
        L.append(f"Пример истории для позиции **«{nm}»**:\n")
        L.append("| Версия | Дата | Цена резидент (KZT) | Активна | Флаги |")
        L.append("| --- | --- | --- | --- | --- |")
        for it in ch:
            L.append(f"| v{it.version} | {it.effective_date} | {it.price_resident_kzt} | "
                     f"{'да' if it.is_active else 'архив'} | {', '.join(it.anomaly_flags or []) or '—'} |")
        L.append(f"\nВсего позиций с историей (>1 версии): {len(c['history_examples'])}\n")
    else:
        L.append("_Нет позиций с несколькими версиями в текущем наборе._\n")

    L.append("## 6. Конвертация валют (ТЗ §4.4)\n")
    if c["currency_examples"]:
        L.append("| Услуга | Оригинал | Курс→KZT | Цена в KZT |")
        L.append("| --- | --- | --- | --- |")
        for i in c["currency_examples"]:
            L.append(f"| {i.service_name_raw[:40]} | {i.price_original} {i.currency_original} | "
                     f"{i.fx_rate_to_kzt} | {i.price_resident_kzt} |")
    else:
        L.append("_Позиций в иностранной валюте не найдено._")
    L.append("")

    L.append("## 7. Очередь несопоставленных (для ручной разметки)\n")
    if c["unmatched_examples"]:
        L.append("| Сырое название | Уверенность лучшего кандидата |")
        L.append("| --- | --- |")
        for i in c["unmatched_examples"]:
            conf = f"{i.match_confidence:.2f}" if i.match_confidence is not None else "—"
            L.append(f"| {i.service_name_raw[:50]} | {conf} |")
    else:
        L.append("_Очередь пуста._")
    L.append("")
    return "\n".join(L)


def main() -> None:
    c = collect()
    if not c["docs"]:
        print("База пуста. Сначала выполните: python -m scripts.bootstrap_demo")
        return
    md = render(c)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")

    active, total = c["active"], c["total"]
    matched = c["matched"]
    auto = c["ms"][MatchStatus.matched_auto] / total
    print("=" * 56)
    print("MedArchive — отчёт о качестве обработки")
    print("=" * 56)
    print(f"  Документов:      {len(c['docs'])}  ({dict((getattr(k,'value',k),v) for k,v in c['by_format'].items())})")
    print(f"  Позиций (актив): {len(active)}")
    print(f"  Нормализация:    {matched}/{total} = {matched/total*100:.1f}%")
    print(f"  Авто-норм.:      {auto*100:.1f}%  (цель ≥70%: {'OK' if auto>=0.7 else 'LOW'})")
    print(f"  Очередь review:  {sum(1 for i in active if i.needs_review)}")
    print(f"  Unmatched:       {c['ms'][MatchStatus.unmatched]}")
    print(f"  Отчёт записан:   {REPORT_PATH}")
    print("=" * 56)


if __name__ == "__main__":
    main()
