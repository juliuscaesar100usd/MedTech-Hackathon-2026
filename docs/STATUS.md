# MedArchive — Status Audit (read-only)

> Project in repo is **MedArchive** (МедТех Хакатон 2026, Кейс 2). The build plan
> called it "MedPartners"; same Track-2 case. This is a **read-only** audit:
> nothing was installed, booted, built, seeded, or tested. Verdicts below come from
> **static code reading** + the author's **committed `docs/REPORT.md`** numbers —
> NOT from runtime verification in this environment.

## 0. Environment reality (why nothing could be executed here)

This checkout is **un-provisioned**:

| Thing | State |
| --- | --- |
| Python venv / backend deps | **none** — only `pydantic`, `httpx`, `dateutil` import; `fastapi`, `uvicorn`, `sqlalchemy`, `pandas`, `openpyxl`, `python-docx`, `pdfplumber`, `PyMuPDF`, `pytesseract`, `Pillow`, `rapidfuzz`, `pytest`, `reportlab`, `psycopg2` are all **missing** |
| `tesseract` binary | **not on PATH** (required for the scan/OCR parser) |
| Database | **no DB exists** (default is SQLite `backend/medarchive.db`; file absent) |
| `frontend/node_modules` | **absent** |
| Docker | **not running** (compose path unavailable) |
| Python on host | **3.14.6** — newer than the project's `python:3.12-slim` Docker target; several pinned deps (pandas/PyMuPDF/psycopg2/pdfplumber) may lack 3.14 wheels |

**Boot attempt:** `python3 -c "import app.main"` → `ModuleNotFoundError: No module named 'fastapi'`.
**Build attempt:** `npm run build` → `sh: tsc: command not found` (no node_modules).

Per the no-install constraint these were **not** resolved. To actually run it: `docker compose up`
(builds 3.12 image, installs tesseract, runs `scripts.bootstrap_demo`, serves on :8000/:5173),
**or** a Python 3.12 venv + `pip install -r backend/requirements.txt` + system `tesseract-ocr`,
plus `npm install` in `frontend/`.

## 1. Phase status (build plan 0–8)

| Phase | Verdict | Note |
| --- | --- | --- |
| 0 — scaffold (monorepo, FastAPI, React+Vite, compose, /health) | **DONE** | All present; health is at **`/api/health`** (not `/health`); `/`→`/docs`. Not booted here. |
| 1 — data model + catalog ingestion + docs/CONTEXT.md | **DONE** | Service/Partner/PriceDocument/PriceItem (+IngestionBatch/MatchEvent) match ТЗ §3. **No `ServiceSpecialty`** — but ТЗ has no specialty (only `category`); "511 services/122 specialties" is **not in the ТЗ**. `CONTEXT.md` delivered as `docs/ARCHITECTURE.md`. |
| 2 — native parsers XLSX/XLS/DOCX | **PARTIAL** | XLSX (multi-sheet, header + resident/non-resident/currency column-role detection) and DOCX (incl. tracked-changes acceptance) are strong. **`.xls` is BROKEN**: `xlrd` missing from requirements → every `.xls` errors; also untested (no `.xls` in demo). In-table section/category rows not specially handled. |
| 3 — PDF + scan via vision-LLM (claude-sonnet-4-6), hybrid | **DONE** (different approach) | PDF-text (pdfplumber+fitz) and scan extraction work, with hybrid routing in `detect.py`. **Scan path is Tesseract OCR, NOT a vision-LLM** — there is no `anthropic`/Claude code or dependency anywhere. |
| 4 — normalization (exact/fuzzy/embedding, specialty-aware prior) + quality report | **DONE** | exact→synonym→fuzzy(rapidfuzz) real; embedding leg present but **off by default** (`use_embeddings=False`, `sentence-transformers` only in `requirements-ml.txt`). **No specialty-aware prior** (no specialty concept). `quality_report.py` real → writes `REPORT.md`. |
| 5 — validation checklist + dedup + versioning/price-history | **DONE** | Validators (empty-name skip, invalid price, non-resident<resident, future-date warn, dated FX→KZT), dedup by (partner, raw-name, date), versioning (`version`/`previous_item_id`/`is_active` + `reconcile_active_versions`), >50% price-anomaly flag. History stored — but not exposed (see 6/7). |
| 6 — REST API + OpenAPI (…history, stats, upload) | **PARTIAL** | services/partners/search/unmatched/match/upload/stats(dashboard)/catalog/documents/batches/verification/verify all present & real. **Price-`history` endpoint MISSING.** OpenAPI auto-served at `/docs` but not rendered here (can't boot). |
| 7 — frontend (dashboard, upload, verification split-view, unmatched, search, detail + history chart) | **PARTIAL** | 6/7 pages real and wired to live endpoints (split-view verify + manual-match queue both implemented). **Price-history chart MISSING** (no charting lib / time-series; only hand-rolled distribution bars). Build **unverified** (no node_modules). |
| 8 — demo seed + REPORT.md + PITCH.md | **DONE** | `bootstrap_demo.py` (init→seed→ingest→process→summary) + generators real. `REPORT.md` committed with real numbers. `PITCH.md` delivered as `docs/PRESENTATION.md`. Cannot regenerate here (no deps/DB). |

## 2. Key metrics

- **Catalog loaded:** **No** (no DB in this env). Seed data present = **78 services / 7 categories / 0 specialties** (`sample_data/service_catalog.{json,xlsx}` agree). This is a demo catalog, **not** the 511/122 figure (which isn't a ТЗ requirement); the real organizer catalog is loadable via `POST /api/admin/catalog` / `seed_catalog.py`.
- **Docs ingested:** **0/8** here (no DB). Demo archive = **8 files** (plan said 10): 3 text PDF (Сұнқар, incl. version history), 1 scan PDF (Шипагер→OCR), 2 XLSX, 2 DOCX (one "правки"/tracked-changes). **No `.xls`.** Author-reported run: 8/8 processed (3 done, 5 needs_review, 0 error).
- **% auto-normalized:** **Not computed here.** Author-committed `REPORT.md`: **94.7%** (71/75 items, manual 0).
- **Unmatched count:** Not computed here. Author-reported: **3**.
- **Verification-queue (needs_review):** Not computed here. Author-reported: **10**.

## 3. Top blockers (most impactful next)

1. **Nothing runs in this environment.** No venv/deps, no DB, no node_modules, no tesseract, Docker down; host Python 3.14 likely can't pip-install the 3.12-targeted deps. Nothing (any phase) is runtime-verified. → Provision via Docker or a 3.12 venv + system tesseract + `npm install`.
2. **`.xls` parsing is dead:** `xlrd` absent from `requirements.txt`; real `.xls` → parse error (masked because the demo archive has none).
3. **Price-history not surfaced:** versioning data + `reconcile_active_versions` exist, but there is **no `GET …/history` endpoint and no UI history chart** — both explicitly in the plan. Thin missing layer over existing data.
4. **Scan extraction is Tesseract OCR, not the planned Claude vision-LLM.** Works (author-reported 100% on the scan), but diverges from spec and OCR is more brittle; matters if grading rewards LLM-vision.
5. **Catalog is a 78-item demo.** Architecturally fine (loader exists), but the system only normalizes against 78 services/7 categories until the organizer catalog is uploaded; no specialty dimension exists.

## 4. Exists but doesn't actually work / isn't wired

- **Backend** can't boot here → `ModuleNotFoundError: fastapi` (uvicorn/sqlalchemy also missing).
- **Frontend** can't build here → `npm run build` = `tsc: command not found` (node_modules absent).
- **`.xls` parser**: detection (OLE2 magic) + pandas branch present, but errors at runtime (no `xlrd`). Effectively dead code.
- **Embedding matcher**: implemented but **off by default**, and `sentence-transformers` isn't in base requirements — never runs unless separately installed + enabled.
- **Price-history**: data model + reconcile present; **no REST endpoint, no UI chart**.
- **`getBatches` (`GET /admin/batches`)**: frontend helper defined but **unused** by any page.
- **Test suite** (59 test fns, ~72 cases; hermetic SQLite + TestClient, async worker monkeypatched): **can't run here**; even with Python deps, **8 parser tests hardcode a Linux font path** `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` and 1 needs the `tesseract` binary → they error on macOS. Designed for Debian/CI; would plausibly pass there.
- **Section/category header rows** in tables are emitted as null-price rows (data-quality nit, not a crash).
- Backend `Dockerfile` installs tesseract but **not** `fonts-dejavu` (only affects in-image test fixtures, not runtime).

## 5. Endpoint inventory (all under `/api`, read from routers)

`GET /api/health` · `GET /` →`/docs` · `GET /services` · `GET /services/{id}/partners` ·
`GET /partners` · `GET /partners/{id}` · `GET /partners/{id}/services` · `GET /search?q=` ·
`GET /unmatched` · `POST /match` · `POST /admin/upload` · `POST /admin/catalog` ·
`GET /admin/documents` · `GET /admin/batches` · `GET /admin/verification` · `POST /admin/verify` ·
`GET /admin/dashboard`. **Missing vs plan:** price-`history`.

---
*Audited read-only; no code, data, or dependencies were modified. Author-reported figures come from the committed `docs/REPORT.md` and are not reproducible without provisioning the stack.*
