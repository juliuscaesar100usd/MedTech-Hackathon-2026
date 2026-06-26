# Архитектура MedArchive

## 1. Обзор

MedArchive — конвейер обработки прайс-листов клиник-партнёров. Поток данных:

```
ZIP-архив ─▶ распаковка ─▶ детект формата ─▶ очередь (PriceDocument.pending)
   ─▶ фоновый воркер: parse ─▶ normalize ─▶ validate ─▶ version ─▶ persist
   ─▶ БД ─▶ REST API ─▶ React UI (поиск / админка / дашборд)
```

Принцип расширяемости (НФТ §5): ядро (pipeline) общается только с **контрактами**
(`parsers.base.BaseParser`, `normalization.MatchResult`, `validation.ValidationOutcome`),
поэтому новый формат/источник добавляется регистрацией парсера без изменения ядра.

## 2. Слои и модули

| Слой | Пакет | Ответственность |
| --- | --- | --- |
| Контракты | `app/models.py`, `app/schemas.py`, `app/enums.py`, `parsers/base.py`, `*/types.py` | Сущности БД, DTO API, перечисления, интерфейсы парсеров и движков |
| Парсеры | `app/parsers/` | `detect` (тип файла), `pdf_text`, `pdf_scan` (OCR), `xlsx`, `docx` (tracked changes), `table_extract` (эвристики колонок услуга/цена) |
| Нормализация | `app/normalization/` | `catalog` (загрузка справочника), `matcher` (exact → синонимы → fuzzy → эмбеддинги), генерация кандидатов для очереди |
| Валидация | `app/validation/` | `validators` (проверки §4.4), `currency` (конвертация в KZT по дате), `versioning` (dedup + история цен + аномалии) |
| Приём данных | `app/ingestion/` | `archive` (ZIP), `partner` (разрешение/dedup партнёра по БИН+имени), `pipeline` (оркестрация), `worker` (фоновая очередь) |
| API | `app/api/` | роутеры services / partners / search / matching / admin |
| UI | `frontend/` | React+Vite: поиск, страница партнёра, админка, дашборд |

## 3. Модель данных (ТЗ §3)

- **Service** — целевой справочник (`service_id`, `service_name`, `synonyms[]`, `category`, `icd_code`).
- **Partner** — клиника (`name`, `city`, `address`, `bin`, контакты, `is_active`).
- **PriceDocument** — один файл = прайс одной клиники на дату; одновременно строка
  очереди обработки (`parse_status`: pending/processing/done/error/needs_review),
  хранит `stored_path` (оригинал не удаляется), `raw_content` (аудит).
- **PriceItem** — позиция прайса: сырое имя, цена резидент/нерезидент (KZT),
  оригинальная цена/валюта, привязка к `service_id`, статус матчинга, флаги
  валидации/аномалий, верификация, **версионирование** (`is_active`, `version`,
  `previous_item_id`).
- **IngestionBatch** — загруженный архив (для дашборда/статуса).
- **MatchEvent** — аудит ручных действий оператора (match/verify/reject/create).

## 4. Ключевые решения

- **Портативность БД.** UUID как `String(36)`, JSON через portable-тип → один и тот
  же код на SQLite (dev, zero-config) и PostgreSQL (prod, docker-compose).
- **Очередь без внешней инфраструктуры.** Очередь = строки `PriceDocument` со
  статусом; фоновый воркер на пуле потоков обрабатывает их асинхронно после
  загрузки (масштабируется до Celery/RQ без изменения контракта pipeline).
- **OCR.** `pdf_scan` растрирует страницы (PyMuPDF) и распознаёт Tesseract
  (`rus+kaz+eng`), затем чистит артефакты перед извлечением таблиц.
- **Нормализация.** Каскад: точное совпадение → синонимы → RapidFuzz (token-set) →
  опционально мультиязычные эмбеддинги (sentence-transformers). Порог
  автосопоставления конфигурируется (`MATCH_AUTO_THRESHOLD`, по умолчанию 0.85);
  «серая зона» → `needs_review`, ниже `MATCH_REVIEW_THRESHOLD` → `unmatched`.
- **Версионирование цен.** При изменении цены прежняя позиция архивируется
  (`is_active=False`), создаётся новая версия с инкрементом `version` и ссылкой
  `previous_item_id`. История хранится бессрочно.
- **Валюта.** Не-KZT конвертируется по курсу на дату прайса (`fx_rates.json`,
  ближайшая дата ≤ даты прайса), оригинал сохраняется (`price_original`/`currency`).

## 5. Нефункциональные требования (§5)

| Требование | Как обеспечено |
| --- | --- |
| ≤60с на текстовый документ | Парсинг pdfplumber/openpyxl/python-docx; матчинг RapidFuzz (мс на позицию) |
| ≤3мин на скан (OCR) | Растеризация 300 DPI + Tesseract постранично |
| ≥70% автонормализации | Каскад exact/синонимы/fuzzy + богатые синонимы в справочнике |
| Сохранность данных | Оригиналы в `storage/originals`, `raw_content` в БД — не удаляются |
| История цен бессрочно | Версионирование без удаления |
| Расширяемость | Реестр парсеров + стратегии матчинга + конвейер валидаторов |
```

