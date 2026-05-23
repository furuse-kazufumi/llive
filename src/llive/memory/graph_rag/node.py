# SPDX-License-Identifier: Apache-2.0
"""GraphRAG ``Node`` — a single graph vertex for hybrid retrieval.

A Node represents an addressable item in the knowledge graph that lives
alongside (and is referenced from) the long-term memory layer. It carries:

* an opaque ``id`` (UUID hex, slug, or any caller-supplied stable key),
* a ``kind`` discriminator restricted to ``concept`` / ``entity`` /
  ``memory`` / ``event`` so the GraphRAG store can apply kind-aware
  scoring later,
* a free-form ``payload`` (text content, source URI, metadata),
* an optional ``embedding`` (numpy float32 vector) used by the hybrid
  retrieval scorer in :mod:`llive.memory.graph_rag.store`,
* a ``created_at`` timestamp for recency-decay scoring (future).

Notes
-----
The embedding type is ``np.ndarray | None``. Nodes without an embedding
are still reachable via graph-only traversal (``neighbors``) but do not
contribute to the embedding-similarity term of the hybrid score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import numpy as np

NodeKind = Literal["concept", "entity", "memory", "event"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Node:
    """A vertex in the GraphRAG knowledge graph.

    Attributes
    ----------
    id:
        Stable identifier (caller-supplied or UUID hex).
    kind:
        One of ``concept`` / ``entity`` / ``memory`` / ``event``.
    payload:
        Free-form metadata dict (text, source URIs, tags, etc.).
    embedding:
        Optional numpy float32 vector for cosine similarity ranking.
    created_at:
        UTC timestamp; defaults to now.
    """

    id: str
    kind: NodeKind
    payload: dict[str, Any] = field(default_factory=dict)
    embedding: np.ndarray | None = None
    created_at: datetime = field(default_factory=_utcnow)

    # -- serialization helpers ---------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly dict representation (embedding -> list of floats)."""
        return {
            "id": self.id,
            "kind": self.kind,
            "payload": dict(self.payload),
            "embedding": None if self.embedding is None else [float(x) for x in self.embedding.tolist()],
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Node:
        emb_raw = d.get("embedding")
        emb = None if emb_raw is None else np.asarray(emb_raw, dtype=np.float32)
        ts_raw = d.get("created_at")
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw)
        elif isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            ts = _utcnow()
        return cls(
            id=str(d["id"]),
            kind=d.get("kind", "concept"),  # type: ignore[arg-type]
            payload=dict(d.get("payload", {})),
            embedding=emb,
            created_at=ts,
        )
