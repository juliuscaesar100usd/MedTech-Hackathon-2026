"""Bake the sentence-transformers embedding model into the OFFLINE cache.

Run ONCE with network access; afterwards the matcher loads the model from
``backend/model_cache/`` with no network (``embeddings_offline=True``), so there
is no ~1GB download at judging time.

    # default model (intfloat/multilingual-e5-base)
    python -m scripts.bake_embedding_model

    # lighter fallback if size/RAM is a concern
    python -m scripts.bake_embedding_model intfloat/multilingual-e5-small

NOTE: the model weights (~1.1GB for e5-base, ~0.47GB for e5-small) exceed
GitHub's 100MB/file limit, so ``backend/model_cache/`` is gitignored. To ship
the weights inside the repo instead, use Git LFS; otherwise run this script as a
one-time setup step on the judging machine (with network), then run fully offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.config import settings

DEFAULT_MODEL = "intfloat/multilingual-e5-base"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    model_name = argv[0] if argv else DEFAULT_MODEL
    cache_dir = Path(settings.embeddings_model_cache)
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: sentence-transformers not installed: {exc}")
        return 1

    print(f"Downloading {model_name} into {cache_dir} (network required, one time)…")
    SentenceTransformer(model_name, cache_folder=str(cache_dir))
    print("Done. The matcher will now load it OFFLINE (embeddings_offline=True).")
    print(f"Cache: {cache_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
