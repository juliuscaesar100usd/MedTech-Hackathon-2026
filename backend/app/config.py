"""Application configuration (env-driven via pydantic-settings).

All behaviour-controlling knobs live here so the system can be re-targeted at a
new database, OCR language set, or matching threshold without touching the core.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- General ---
    app_name: str = "MedArchive"
    environment: str = "development"

    # --- Database ---
    # Default to a zero-config local SQLite file. In production set DATABASE_URL
    # to a PostgreSQL DSN, e.g. postgresql+psycopg2://user:pass@host:5432/medarchive
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'medarchive.db'}"

    # --- Storage of original/raw artefacts (NFR: source files never deleted) ---
    data_dir: Path = BACKEND_ROOT / "storage"

    # --- Matching / normalization thresholds ---
    # cosine/ratio similarity in [0,1]
    match_auto_threshold: float = 0.85   # >= -> auto-match
    match_review_threshold: float = 0.60  # [review,auto) -> needs_review queue; below -> unmatched
    use_embeddings: bool = False
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # --- OCR ---
    ocr_langs: str = "rus+kaz+eng"
    # Local tessdata (rus/kaz traineddata shipped in backend/tessdata)
    tessdata_prefix: Path = BACKEND_ROOT / "tessdata"
    ocr_dpi: int = 300

    # --- Validation ---
    price_anomaly_pct: float = 0.50      # |Δprice| > 50% vs previous version -> anomaly flag
    default_currency: str = "KZT"

    # --- Currency rates file (currency -> KZT, dated) ---
    fx_rates_path: Path = BACKEND_ROOT / "app" / "data" / "fx_rates.json"

    # --- API ---
    cors_origins: list[str] = ["*"]
    api_prefix: str = "/api"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    s = get_settings_uncached()
    return s


def get_settings_uncached() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    (s.data_dir / "originals").mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
