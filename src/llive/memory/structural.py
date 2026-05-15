# SPDX-License-Identifier: Apache-2.0
"""Structural memory (MEM-05) — Kùzu-backed graph store.

Bipartite-ish schema:
- ``MemoryNode``  : (id, memory_type, zone, payload_json, embedding_blob, created_at, provenance_json)
- ``MemoryEdge``  : (src_id, dst_id, rel_type, weight, provenance_json, created_at)

Relation types (``rel_type``): ``derived_from / contradicts / generalizes /
temporal_after / co_occurs_with / linked_concept``.

The Kùzu Python binding is required at runtime; install via ``pip install
llmesh-llive`` (kuzu is a core dependency in v0.2.0).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import kuzu

from llive.memory.provenance import Provenance


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _default_db_path() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "memory" / "structural.kuzu"


VALID_NODE_TYPES = {"semantic", "episodic", "structural", "parameter", "concept"}
VALID_EDGE_TYPES = {
    "derived_from",
    "contradicts",
    "generalizes",
    "temporal_after",
    "co_occurs_with",
    "linked_concept",
}


@dataclass
class GraphNode:
    id: str
    memory_type: str
    zone: str = "trusted"
    payload: dict[str, Any] = field(default_factory=dict)
    provenance: Provenance | None = None
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class GraphEdge:
    src_id: str
    dst_id: str
    rel_type: str
    weight: float = 1.0
    provenance: Provenance | None = None
    created_at: datetime = field(default_factory=_utcnow)


class StructuralMemory:
    """Kùzu wrapper for the L5 structural memory layer."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = kuzu.Database(str(self.db_path))
        self._conn = kuzu.Connection(self._db)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        # Kùzu has no IF NOT EXISTS for tables in older versions; rely on idempotent retries.
        try:
            self._conn.execute(
                "CREATE NODE TABLE MemoryNode("
                "id STRING, "
                "memory_type STRING, "
                "zone STRING, "
                "payload STRING, "
                "provenance STRING, "
                "created_at TIMESTAMP, "
                "PRIMARY KEY(id))"
            )
        except RuntimeError as e:  # pragma: no cover - idempotent CREATE TABLE
            if "already exists" not in str(e).lower():
                raise
        try:
            self._conn.execute(
                "CREATE REL TABLE MemoryEdge(FROM MemoryNode TO MemoryNode, "
                "rel_type STRING, weight DOUBLE, provenance STRING, created_at TIMESTAMP)"
            )
        except RuntimeError as e:  # pragma: no cover - idempotent CREATE TABLE
            if "already exists" not in str(e).lower():
                raise

    # -- node operations --------------------------------------------------

    def add_node(
        self,
        memory_type: str,
        payload: dict[str, Any] | None = None,
        zone: str = "trusted",
        provenance: Provenance | None = None,
        node_id: str | None = None,
    ) -> str:
        if memory_type not in VALID_NODE_TYPES:
            raise ValueError(f"invalid memory_type {memory_type!r}; must be one of {VALID_NODE_TYPES}")
        nid = node_id or uuid.uuid4().hex
        payload_json = json.dumps(payload or {})
        provenance_json = provenance.to_json() if provenance else "{}"
        with self._lock:
            self._conn.execute(
                "CREATE (:MemoryNode {id: $id, memory_type: $mt, zone: $z, "
                "payload: $p, provenance: $prov, created_at: $ts})",
                {"id": nid, "mt": memory_type, "z": zone, "p": payload_json, "prov": provenance_json, "ts": _utcnow()},
            )
        return nid

    def get_node(self, node_id: str) -> GraphNode | None:
        with self._lock:
            result = self._conn.execute(
                "MATCH (n:MemoryNode) WHERE n.id = $id "
                "RETURN n.id, n.memory_type, n.zone, n.payload, n.provenance, n.created_at",
                {"id": node_id},
            )
            if not result.has_next():
                return None
            row = result.get_next()
        prov_data = json.loads(row[4]) if row[4] else None
        prov = Provenance.model_validate(prov_data) if prov_data else None
        return GraphNode(
            id=row[0],
            memory_type=row[1],
            zone=row[2],
            payload=json.loads(row[3]) if row[3] else {},
            provenance=prov,
            created_at=row[5] if isinstance(row[5], datetime) else datetime.fromisoformat(str(row[5])),
        )

    def list_nodes(self, memory_type: str | None = None, limit: int = 100) -> list[GraphNode]:
        clauses = ""
        params: dict[str, Any] = {"lim": int(limit)}
        if memory_type is not None:
            if memory_type not in VALID_NODE_TYPES:
                raise ValueError(f"invalid memory_type {memory_type!r}")
            clauses = "WHERE n.memory_type = $mt "
            params["mt"] = memory_type
        with self._lock:
            result = self._conn.execute(
                "MATCH (n:MemoryNode) "
                + clauses
                + "RETURN n.id, n.memory_type, n.zone, n.payload, n.provenance, n.created_at LIMIT $lim",
                params,
            )
            rows: list[GraphNode] = []
            while result.has_next():
                row = result.get_next()
                prov_data = json.loads(row[4]) if row[4] else None
                prov = Provenance.model_validate(prov_data) if prov_data else None
                rows.append(
                    GraphNode(
                        id=row[0],
                        memory_type=row[1],
                        zone=row[2],
                        payload=json.loads(row[3]) if row[3] else {},
                        provenance=prov,
                        created_at=row[5] if isinstance(row[5], datetime) else datetime.fromisoformat(str(row[5])),
                    )
                )
            return rows

    def delete_node(self, node_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "MATCH (n:MemoryNode) WHERE n.id = $id DETACH DELETE n",
                {"id": node_id},
            )

    # -- edge operations --------------------------------------------------

    def add_edge(
        self,
        src_id: str,
        dst_id: str,
        rel_type: str,
        weight: float = 1.0,
        provenance: Provenance | None = None,
    ) -> None:
        if rel_type not in VALID_EDGE_TYPES:
            raise ValueError(f"invalid rel_type {rel_type!r}; must be one of {VALID_EDGE_TYPES}")
        provenance_json = provenance.to_json() if provenance else "{}"
        with self._lock:
            self._conn.execute(
                "MATCH (a:MemoryNode), (b:MemoryNode) "
                "WHERE a.id = $sid AND b.id = $did "
                "CREATE (a)-[:MemoryEdge {rel_type: $rt, weight: $w, provenance: $prov, created_at: $ts}]->(b)",
                {"sid": src_id, "did": dst_id, "rt": rel_type, "w": float(weight), "prov": provenance_json, "ts": _utcnow()},
            )

    def query_neighbors(
        self,
        node_id: str,
        rel_type: str | None = None,
        direction: str = "out",
        limit: int = 100,
        min_weight: float | None = None,
    ) -> list[GraphNode]:
        if direction not in ("out", "in", "both"):
            raise ValueError("direction must be 'out', 'in', or 'both'")
        params: dict[str, Any] = {"id": node_id, "lim": int(limit)}
        if rel_type is not None and rel_type not in VALID_EDGE_TYPES:
            raise ValueError(f"invalid rel_type {rel_type!r}")
        cond_parts = ["n.id = $id"]
        if rel_type is not None:
            cond_parts.append("e.rel_type = $rt")
            params["rt"] = rel_type
        if min_weight is not None:  # pragma: no cover - optional weight filter
            cond_parts.append("e.weight >= $minw")
            params["minw"] = float(min_weight)
        cond = " WHERE " + " AND ".join(cond_parts)
        if direction == "out":
            pat = "(n:MemoryNode)-[e:MemoryEdge]->(m:MemoryNode)"
        elif direction == "in":
            pat = "(m:MemoryNode)-[e:MemoryEdge]->(n:MemoryNode)"
        else:  # both
            pat = "(n:MemoryNode)-[e:MemoryEdge]-(m:MemoryNode)"
        with self._lock:
            result = self._conn.execute(
                "MATCH " + pat + cond +
                " RETURN m.id, m.memory_type, m.zone, m.payload, m.provenance, m.created_at, e.weight"
                " ORDER BY e.weight DESC LIMIT $lim",
                params,
            )
            rows: list[GraphNode] = []
            while result.has_next():
                row = result.get_next()
                prov_data = json.loads(row[4]) if row[4] else None
                prov = Provenance.model_validate(prov_data) if prov_data else None
                rows.append(
                    GraphNode(
                        id=row[0],
                        memory_type=row[1],
                        zone=row[2],
                        payload=json.loads(row[3]) if row[3] else {},
                        provenance=prov,
                        created_at=row[5] if isinstance(row[5], datetime) else datetime.fromisoformat(str(row[5])),
                    )
                )
            return rows

    def count_nodes(self, memory_type: str | None = None) -> int:
        clauses = ""
        params: dict[str, Any] = {}
        if memory_type is not None:
            clauses = "WHERE n.memory_type = $mt "
            params["mt"] = memory_type
        with self._lock:
            result = self._conn.execute(
                "MATCH (n:MemoryNode) " + clauses + "RETURN COUNT(n)", params
            )
            (n,) = result.get_next()
        return int(n)

    def close(self) -> None:
        # Kùzu's Python binding closes implicitly on GC, but expose a hook for tests.
        with self._lock:
            self._conn = None  # type: ignore[assignment]
            self._db = None  # type: ignore[assignment]

    def __enter__(self) -> StructuralMemory:
        return self

    def __exit__(self, *_args) -> None:
        self.close()
