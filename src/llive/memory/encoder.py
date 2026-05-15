# SPDX-License-Identifier: Apache-2.0
"""Embedding encoder for semantic memory.

Default backend: `sentence-transformers/all-MiniLM-L6-v2` (384 dim, local).
Fallback backend: a deterministic hash-based pseudo-embedding (for environments
without torch / sentence-transformers, e.g. lightweight CI). Real production
work should install the `torch` extra: ``pip install llmesh-llive[torch]``.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Sequence

import numpy as np

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIM = 384
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _hash_embed(text: str, dim: int) -> np.ndarray:
    """Deterministic hash-based bag-of-tokens pseudo embedding.

    NOT semantically meaningful — only suitable for tests / fallback. Tokens are
    hashed into a fixed-size feature space; weights are sub-linear in count so
    repeated tokens don't dominate.
    """
    vec = np.zeros(dim, dtype=np.float32)
    tokens = _TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return vec
    counts: dict[int, int] = {}
    for tok in tokens:
        h = int.from_bytes(hashlib.blake2s(tok.encode("utf-8"), digest_size=4).digest(), "little")
        idx = h % dim
        counts[idx] = counts.get(idx, 0) + 1
    for idx, c in counts.items():
        vec[idx] = np.log1p(c)
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


class MemoryEncoder:
    """Wraps sentence-transformers (preferred) or a hash fallback (CI-safe)."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        dim: int | None = None,
        prefer_fallback: bool | None = None,
    ) -> None:
        self.model_name = model_name
        self._model = None
        self._fallback_dim = dim or DEFAULT_DIM
        env_flag = os.environ.get("LLIVE_EMBED_FALLBACK", "")
        force_fallback = (
            prefer_fallback if prefer_fallback is not None else env_flag.lower() in ("1", "true", "yes")
        )
        if not force_fallback:
            self._try_load()

    def _try_load(self) -> None:  # pragma: no cover - requires sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        except Exception:
            self._model = None

    @property
    def dim(self) -> int:
        if self._model is not None:  # pragma: no cover - requires sentence-transformers
            return int(self._model.get_sentence_embedding_dimension() or DEFAULT_DIM)
        return self._fallback_dim

    @property
    def is_real(self) -> bool:
        return self._model is not None

    def encode(self, texts: str | Sequence[str]) -> np.ndarray:
        single = isinstance(texts, str)
        items: list[str] = [texts] if single else list(texts)
        if not items:
            return np.zeros((0, self.dim), dtype=np.float32)
        if self._model is not None:  # pragma: no cover - requires sentence-transformers
            arr = np.asarray(
                self._model.encode(items, normalize_embeddings=True, show_progress_bar=False),
                dtype=np.float32,
            )
        else:
            arr = np.stack([_hash_embed(t, self._fallback_dim) for t in items], axis=0)
        if single:
            return arr[0]
        return arr
