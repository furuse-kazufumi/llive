"""Dynamic edge weight updater (LLW-AC-10).

Weights stored in :class:`StructuralMemory` MemoryEdges are not static —
they must react to actual Wiki usage. This module wires the 5 update
triggers from LLW-AC-10:

* ``on_read_hit``           — memory_read on a page reinforces its outgoing
                              ``linked_concept`` edges.
* ``on_consolidation``       — Consolidator drops a re-derived weight in
                              after each Wiki Compile cycle (handled by
                              :class:`llive.memory.consolidation.Consolidator`).
* ``apply_time_decay``       — exponential decay applied by a cron job.
* ``on_contradiction``       — diversity / merge rejection downweighs the
                              proposed link.
* ``on_surprise``            — high surprise injections boost adjacent
                              edges so fresh evidence becomes a hub.

Each call writes a JSONL audit row to ``logs/edge_weight.jsonl`` so the
weight history is reviewable from llove HITL or external tooling.

Kùzu does not yet support partial UPDATE through our wrapper, so weight
changes are realised by *deleting* and *re-inserting* the same edge with
the new weight. Pruning (w < min_weight_keep) skips the re-insert.
"""

from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from llive.memory.structural import VALID_EDGE_TYPES, StructuralMemory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_log_path() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "logs" / "edge_weight.jsonl"


@dataclass
class EdgeWeightConfig:
    alpha_read: float = 0.02
    alpha_penalty: float = 0.1
    alpha_surprise: float = 0.15
    decay_tau_days: dict[str, float] = field(
        default_factory=lambda: {
            "linked_concept": 30.0,
            "co_occurs_with": 7.0,
            "temporal_after": 14.0,
        }
    )
    min_weight_keep: float = 0.05


@dataclass
class _EdgeRow:
    src_id: str
    dst_id: str
    rel_type: str
    weight: float
    created_at: datetime


class EdgeWeightUpdater:
    """Apply dynamic weight changes to MemoryEdges in StructuralMemory."""

    def __init__(
        self,
        structural: StructuralMemory,
        config: EdgeWeightConfig | None = None,
        log_path: Path | str | None = None,
    ) -> None:
        self.structural = structural
        self.config = config or EdgeWeightConfig()
        self.log_path = Path(log_path) if log_path is not None else _default_log_path()
        self._lock = threading.Lock()

    # -- public hooks -----------------------------------------------------

    def on_read_hit(self, src_id: str, neighbor_ids: Iterable[str]) -> int:
        """Reinforce outgoing linked_concept edges from ``src_id`` to each neighbour."""
        n = 0
        for dst_id in neighbor_ids:
            if self._adjust(src_id, dst_id, "linked_concept", self.config.alpha_read, reason="read_hit"):
                n += 1
        return n

    def on_contradiction(self, src_id: str, dst_id: str) -> bool:
        return self._adjust(
            src_id, dst_id, "linked_concept", -self.config.alpha_penalty, reason="contradiction"
        )

    def on_surprise(
        self,
        page_id: str,
        surprise: float,
        neighbor_ids: Iterable[str],
    ) -> int:
        delta = self.config.alpha_surprise * float(surprise)
        n = 0
        for dst_id in neighbor_ids:
            if self._adjust(page_id, dst_id, "linked_concept", delta, reason="surprise"):
                n += 1
        return n

    def apply_time_decay(self, now: datetime | None = None) -> int:
        """Apply exp(-Δt / τ) decay to every decayable edge."""
        ref = now or _utcnow()
        rows = self._fetch_all_edges(rel_types=tuple(self.config.decay_tau_days.keys()))
        updates = 0
        for row in rows:
            tau = self.config.decay_tau_days.get(row.rel_type)
            if tau is None or tau <= 0:
                continue
            age_days = max(0.0, (ref - row.created_at).total_seconds() / 86400.0)
            factor = math.exp(-age_days / tau)
            new_weight = row.weight * factor
            if self._replace_edge(row, new_weight, reason="time_decay"):
                updates += 1
        return updates

    def prune(self, threshold: float | None = None) -> int:
        """Delete edges whose weight is below ``threshold`` (default ``min_weight_keep``)."""
        thr = self.config.min_weight_keep if threshold is None else float(threshold)
        rows = self._fetch_all_edges()
        deleted = 0
        for row in rows:
            if row.weight < thr:
                self._delete_edge(row.src_id, row.dst_id, row.rel_type)
                self._log({
                    "op": "prune",
                    "src": row.src_id,
                    "dst": row.dst_id,
                    "rel_type": row.rel_type,
                    "old_weight": row.weight,
                    "new_weight": 0.0,
                })
                deleted += 1
        return deleted

    # -- internals --------------------------------------------------------

    def _adjust(
        self,
        src_id: str,
        dst_id: str,
        rel_type: str,
        delta: float,
        *,
        reason: str,
    ) -> bool:
        if rel_type not in VALID_EDGE_TYPES:
            raise ValueError(f"invalid rel_type {rel_type!r}")
        row = self._fetch_edge(src_id, dst_id, rel_type)
        if row is None:
            return False
        new_weight = max(0.0, min(1.0, row.weight + float(delta)))
        if new_weight == row.weight:
            return False
        ok = self._replace_edge(row, new_weight, reason=reason)
        return ok

    def _fetch_edge(
        self, src_id: str, dst_id: str, rel_type: str
    ) -> _EdgeRow | None:
        with self._lock:
            result = self.structural._conn.execute(  # type: ignore[attr-defined]
                "MATCH (a:MemoryNode)-[e:MemoryEdge]->(b:MemoryNode) "
                "WHERE a.id = $s AND b.id = $d AND e.rel_type = $r "
                "RETURN e.weight, e.created_at",
                {"s": src_id, "d": dst_id, "r": rel_type},
            )
            if not result.has_next():
                return None
            row = result.get_next()
        return _EdgeRow(
            src_id=src_id, dst_id=dst_id, rel_type=rel_type,
            weight=float(row[0]),
            created_at=row[1] if isinstance(row[1], datetime) else _utcnow(),
        )

    def _fetch_all_edges(
        self, rel_types: tuple[str, ...] | None = None
    ) -> list[_EdgeRow]:
        params: dict[str, Any] = {}
        cond = ""
        if rel_types:
            cond = " WHERE e.rel_type IN $rts"
            params["rts"] = list(rel_types)
        with self._lock:
            result = self.structural._conn.execute(  # type: ignore[attr-defined]
                "MATCH (a:MemoryNode)-[e:MemoryEdge]->(b:MemoryNode)"
                + cond
                + " RETURN a.id, b.id, e.rel_type, e.weight, e.created_at",
                params,
            )
            out: list[_EdgeRow] = []
            while result.has_next():
                row = result.get_next()
                out.append(
                    _EdgeRow(
                        src_id=row[0],
                        dst_id=row[1],
                        rel_type=row[2],
                        weight=float(row[3]),
                        created_at=row[4] if isinstance(row[4], datetime) else _utcnow(),
                    )
                )
            return out

    def _delete_edge(self, src_id: str, dst_id: str, rel_type: str) -> None:
        with self._lock:
            self.structural._conn.execute(  # type: ignore[attr-defined]
                "MATCH (a:MemoryNode)-[e:MemoryEdge]->(b:MemoryNode) "
                "WHERE a.id = $s AND b.id = $d AND e.rel_type = $r DELETE e",
                {"s": src_id, "d": dst_id, "r": rel_type},
            )

    def _replace_edge(self, row: _EdgeRow, new_weight: float, *, reason: str) -> bool:
        old_weight = row.weight
        if new_weight < self.config.min_weight_keep:
            self._delete_edge(row.src_id, row.dst_id, row.rel_type)
            self._log({
                "op": "delete_below_threshold",
                "src": row.src_id,
                "dst": row.dst_id,
                "rel_type": row.rel_type,
                "old_weight": old_weight,
                "new_weight": new_weight,
                "reason": reason,
            })
            return True
        self._delete_edge(row.src_id, row.dst_id, row.rel_type)
        self.structural.add_edge(row.src_id, row.dst_id, row.rel_type, weight=new_weight)
        self._log({
            "op": "adjust",
            "src": row.src_id,
            "dst": row.dst_id,
            "rel_type": row.rel_type,
            "old_weight": old_weight,
            "new_weight": new_weight,
            "reason": reason,
        })
        return True

    def _log(self, payload: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"timestamp": _utcnow().isoformat(), **payload}
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
