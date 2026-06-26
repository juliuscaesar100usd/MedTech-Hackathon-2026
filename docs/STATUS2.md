# MedArchive — Post-Merge Audit (STATUS2)

> Read-only audit after the 4-lane parallel build + integration step. No code was
> changed. Verdicts come from live runs in this environment (Python 3.14 venv with
> the merged deps installed during the prior integration step, system `tesseract`
> 5.5.2, SQLite) plus static reading where a thing could not be exercised. The
> auditor also performed the integration step, so integration-introduced edits are
> attributed to "integration", not to a lane.

## Provenance / how this was verified
- Git history: `9e5465e` (Initial commit) → `238701c` ("Integrate lanes 1-4 …").
  **All four lanes + the integration landed in ONE squashed commit** — there are no
  per-lane commits or merge commits, so file→lane attribution below is by content,
  not by `git blame`.
- Live: backend booted (`uvicorn app.main:app`), `/api/health`, `/docs`,
  `/openapi.json` all 200; pipeline run on `data/archive/` (9 files) into
  `backend/integration_xls.db`; `pytest`; OpenAPI route introspection.

---

## 1. What changed (`git diff 9e5465e..238701c`, 29 files, +2716/-133)

| Lane | Files it actually touched |
| --- | --- |
| **Lane 1 — catalog/schema** | `app/models.py` (+`Service.code`, `ServiceSpecialty`, `PriceItem.section`), `app/catalog_loader.py` (new), `scripts/load_real_catalog.py` (new), `app/api/admin.py` (route `POST /catalog` → real loader), `requirements.lane1.txt`, `data/catalog/real_catalog.xlsx` |
| **Lane 2 — matching** | `app/normalization/matcher.py`, `app/normalization/embeddings.py`, `tests/test_matcher_lane2.py` (new), `requirements.lane2.txt` |
| **Lane 3 — extraction** | `app/parsers/xlsx_parser.py` (.xls), `app/parsers/pdf_scan.py` (vision hook), `app/parsers/table_extract.py` (sections), `app/parsers/vision_fallback.py` (new), `requirements.lane3.txt` |
| **Lane 4 — price history** | `app/api/price_history.py` (new), `app/main.py` (1 include line), `frontend/src/pages/ServicePartnersPage.tsx`, `frontend/package.json` + `package-lock.json`, `frontend/tsconfig.tsbuildinfo`, `requirements.lane4.txt` |
| **Integration step** | `requirements.txt` (merged fragments), `app/ingestion/pipeline.py` (pass `section`→matcher+upsert), `app/validation/versioning.py` (`section` param), `tests/test_parsers.py` (cross-OS font path), `docs/REPORT.md` (regenerated), `data/archive/` (reconstructed clinic set + a synthetic `.xls`) |
| Other | `.gitignore` (+1), `docs/STATUS.md` (prior audit, committed) |

**Cross-lane file overlaps (merge-risk):** **none between lanes** — no single source
file was edited by two different lanes. The only shared-core files edited are
`pipeline.py` and `versioning.py`, both touched **only by the integration step** (to
wire lane-2's specialty prior + lane-1's `section` column). That is a deliberate
integration touchpoint, not a lane-vs-lane collision.

## 2. No-conflict contract

| Contract | Result |
| --- | --- |
| Only lane 1 touches models/migrations | ✅ HELD. `models.py` = lane 1 only; no Alembic/migrations exist (schema is `create_all`). |
| Only lane 4 touches frontend & `app/main.py` | ✅ HELD. `main.py` (1 line) + all `frontend/*` = lane 4 only. |
| `requirements.txt` assembled from fragments, not edited directly by lanes | ✅ HELD for lanes (each shipped `requirements.laneN.txt`). The **integration step** edited `requirements.txt` directly to merge them — the sanctioned integration action. |

**Violations: none.**

---

## 3. Lane deliverables (DONE / PARTIAL / MISSING / BROKEN)

### LANE 1 — real catalog · **DONE**
- `ServiceSpecialty` model exists; `Service.code` (int, unique, nullable) + `PriceItem.section` added.
- Loader `catalog_loader.load_real_catalog` ingests `data/catalog/real_catalog.xlsx`; auto-routed from `POST /api/admin/catalog`.
- **Live assert:** loaded → **511 coded services / 122 specialties / 1281 links** (1231 total Service rows = 511 coded + 720 NULL-code lab rows; the file's lab block is `#REF!`-corrupted, codes unrecoverable — documented). `scripts/load_real_catalog.py` self-asserts these and passes.

### LANE 2 — matching · **DONE (code) / PARTIAL (active by default)**
- Chain `exact → synonym → fuzzy(rapidfuzz) → embedding(e5)` is wired in `matcher.match()`.
- `sentence-transformers` is in merged `requirements.txt` and importable (5.6.0 / torch 2.12.1). Embedding step **works** (live run: 40/81 active matches via `embedding`).
- **But embeddings are OFF by default** (`config.use_embeddings = False`); only ON when `USE_EMBEDDINGS=true`. Default config = fuzzy-only (~84.7%).
- Specialty-aware prior **is present** (`_infer_specialty` / `_allowed_sids` restrict candidates by `ServiceSpecialty`) and **is now wired** into the pipeline (integration). Section-header **input filter** exists (`is_section_header`/`match_item`) — see "merged but doesn't work".

### LANE 3 — extraction · **DONE**
- `xlrd` in merged requirements; **`.xls` path works live** (Клиника 7 `.xls` → `xls`, 8 rows, all exact-matched, `done`). LibreOffice `.xls→.xlsx` fallback present in code but **inert here** (no `soffice` installed) — the working path is xlrd.
- Claude vision fallback wired: `pdf_scan.py` calls `is_low_confidence()` then `vision_fallback` (model `claude-sonnet-4-6`, per-page-hash cache, `ANTHROPIC_API_KEY` from env/.env, kill-switch `VISION_FALLBACK_ENABLED`). **Tesseract OCR is the default**; vision is **inert without `ANTHROPIC_API_KEY`** (not set here) and was not exercised.

### LANE 4 — price history · **DONE**
- `GET /api/services/{service_id}/partners/{partner_id}/history` exists and is **registered** (in OpenAPI; `main.py` include line present). Live: returns 200 with the ordered version chain + `is_anomaly`.
- recharts history chart on the Service-detail page with a red >50% anomaly marker — verified live in the integration step (Сункар "Витамин D" 9000→19000, +111%, flagged red).

---

## 4. Integration health
- **Merged `requirements.txt`:** union of all 4 fragments, **no duplicate packages** (`openpyxl` de-duped; `sentence-transformers`, `numpy`, `xlrd`, `anthropic` added). All 4 `requirements.laneN.txt` fragments **still linger** in the tree.
- **Boots:** ✅ `uvicorn app.main:app` starts clean; `/api/health` → `{"status":"ok"}`; `/docs` 200; `/openapi.json` 200; **17 routes** registered incl. the history route.
- **Pipeline (live, `data/archive/`, embeddings ON):** see metrics.
- **Tests:** **83 passed / 0 failed / 0 errored**. (Before the integration font fix these were 75 passed / 8 errored — the 8 were a macOS-only fixture issue, now resolved cross-OS.)

## 5. Key metrics (live, `backend/integration_xls.db`, 9-file `data/archive/`, embeddings ON)
- Catalog loaded: **yes** — 1231 services (511 coded) / 122 specialties / 1281 links / 6 partners.
- Docs processed: **9/9, 0 errors** (3 `done`, 6 `needs_review`). *(Original demo archive = 8 files; integration added one synthetic `.xls` → 9.)*
- % auto-normalized vs the real catalog: **93.8%** active (76/81) · **93.5%** all-extracted (87/93). *(Fuzzy-only baseline w/o embeddings ≈ 84.7%.)*
- `match_method` (active): **embedding 40 · fuzzy 20 · exact 21**.
- Unmatched: **0** (active). Verification queue (`needs_review`): **14**.
- Per-file extracted rows: scan 9 · **.xls 8** · docx 8 · docx-правки 7 · Сункар pdf 5/21/5 · xlsx 22 · xlsx 8.
- **.xls works: YES** (Клиника 7, 8 rows, exact-matched). **Scan works: YES** (Клиника 4 / Шипагер, 9 rows via Tesseract). **History endpoint + chart: YES**.

## 6. Top blockers (most impactful next)
1. **Quality is config-gated.** The headline 93.8% needs `USE_EMBEDDINGS=true`; default `use_embeddings=False` ships the ~84.7% fuzzy-only behavior. Decide the production default.
2. **Specialty prior is dormant on real data.** It is wired, but the demo/reconstructed archive yields **0 section headers**, so the prior never restricts candidates — the embedding gain is doing the work, not the prior. Needs source files that actually carry section headings to validate.
3. **Section-header rows are not filtered in the pipeline.** The matcher has `match_item()` (drops header rows), but `process_document` calls `matcher.match()` — header rows can still be emitted as items.
4. **No real `.xls`/scan from the organizer dataset.** `data/archive/` is reconstructed; the `.xls` proving the path is **synthetically generated**. `.xls` LibreOffice fallback and the Claude vision fallback are both **inert** here (no `soffice`, no `ANTHROPIC_API_KEY`) and degrade silently.
5. **Ops shape:** schema is `create_all` (no Alembic migrations); `psycopg2-binary` (Postgres) is listed but unexercised (SQLite only); the run needs a ~1 GB e5 model download + system tesseract.

## 7. Merged but doesn't actually work / isn't active
- **Embeddings:** OFF by default; only the env-flagged runs use them.
- **Specialty-aware prior:** wired but a **no-op on this data** (0 sections detected; `PriceItem.section` came back unpopulated in the integration run).
- **Section-header input filter (`match_item`):** implemented in lane 2 but **not called** by the pipeline (uses `match()`), so it's bypassed.
- **Claude vision fallback:** complete but **inert** without `ANTHROPIC_API_KEY` (`vision_available()` → False) — Tesseract is the only live scan path.
- **`.xls` LibreOffice fallback:** present but **dead** here (no `soffice`); `.xls` works only via xlrd.
- **`docs/REPORT.md` timing section:** re-parses `sample_data/archive.zip` (8 files), so the `.xls` is absent from that one table even though the DB metrics reflect 9 docs.
- **`frontend/tsconfig.tsbuildinfo`** committed as a build artifact (noise).
- **`requirements.laneN.txt` fragments** still present post-merge (harmless, but redundant now).
