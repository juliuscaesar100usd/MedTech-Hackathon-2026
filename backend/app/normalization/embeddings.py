"""Optional semantic index backed by sentence-transformers.

The whole module is designed to degrade gracefully: if the library is not
installed, or ``settings.use_embeddings`` is False, or the model fails to load,
``EmbeddingIndex.available()`` returns False and the matcher simply skips the
embedding stage. Importing this module never crashes.
"""
from __future__ import annotations


class EmbeddingIndex:
    """Lazily-loaded cosine-similarity index over catalog texts.

    Nothing heavy happens in ``__init__``; the model is only imported/loaded
    inside ``build`` (and only when ``enabled`` is True).
    """

    def __init__(self, model_name: str, enabled: bool = True) -> None:
        self.model_name = model_name
        self.enabled = enabled
        self._model = None  # sentence_transformers.SentenceTransformer | None
        self._emb = None  # numpy.ndarray (n_texts, dim), L2-normalized
        self._n = 0

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

    # -- public API --------------------------------------------------------- #
    def build(self, texts: list[str]) -> bool:
        """Encode ``texts`` into a normalized matrix. Returns success flag."""
        if not texts or not self._load_model():
            return False
        try:
            import numpy as np  # sentence-transformers always pulls numpy.

            emb = self._model.encode(  # type: ignore[union-attr]
                texts, convert_to_numpy=True, show_progress_bar=False
            )
            norms = np.linalg.norm(emb, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._emb = emb / norms
            self._n = len(texts)
        except Exception:
            self._emb = None
            self._n = 0
            return False
        return True

    def available(self) -> bool:
        """True only when a built, queryable index exists."""
        return self.enabled and self._emb is not None and self._n > 0

    def query(self, text: str, top_k: int = 5) -> list[tuple[int, float]]:
        """Return ``[(row_index, cosine_score in [0,1]), ...]`` best-first."""
        if not self.available() or not text:
            return []
        try:
            import numpy as np

            q = self._model.encode(  # type: ignore[union-attr]
                [text], convert_to_numpy=True, show_progress_bar=False
            )[0]
            qn = np.linalg.norm(q)
            if qn == 0:
                return []
            q = q / qn
            sims = self._emb @ q  # type: ignore[operator]  # cosine, in [-1,1]
            k = min(top_k, self._n)
            # argpartition for the top-k, then sort that slice descending.
            idx = np.argpartition(-sims, k - 1)[:k]
            idx = idx[np.argsort(-sims[idx])]
            out: list[tuple[int, float]] = []
            for i in idx:
                # Clamp cosine into [0,1] (negatives mean "unrelated").
                score = float(max(0.0, min(1.0, (sims[int(i)] + 0.0))))
                out.append((int(i), score))
            return out
        except Exception:
            return []
