# SPDX-License-Identifier: Apache-2.0
"""Semantic memory (MEM-01) — Faiss IP index + JSONL row store.

Default backend: faiss-cpu IndexFlatIP (L2-normalized embeddings → cosine).
Fallback backend: pure-numpy nearest neighbor (no faiss required) — used in
environments without faiss-cpu (e.g. Windows CI without prebuilt wheels).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from llive.memory.provenance import Provenance

try:  # pragma: no cover - import branch tested separately
    import faiss  # type: ignore[import-not-found]

    _HAS_FAISS = True
except Exception:  # pragma: no cover - exercised when faiss missing
    faiss = None  # type: ignore[assignment]
    _HAS_FAISS = False


def _default_data_dir() -> Path:
    env = os.environ.get("LLIVE_DATA_DIR")
    if env:
        return Path(env) / "memory" / "semantic"
    return Path("D:/data/llive/memory/semantic")


@dataclass
class SemanticHit:
    entry_id: str
    score: float
    content: str
    provenance: Provenance


@dataclass
class _Entry:
    entry_id: str
    content: str
    embedding: np.ndarray
    provenance: Provenance


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm == 0:
        return vec
    return vec / norm


class SemanticMemory:
    """In-memory + persistent semantic memory.

    Persistence layout:
        <data_dir>/
            index.faiss   (or  index.npy   if faiss is unavailable)
            rows.jsonl
    """

    def __init__(
        self,
        dim: int,
        data_dir: Path | str | None = None,
        use_faiss: bool | None = None,
    ) -> None:
        self.dim = int(dim)
        self.data_dir = Path(data_dir) if data_dir else _default_data_dir()
        if use_faiss is None:
            use_faiss = _HAS_FAISS
        self.use_faiss = bool(use_faiss and _HAS_FAISS)
        self._lock = threading.Lock()
        self._entries: list[_Entry] = []
        if self.use_faiss:
            self._index = faiss.IndexFlatIP(self.dim)  # type: ignore[union-attr]
        else:
            self._index = None
            self._matrix: np.ndarray | None = None  # (N, dim)

    # -- public api --------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    def write(self, content: str, embedding: np.ndarray, provenance: Provenance) -> str:
        if embedding.shape[-1] != self.dim:
            raise ValueError(f"embedding dim {embedding.shape[-1]} != index dim {self.dim}")
        vec = _l2_normalize(np.asarray(embedding, dtype=np.float32).reshape(self.dim))
        entry_id = uuid.uuid4().hex
        entry = _Entry(entry_id=entry_id, content=content, embedding=vec, provenance=provenance)
        with self._lock:
            self._entries.append(entry)
            self._refresh_search_state_locked(new_vec=vec)
        return entry_id

    def query(self, embedding: np.ndarray, top_k: int = 5) -> list[SemanticHit]:
        if not self._entries:
            return []
        if embedding.shape[-1] != self.dim:
            raise ValueError(f"query dim {embedding.shape[-1]} != index dim {self.dim}")
        q = _l2_normalize(np.asarray(embedding, dtype=np.float32).reshape(1, self.dim))
        with self._lock:
            if self.use_faiss:  # pragma: no cover - requires faiss-cpu
                scores, idxs = self._index.search(q, min(top_k, len(self._entries)))  # type: ignore[union-attr]
                pairs = list(zip(idxs[0].tolist(), scores[0].tolist(), strict=False))
            else:
                assert self._matrix is not None
                sims = (self._matrix @ q.T).flatten()
                order = np.argsort(-sims)[:top_k]
                pairs = [(int(i), float(sims[i])) for i in order]
            hits: list[SemanticHit] = []
            for idx, score in pairs:
                if idx < 0 or idx >= len(self._entries):
                    continue
                e = self._entries[idx]
                hits.append(SemanticHit(entry_id=e.entry_id, score=float(score), content=e.content, provenance=e.provenance))
            return hits

    def all_embeddings(self) -> np.ndarray:
        with self._lock:
            if not self._entries:
                return np.zeros((0, self.dim), dtype=np.float32)
            return np.stack([e.embedding for e in self._entries], axis=0)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            if self.use_faiss:  # pragma: no cover - requires faiss-cpu
                self._index.reset()  # type: ignore[union-attr]
            else:
                self._matrix = None

    # -- persistence -------------------------------------------------------

    def save(self) -> None:
        with self._lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            rows_path = self.data_dir / "rows.jsonl"
            with rows_path.open("w", encoding="utf-8") as fh:
                for e in self._entries:
                    fh.write(
                        json.dumps(
                            {
                                "entry_id": e.entry_id,
                                "content": e.content,
                                "embedding": e.embedding.tolist(),
                                "provenance": json.loads(e.provenance.to_json()),
                            }
                        )
                        + "\n"
                    )

    def load(self) -> None:
        rows_path = self.data_dir / "rows.jsonl"
        if not rows_path.exists():
            return
        with self._lock:
            self._entries.clear()
            if self.use_faiss:  # pragma: no cover - requires faiss-cpu
                self._index.reset()  # type: ignore[union-attr]
            else:
                self._matrix = None
            with rows_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    row = json.loads(line)
                    emb = np.asarray(row["embedding"], dtype=np.float32)
                    prov = Provenance.model_validate(row["provenance"])
                    self._entries.append(
                        _Entry(entry_id=row["entry_id"], content=row["content"], embedding=emb, provenance=prov)
                    )
            if self._entries:
                mat = np.stack([e.embedding for e in self._entries], axis=0)
                if self.use_faiss:  # pragma: no cover - requires faiss-cpu
                    self._index.add(mat)  # type: ignore[union-attr]
                else:
                    self._matrix = mat

    # -- internals ---------------------------------------------------------

    def _refresh_search_state_locked(self, new_vec: np.ndarray) -> None:
        if self.use_faiss:  # pragma: no cover - requires faiss-cpu
            self._index.add(new_vec.reshape(1, self.dim))  # type: ignore[union-attr]
        else:
            row = new_vec.reshape(1, self.dim)
            if self._matrix is None:
                self._matrix = row
            else:
                self._matrix = np.concatenate([self._matrix, row], axis=0)
