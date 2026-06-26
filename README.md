# MedArchive — автоматическая обработка архива прайсов клиник-партнёров

Система автоматически разбирает архив прайс-листов клиник-партнёров (PDF, скан-PDF,
DOCX, XLSX), извлекает услуги и цены (резидент/нерезидент), нормализует их к
целевому справочнику услуг, валидирует, версионирует историю цен и предоставляет
REST API + веб-интерфейс для поиска «кто оказывает услугу и по какой цене».

> Кейс 2 хакатона MedPartners. Полная реализация ТЗ: парсинг всех форматов с OCR и
> tracked changes, нормализация (exact/синонимы/fuzzy/эмбеддинги), валидация и
> верификация, версионирование цен, REST API (OpenAPI), админ-панель и дашборд.

---

## Архитектура

```
            ┌──────────────┐     ┌───────────────────────────────────────┐
  ZIP /     │   FastAPI    │     │            Ingestion pipeline          │
  upload ──▶│  + React UI  │────▶│  detect → parse → normalize → validate │
            └──────────────┘     │         → version → persist            │
                  │              └───────────────────────────────────────┘
                  │                     │            │            │
                  ▼                     ▼            ▼            ▼
            ┌──────────┐         ┌──────────┐ ┌──────────┐ ┌──────────────┐
            │  Search  │         │ Parsers  │ │ Matcher  │ │  Validators  │
            │   API    │         │ pdf/ocr/ │ │ fuzzy/   │ │  + currency  │
            └──────────┘         │ xlsx/docx│ │ embed    │ │  + versioning│
                  │              └──────────┘ └──────────┘ └──────────────┘
                  ▼                                  │
            ┌───────────────────────────────────────▼──────────────────┐
            │     DB: Partner · PriceDocument · PriceItem · Service      │
            │           (SQLite by default · PostgreSQL in prod)         │
            └───────────────────────────────────────────────────────────┘
```

Детали — в [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Быстрый старт (без Docker, SQLite — для разработки и демо)

Требуется: Python 3.11+, Node 18+, установленный Tesseract OCR
(`apt install tesseract-ocr tesseract-ocr-rus tesseract-ocr-kaz`; русский/казахский
traineddata также лежат в `backend/tessdata`).

```bash
# 1. Бэкенд
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# 2. Сгенерировать демо-справочник + демо-архив, наполнить БД и обработать его
python -m scripts.bootstrap_demo

# 3. Запустить API (Swagger на http://localhost:8000/docs)
uvicorn app.main:app --reload

# 4. Фронтенд (в другом терминале)
cd ../frontend
npm install
npm run dev          # http://localhost:5173
```

## Быстрый старт через Docker (PostgreSQL — как в проде)

```bash
docker compose up --build
# UI:      http://localhost:5173
# API:     http://localhost:8000/docs
```
При первом запуске backend автоматически наполняет демо-данные.

---

## Загрузка реального архива организаторов

```bash
# Через CLI:
python -m scripts.seed_catalog  path/to/service_catalog.xlsx   # загрузить справочник
python -m scripts.run_ingest    path/to/clinic_prices.zip      # обработать архив

# Через API / UI:
POST /api/admin/catalog   (файл XLSX/JSON справочника)
POST /api/admin/upload    (ZIP-архив прайсов)  → админ-панель «Загрузка»
```

---

## REST API (полная спецификация — `/docs`, OpenAPI — `/openapi.json`)

| Метод | Endpoint | Описание |
| --- | --- | --- |
| GET  | `/api/services` | Справочник услуг (фильтр по категории) |
| GET  | `/api/services/{id}/partners` | Партнёры, оказывающие услугу, с ценами |
| GET  | `/api/partners` | Партнёры (фильтр по городу/статусу) |
| GET  | `/api/partners/{id}/services` | Все услуги партнёра с ценами |
| GET  | `/api/search?q=` | Полнотекстовый поиск по услугам и партнёрам |
| GET  | `/api/unmatched` | Несопоставленные позиции (для операторов) |
| POST | `/api/match` | Ручное сопоставление позиции со справочником |
| POST | `/api/admin/upload` | Загрузка ZIP-архива прайсов |
| POST | `/api/admin/catalog` | Загрузка справочника услуг |
| GET  | `/api/admin/documents` | Статус обработки документов (очередь) |
| GET  | `/api/admin/verification` | Очередь верификации |
| POST | `/api/admin/verify` | Подтвердить/отклонить/исправить позицию |
| GET  | `/api/admin/dashboard` | Метрики: документы, % нормализации, очереди |

---

## Отчёт о качестве

```bash
python -m scripts.quality_report          # печатает метрики и пишет docs/REPORT.md
```

---

## Тесты

```bash
cd backend && . .venv/bin/activate
pytest -q
```

---

## Структура

```
backend/
  app/
    parsers/        # pdf_text, pdf_scan(OCR), xlsx, docx(tracked changes), detect
    normalization/  # matcher (exact/synonym/fuzzy/embedding), catalog loader
    validation/     # §4.4 проверки, конвертация валют, версионирование цен
    ingestion/      # zip-архив, очередь, фоновый воркер, разрешение партнёра
    api/            # роутеры services/partners/search/match/admin
    models.py schemas.py config.py database.py enums.py
  scripts/          # генерация демо-данных, seed, run_ingest, bootstrap, отчёт
  tests/
frontend/           # React + Vite (поиск, страница партнёра, админка, дашборд)
docs/               # ARCHITECTURE, REPORT, презентация
```

См. также: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
[`docs/REPORT.md`](docs/REPORT.md) · [`docs/PRESENTATION.md`](docs/PRESENTATION.md)
