# MedArchive — submission Makefile (SQLite, no Docker needed).
#
#   make setup   # one-time: venv + backend deps + frontend deps
#   make demo    # run the REAL-data pipeline end-to-end, leave the DB seeded
#   make run-api # serve the API  -> http://localhost:8000/docs
#   make run-web # serve the UI   -> http://localhost:5173
#   make test    # backend test suite
#
# Embeddings load OFFLINE from a baked cache when present (make bake-model);
# without it the matcher degrades to the lexical chain and the demo still runs.

PY  ?= python3
VPY := .venv/bin/python
VPIP := .venv/bin/pip

.PHONY: help setup bake-model demo report run-api run-web test clean

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## one-time: create venv, install backend + frontend deps
	$(PY) -m venv backend/.venv
	cd backend && $(VPIP) install -U pip && $(VPIP) install -r requirements.txt
	cd frontend && npm install

bake-model: ## optional: download the e5 embedding model for OFFLINE use (~1.1GB, one time)
	cd backend && PYTHONPATH=. $(VPY) -m scripts.bake_embedding_model

demo: ## run the REAL-data pipeline end-to-end and leave the DB seeded
	cd backend && PYTHONPATH=. $(VPY) -m scripts.run_demo

report: ## regenerate docs/REPORT.md from the seeded DB
	cd backend && PYTHONPATH=. $(VPY) -m scripts.quality_report

run-api: ## serve the API at http://localhost:8000/docs
	cd backend && PYTHONPATH=. $(VPY) -m uvicorn app.main:app --reload --port 8000

run-web: ## serve the frontend at http://localhost:5173
	cd frontend && npm run dev

test: ## run the backend test suite
	cd backend && PYTHONPATH=. $(VPY) -m pytest -q

clean: ## delete the local demo database
	rm -f backend/medarchive.db backend/medarchive.db-shm backend/medarchive.db-wal
