"""Dynamic edge weight updater (LLW-AC-10) + exploration balance (LLW-AC-11).

Weights stored in :class:`StructuralMemory` MemoryEdges are not static —
they must react to actual Wiki usage. AC-10 wires the deterministic
triggers:

* ``on_read_hit``       — memory_read reinforces outgoing edges.
* ``apply_time_decay``  — exponential decay applied by a cron job.
* ``on_contradiction``  — diversity / merge rejection downweighs.
* ``on_surprise``       — high surprise injections boost adjacent edges.
* ``prune``             — physically remove dead edges.

AC-11 adds the stochastic balance:

* ``random_boost``       — coin-flip resurrection of dormant edges.
* ``exploration_score``  — UCB1 score combining weight + visit count.
* ``rank_neighbors``     — return neighbours ordered by exploration score.
* Visit counts tracked via :meth:`on_read_hit`.

Each call writes a JSONL audit row to ``logs/edge_weight.jsonl`` so the
weight history is reviewable from llove HITL or external tooling.

Kùzu does not yet support partial UPDATE through our wrapper, so weight
changes are realised by *deleting* and *re-inserting* the same edge with
the new weight. Edges with weight below ``floor_weight`` are physically
deleted; edges between ``floor_weight`` and ``min_weight_keep`` are kept
as *dormant* so ``random_boost`` can resurrect them.
"""

from __future__ import annotations

import json
import math
import os
import random
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
    # --- LLW-AC-11 exploration / exploitation balance ---
    floor_weight: float = 0.02
    """Below this weight an edge is physically deleted (no chance of comeback)."""
    random_boost_probability: float = 0.05
    """Probability that a candidate edge is randomly boosted during ``random_boost``."""
    random_boost_amount: float = 0.05
    """Boost amount applied when an edge wins the random_boost coin flip."""
    ucb_c: float = 1.0
    """Exploration coefficient (UCB1)."""


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
        rng: random.Random | None = None,
    ) -> None:
        self.structural = structural
        self.config = config or EdgeWeightConfig()
        self.log_path = Path(log_path) if log_path is not None else _default_log_path()
        self._lock = threading.Lock()
        # LLW-AC-11 visit tracking (in-memory; Phase 4 will persist on the edge schema)
        self._visit_counts: dict[tuple[str, str, str], int] = {}
        self._rng = rng or random.Random()

    # -- public hooks -----------------------------------------------------

    def on_read_hit(self, src_id: str, neighbor_ids: Iterable[str]) -> int:
        """Reinforce outgoing linked_concept edges from ``src_id`` to each neighbour."""
        n = 0
        for dst_id in neighbor_ids:
            key = (src_id, dst_id, "linked_concept")
            self._visit_counts[key] = self._visit_counts.get(key, 0) + 1
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
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        rows = self._fetch_all_edges(rel_types=tuple(self.config.decay_tau_days.keys()))
        updates = 0
        for row in rows:
            tau = self.config.decay_tau_days.get(row.rel_type)
            if tau is None or tau <= 0:
                continue
            created = row.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (ref - created).total_seconds() / 86400.0)
            factor = math.exp(-age_days / tau)
            new_weight = row.weight * factor
            if self._replace_edge(row, new_weight, reason="time_decay"):
                updates += 1
        return updates

    def prune(self, threshold: float | None = None) -> int:
        """Delete edges whose weight is below ``threshold`` (default ``floor_weight``).

        Note: in AC-11 semantics, edges below ``min_weight_keep`` but above
        ``floor_weight`` are kept as dormant. ``prune`` only deletes those that fell below
        the absolute floor.
        """
        thr = self.config.floor_weight if threshold is None else float(threshold)
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

    # -- LLW-AC-11 exploration ------------------------------------------

    def random_boost(self, rel_types: tuple[str, ...] | None = None) -> int:
        """Stochastically boost edges so dormant branches stay reachable."""
        rows = self._fetch_all_edges(rel_types=rel_types)
        boosted = 0
        for row in rows:
            if self._rng.random() < self.config.random_boost_probability:
                if self._adjust(
                    row.src_id,
                    row.dst_id,
                    row.rel_type,
                    self.config.random_boost_amount,
                    reason="random_boost",
                ):
                    boosted += 1
        return boosted

    def total_visits(self) -> int:
        return int(sum(self._visit_counts.values()))

    def visit_count(self, src_id: str, dst_id: str, rel_type: str) -> int:
        return int(self._visit_counts.get((src_id, dst_id, rel_type), 0))

    def exploration_score(
        self,
        weight: float,
        visit_count: int,
        total_visits: int | None = None,
        c: float | None = None,
    ) -> float:
        """UCB1-flavoured score: weight + c * sqrt(ln(N + 1) / (n + 1))."""
        n_total = total_visits if total_visits is not None else self.total_visits()
        coef = self.config.ucb_c if c is None else float(c)
        return float(weight) + coef * math.sqrt(math.log(n_total + 1) / (int(visit_count) + 1))

    def rank_neighbors(
        self,
        edges: Iterable[tuple[str, str, str, float]],
        c: float | None = None,
    ) -> list[tuple[str, float]]:
        """Given (src, dst, rel_type, weight) tuples, return [(dst, score), ...] sorted DESC."""
        n_total = self.total_visits()
        coef = self.config.ucb_c if c is None else float(c)
        ranked: list[tuple[str, float]] = []
        for src, dst, rel_type, weight in edges:
            visits = self._visit_counts.get((src, dst, rel_type), 0)
            score = self.exploration_score(weight, visits, total_visits=n_total, c=coef)
            ranked.append((dst, score))
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

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
        # LLW-AC-11: only physically delete when below the absolute floor.
        # Edges between floor_weight and min_weight_keep are kept as dormant so
        # random_boost can resurrect them.
        if new_weight < self.config.floor_weight:
            self._delete_edge(row.src_id, row.dst_id, row.rel_type)
            self._log({
                "op": "delete_below_floor",
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
        dormant = new_weight < self.config.min_weight_keep
        self._log({
            "op": "adjust",
            "src": row.src_id,
            "dst": row.dst_id,
            "rel_type": row.rel_type,
            "old_weight": old_weight,
            "new_weight": new_weight,
            "dormant": dormant,
            "reason": reason,
        })
        return True

    def _log(self, payload: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"timestamp": _utcnow().isoformat(), **payload}
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
