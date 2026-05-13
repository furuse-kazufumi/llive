"""Reverse-Evolution Monitor (EVO-07 / FR-22).

Watches BWT and other regression metrics after each candidate is promoted.
When a regression threshold is crossed, the monitor records a rollback
decision and emits the inverse :class:`ChangeOp` sequence so the caller can
revert the container to its pre-candidate state (Memento + Saga pattern).

The monitor is **deterministic and side-effect-free** outside its own log:
it does not mutate the structural memory directly; callers apply or skip
the suggested rollback.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llive.evolution.change_op import ChangeOp
from llive.schema.models import ContainerSpec


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _default_log_path() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "logs" / "reverse_evo.jsonl"


@dataclass
class RegressionThresholds:
    """How bad must things get before the monitor fires?

    All values are *absolute* (not relative).
    ``bwt_drop`` is interpreted as "BWT decreased by at least this much".
    """

    bwt_drop: float = 0.02  # 2 pp regression -> rollback
    pollution_rise: float = 0.10
    rollback_rate_rise: float = 0.20
    latency_p99_factor: float = 1.5  # P99 latency >= baseline * factor


@dataclass
class RegressionSignal:
    """Snapshot of metrics before and after candidate promotion."""

    candidate_id: str
    baseline: dict[str, float]
    observed: dict[str, float]
    detected_at: datetime = field(default_factory=_utcnow)

    def delta(self, key: str) -> float | None:
        if key not in self.baseline or key not in self.observed:
            return None
        return float(self.observed[key]) - float(self.baseline[key])


@dataclass
class RollbackDecision:
    decision_id: str
    candidate_id: str
    triggered_by: list[str]
    inverse_ops: list[ChangeOp]
    decided_at: datetime = field(default_factory=_utcnow)


class ReverseEvolutionMonitor:
    """Threshold-driven rollback recommender."""

    def __init__(
        self,
        thresholds: RegressionThresholds | None = None,
        log_path: Path | str | None = None,
    ) -> None:
        self.thresholds = thresholds or RegressionThresholds()
        self.log_path = Path(log_path) if log_path is not None else _default_log_path()
        self._lock = threading.Lock()

    # -- public API --------------------------------------------------------

    def evaluate(self, signal: RegressionSignal) -> list[str]:
        """Return list of triggered reasons. Empty list = no regression."""
        triggers: list[str] = []
        bwt_delta = signal.delta("bwt")
        if bwt_delta is not None and bwt_delta <= -self.thresholds.bwt_drop:
            triggers.append(f"bwt dropped by {-bwt_delta:.4f} (>= {self.thresholds.bwt_drop})")
        poll = signal.delta("pollution")
        if poll is not None and poll >= self.thresholds.pollution_rise:
            triggers.append(f"pollution rose by {poll:.4f} (>= {self.thresholds.pollution_rise})")
        rb = signal.delta("rollback_rate")
        if rb is not None and rb >= self.thresholds.rollback_rate_rise:
            triggers.append(
                f"rollback rate rose by {rb:.4f} (>= {self.thresholds.rollback_rate_rise})"
            )
        # latency: ratio
        baseline_p99 = signal.baseline.get("latency_p99")
        observed_p99 = signal.observed.get("latency_p99")
        if (
            baseline_p99 is not None
            and observed_p99 is not None
            and baseline_p99 > 0
            and observed_p99 / baseline_p99 >= self.thresholds.latency_p99_factor
        ):
            triggers.append(
                f"latency_p99 ratio {observed_p99 / baseline_p99:.2f}x "
                f">= {self.thresholds.latency_p99_factor}x"
            )
        return triggers

    def decide(
        self,
        signal: RegressionSignal,
        container_before: ContainerSpec,
        ops_applied: Sequence[ChangeOp],
    ) -> RollbackDecision | None:
        """Return a RollbackDecision (with inverse ops) if any threshold fires."""
        triggers = self.evaluate(signal)
        if not triggers:
            return None
        inverse_ops = _build_inverse(container_before, list(ops_applied))
        decision = RollbackDecision(
            decision_id=f"rollback_{uuid.uuid4().hex[:12]}",
            candidate_id=signal.candidate_id,
            triggered_by=triggers,
            inverse_ops=inverse_ops,
        )
        self._log(decision, signal)
        return decision

    # -- logging -----------------------------------------------------------

    def _log(self, decision: RollbackDecision, signal: RegressionSignal) -> None:
        payload: dict[str, Any] = {
            "timestamp": decision.decided_at.isoformat(),
            "decision_id": decision.decision_id,
            "candidate_id": decision.candidate_id,
            "triggered_by": decision.triggered_by,
            "n_inverse_ops": len(decision.inverse_ops),
            "baseline": signal.baseline,
            "observed": signal.observed,
        }
        with self._lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _build_inverse(before: ContainerSpec, ops: list[ChangeOp]) -> list[ChangeOp]:
    """Walk the diff forward, recording each op's inverse against the pre-state."""
    inverse: list[ChangeOp] = []
    current = before
    snapshots: list[ContainerSpec] = [current]
    for op in ops:
        current = op.apply(current)
        snapshots.append(current)
    for i in range(len(ops) - 1, -1, -1):
        inverse.append(ops[i].invert(snapshots[i]))
    return inverse


__all__ = [
    "RegressionSignal",
    "RegressionThresholds",
    "ReverseEvolutionMonitor",
    "RollbackDecision",
]
