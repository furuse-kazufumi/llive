"""Backward Transfer (BWT) meter (OBS-04).

Continual learning metric. For ``K`` tasks learned in sequence:

    a[k][k]   = accuracy on task k *immediately after* training on task k.
    a[k][K-1] = accuracy on task k *after* the entire sequence is done.

    BWT = mean( a[k][K-1] - a[k][k]  for k in 0..K-2 )

Positive BWT means later tasks helped earlier tasks (rare in practice).
Negative BWT means the model forgot earlier tasks (the common case).
The Phase 2 acceptance criterion is BWT >= -1%.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_log_path() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "logs" / "llove" / "bwt.jsonl"


@dataclass
class TaskScore:
    task_id: str
    accuracy: float
    measured_at: datetime = field(default_factory=_utcnow)


@dataclass
class BWTSummary:
    n_tasks: int
    bwt: float
    avg_accuracy: float
    per_task_drop: dict[str, float]
    diagonal: dict[str, float]
    final: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_tasks": self.n_tasks,
            "bwt": self.bwt,
            "avg_accuracy": self.avg_accuracy,
            "per_task_drop": self.per_task_drop,
            "diagonal": self.diagonal,
            "final": self.final,
        }


class BWTMeter:
    """Track per-task accuracy through a continual learning sequence."""

    def __init__(self) -> None:
        self.task_order: list[str] = []
        self.matrix: dict[tuple[str, int], TaskScore] = {}
        self._lock = threading.Lock()

    def begin_task(self, task_id: str) -> None:
        with self._lock:
            if task_id not in self.task_order:
                self.task_order.append(task_id)

    def record(self, task_id: str, after_task_index: int, accuracy: float) -> None:
        """Record accuracy on ``task_id`` measured after the ``after_task_index``-th task."""
        with self._lock:
            if not 0 <= after_task_index < max(1, len(self.task_order) + 1):
                pass
            self.matrix[(task_id, int(after_task_index))] = TaskScore(task_id=task_id, accuracy=float(accuracy))

    def diagonal_accuracy(self, task_id: str) -> float | None:
        idx = self._idx(task_id)
        if idx is None:
            return None
        score = self.matrix.get((task_id, idx))
        return score.accuracy if score else None

    def final_accuracy(self, task_id: str) -> float | None:
        if not self.task_order:
            return None
        last_idx = len(self.task_order) - 1
        score = self.matrix.get((task_id, last_idx))
        return score.accuracy if score else None

    def _idx(self, task_id: str) -> int | None:
        try:
            return self.task_order.index(task_id)
        except ValueError:
            return None

    def summarize(self) -> BWTSummary:
        """Compute BWT from recorded scores. Tasks without diagonal+final pairs are skipped."""
        diagonal: dict[str, float] = {}
        final: dict[str, float] = {}
        per_task_drop: dict[str, float] = {}
        if not self.task_order:
            return BWTSummary(n_tasks=0, bwt=0.0, avg_accuracy=0.0, per_task_drop={}, diagonal={}, final={})
        last_idx = len(self.task_order) - 1
        deltas: list[float] = []
        finals: list[float] = []
        for tid in self.task_order:
            d = self.diagonal_accuracy(tid)
            f = self.final_accuracy(tid)
            if d is not None:
                diagonal[tid] = d
            if f is not None:
                final[tid] = f
                finals.append(f)
            if d is not None and f is not None and self._idx(tid) != last_idx:
                deltas.append(f - d)
                per_task_drop[tid] = f - d
        bwt = sum(deltas) / len(deltas) if deltas else 0.0
        avg = sum(finals) / len(finals) if finals else 0.0
        return BWTSummary(
            n_tasks=len(self.task_order),
            bwt=float(bwt),
            avg_accuracy=float(avg),
            per_task_drop=per_task_drop,
            diagonal=diagonal,
            final=final,
        )

    def dump_jsonl(self, path: Path | str | None = None) -> Path:
        target = Path(path) if path is not None else _default_log_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        summary = self.summarize()
        with target.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "timestamp": _utcnow().isoformat(),
                        "task_order": list(self.task_order),
                        **summary.to_dict(),
                    }
                )
                + "\n"
            )
        return target
