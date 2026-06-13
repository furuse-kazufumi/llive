# SPDX-License-Identifier: Apache-2.0
"""GraphRAG ``Edge`` — a directed, typed, weighted relation.

Edges connect two :class:`~llive.memory.graph_rag.node.Node` instances by
their string ``id``. The ``relation`` field is intentionally free-form —
GraphRAG does not enforce a closed schema like the structural-memory
layer (``derived_from`` / ``contradicts`` / ``generalizes`` / etc.) so
that callers can express domain-specific relations such as
``cites`` / ``part_of`` / ``mentioned_in``.

``weight`` is a positive float (default ``1.0``). It multiplies the
graph-proximity term in the hybrid retrieval score and may be tuned per
relation type.

``evidence`` is a list of opaque references (e.g. memory entry IDs,
URLs, paragraph hashes) supporting the edge — used for provenance and
future contradiction handling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Edge:
    """A directed, weighted, typed edge between two nodes.

    Attributes
    ----------
    src:
        Source node ``id``.
    dst:
        Destination node ``id``.
    relation:
        Free-form relation label (e.g. ``cites``, ``part_of``,
        ``mentioned_in``, ``contradicts``).
    weight:
        Positive float used by the proximity scorer. ``1.0`` by default.
    evidence:
        Opaque provenance references (memory IDs, URLs, etc.).
    """

    src: str
    dst: str
    relation: str
    weight: float = 1.0
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "src": self.src,
            "dst": self.dst,
            "relation": self.relation,
            "weight": float(self.weight),
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Edge:
        return cls(
            src=str(d["src"]),
            dst=str(d["dst"]),
            relation=str(d.get("relation", "related")),
            weight=float(d.get("weight", 1.0)),
            evidence=list(d.get("evidence", [])),
        )
