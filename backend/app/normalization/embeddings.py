"""Semantic index backed by sentence-transformers (e5 family).

This is the LANE-2 embedding cache. It is designed to degrade gracefully: if
the library / model is unavailable, embeddings are disabled, or anything fails,
``available()`` returns False and the matcher simply skips the embedding stage.
Importing this module never does heavy work (no torch / numpy at import time).

For the e5 models the *asymmetric* prompts matter and are wired in here:
  * catalog entries are encoded as  ``"passage: <text>"``
  * incoming raw names are encoded as ``"query: <text>"``

The encoded, L2-normalized catalog matrix is cached to a **uniquely-named**
``.npz`` file (keyed by model + passage-prefix + the exact catalog texts) so the
slow encode runs once per catalog. A different catalog (or model) hashes to a
different file, so stale matrices never collide and never need manual clearing.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

# Where catalog embedding matrices are cached. Kept next to this module so it is
# writable in dev; each (model, catalog) pair gets its own uniquely-named file.
_CACHE_DIR = Path(__file__).resolve().parent / "_emb_cache"

# e5 asymmetric prompts (REQUIRED for intfloat/multilingual-e5-*). The trailing
# space is part of the published convention.
_DEFAULT_QUERY_PREFIX = "query: "
_DEFAULT_PASSAGE_PREFIX = "passage: "

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class EmbeddingIndex:
    """Lazily-loaded cosine-similarity index over catalog texts.

    Nothing heavy happens in ``__init__``; the model is only imported/loaded the
    first time it is actually needed (a cache miss in ``build``, or any
    ``query``).
    """

    def __init__(
        self,
        model_name: str,
        enabled: bool = True,
        *,
        query_prefix: str = _DEFAULT_QUERY_PREFIX,
        passage_prefix: str = _DEFAULT_PASSAGE_PREFIX,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.model_name = model_name
        self.enabled = enabled
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix
        self.cache_dir = Path(cache_dir) if cache_dir is not None else _CACHE_DIR
        self._model = None  # sentence_transformers.SentenceTransformer | None
        self._emb = None    # numpy.ndarray (n_texts, dim), L2-normalized float32
        self._n = 0
        # Populated by build(): the on-disk path of the cached catalog matrix.
        self.cache_path: Path | None = None
        self.loaded_from_cache = False

    # -- internal ----------------------------------------------------------- #
    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        if not self.enabled:
            return False
        try:  # Lazy import — never required at module import time.
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception:
            return False
        try:
            self._model = SentenceTransformer(self.model_name)
        except Exception:
            self._model = None
            return False
        return True

    def _cache_key(self, texts: list[str]) -> str:
        """Stable digest of (model, passage prefix, exact catalog texts)."""
        h = hashlib.sha256()
        h.update(self.model_name.encode("utf-8"))
        h.update(b"\x00")
        h.update(self.passage_prefix.encode("utf-8"))
        h.update(b"\x00")
        for t in texts:
            h.update(str(t).encode("utf-8"))
            h.update(b"\x01")
        return h.hexdigest()[:16]

    def _cache_file(self, texts: list[str]) -> Path:
        slug = _SLUG_RE.sub("-", self.model_name.lower()).strip("-")[:48]
        return self.cache_dir / f"catalog_emb_{slug}_{self._cache_key(texts)}.npz"

    # -- public API --------------------------------------------------------- #
    def build(self, texts: list[str]) -> bool:
        """Encode ``texts`` into a normalized matrix (cached). Returns success.

        On a cache hit the matrix is loaded from disk and the (heavy) model is
        not touched at all — it is then loaded lazily on the first ``query``.
        """
        self._emb = None
        self._n = 0
        self.loaded_from_cache = False
        if not texts:
            return False
        try:
            import numpy as np  # numpy ships with sentence-transformers.
        except Exception:
            return False

        cache_file = self._cache_file(texts)
        self.cache_path = cache_file

        # 1) Try the on-disk cache first.
        if cache_file.exists():
            try:
                with np.load(cache_file) as data:
                    emb = np.asarray(data["emb"])
                if emb.ndim == 2 and emb.shape[0] == len(texts):
                    self._emb = emb
                    self._n = len(texts)
                    self.loaded_from_cache = True
                    return True
            except Exception:
                pass  # corrupt / incompatible cache -> recompute below.

        # 2) Cache miss: encode with the model (the slow path).
        if not self._load_model():
            return False
        try:
            inputs = [self.passage_prefix + str(t) for t in texts]
            emb = self._model.encode(  # type: ignore[union-attr]
                inputs, convert_to_numpy=True, show_progress_bar=False
            )
            emb = np.asarray(emb, dtype="float32")
            norms = np.linalg.norm(emb, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            emb = emb / norms
            self._emb = emb
            self._n = len(texts)
        except Exception:
            self._emb = None
            self._n = 0
            return False

        # 3) Best-effort persist (never fatal).
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            np.savez(cache_file, emb=self._emb)
        except Exception:
            pass
        return True

    def available(self) -> bool:
        """True only when a built, queryable matrix exists."""
        return self.enabled and self._emb is not None and self._n > 0

    def query(self, text: str, top_k: int = 5) -> list[tuple[int, float]]:
        """Return ``[(row_index, cosine in [0,1]), ...]`` best-first.

        Loads the model lazily (needed even after a cache hit, since the raw
        name still has to be encoded). Returns ``[]`` on any failure.
        """
        if not self.available() or not text:
            return []
        if not self._load_model():
            return []
        try:
            import numpy as np

            q = self._model.encode(  # type: ignore[union-attr]
                [self.query_prefix + str(text)],
                convert_to_numpy=True,
                show_progress_bar=False,
            )[0]
            q = np.asarray(q, dtype="float32")
            qn = np.linalg.norm(q)
            if qn == 0:
                return []
            q = q / qn
            sims = self._emb @ q  # type: ignore[operator]  # cosine, in [-1, 1]
            k = min(max(1, top_k), self._n)
            # argpartition for the top-k, then sort just that slice descending.
            idx = np.argpartition(-sims, k - 1)[:k]
            idx = idx[np.argsort(-sims[idx])]
            out: list[tuple[int, float]] = []
            for i in idx:
                # Clamp cosine into [0,1] (negatives mean "unrelated").
                score = float(max(0.0, min(1.0, sims[int(i)])))
                out.append((int(i), score))
            return out
        except Exception:
            return []
