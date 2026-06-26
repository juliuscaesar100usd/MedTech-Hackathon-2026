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
    # Embeddings ON by default (lane 2 semantic stage). The model loads from a
    # baked, OFFLINE cache (no ~1GB download at runtime) — see embeddings_* below
    # and scripts/bake_embedding_model.py.
    use_embeddings: bool = True
    embedding_model: str = "intfloat/multilingual-e5-base"
    # Lighter fallback if size is a concern: set EMBEDDING_MODEL=intfloat/multilingual-e5-small.
    # Load the model from this local cache and forbid network fetches (offline judging).
    embeddings_offline: bool = True
    embeddings_model_cache: Path = BACKEND_ROOT / "model_cache"

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

    # --- AI assistant / chatbot ---
    # The assistant parses free-text preferences into a structured query and
    # returns the matching catalog results. It is OFFLINE-FIRST: a deterministic
    # rule-based parser always works. When an Anthropic API key is present AND
    # the ``anthropic`` SDK is installed, the assistant additionally uses Claude
    # to extract preferences for messier / more conversational input; on any
    # failure it transparently falls back to the rule-based parser.
    assistant_enabled: bool = True
    # Set ANTHROPIC_API_KEY in the environment (or .env) to activate the LLM tier.
    anthropic_api_key: str | None = None
    assistant_model: str = "claude-opus-4-8"
    # Max catalog results the assistant returns per message.
    assistant_max_results: int = 5

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def assistant_llm_configured(self) -> bool:
        """True when an Anthropic API key is available for the LLM tier."""
        import os

        return bool(self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))


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
