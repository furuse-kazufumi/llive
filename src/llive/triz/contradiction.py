# SPDX-License-Identifier: Apache-2.0
"""Contradiction Detector (TRIZ-02 / FR-23).

Identifies improvement-vs-degradation pairs in a stream of metric snapshots
and emits :class:`Contradiction` records suitable for the TRIZ Principle
Mapper (TRIZ-03).

Detection heuristic (Phase 3 MVR):
  1. Track every numeric metric in a rolling window (default 100 samples).
  2. Compute mean of the first / second half of the window per metric.
  3. A pair `(M_i, M_j)` is a candidate contradiction iff
     ``direction(M_i) == "up_is_good"`` improved (mean rose) **and**
     ``direction(M_j) == "up_is_good"`` worsened (mean fell), or any
     symmetric flip according to each metric's declared direction.
  4. Severity := |relative_delta_improve| + |relative_delta_degrade|, clipped to [0, 1].

A metric registry maps llive-specific metric names to TRIZ 39 attribute ids
so the mapper can hit the contradiction matrix. The default registry is
small and editable.
"""

from __future__ import annotations

import math
import uuid
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Direction = Literal["up_is_good", "down_is_good"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class MetricSpec:
    """Mapping from a llive metric name to a TRIZ attribute."""

    name: str
    triz_feature_id: int
    direction: Direction
    description: str = ""


# Default mapping per requirements_v0.3 § 2 FR-24
DEFAULT_REGISTRY: dict[str, MetricSpec] = {
    "pipeline.latency_ms": MetricSpec("pipeline.latency_ms", 9, "down_is_good", "speed"),
    "evolution.forgetting": MetricSpec(
        "evolution.forgetting", 13, "down_is_good", "stability"
    ),
    "candidate.acceptance_rate": MetricSpec(
        "candidate.acceptance_rate", 35, "up_is_good", "adaptability"
    ),
    "candidate.rollback_rate": MetricSpec(
        "candidate.rollback_rate", 27, "down_is_good", "reliability"
    ),
    "router.entropy": MetricSpec("router.entropy", 37, "down_is_good", "controllability"),
    "memory.pollution_ratio": MetricSpec(
        "memory.pollution_ratio", 31, "down_is_good", "harmful_side_effects"
    ),
    "pipeline.throughput": MetricSpec("pipeline.throughput", 39, "up_is_good", "productivity"),
    "container.subblock.count": MetricSpec(
        "container.subblock.count", 36, "down_is_good", "device_complexity"
    ),
    "evolution.eval.duration_s": MetricSpec(
        "evolution.eval.duration_s", 25, "down_is_good", "time_loss"
    ),
}


@dataclass
class Contradiction:
    contradiction_id: str
    improve_metric: str
    degrade_metric: str
    improve_feature_id: int
    degrade_feature_id: int
    severity: float
    evidence: dict[str, float]
    detected_at: datetime = field(default_factory=_utcnow)


@dataclass
class _Window:
    samples: deque[float]


class ContradictionDetector:
    """Sliding-window metric contradiction detector."""

    def __init__(
        self,
        registry: dict[str, MetricSpec] | None = None,
        *,
        window: int = 100,
        min_samples: int = 8,
        severity_floor: float = 0.05,
    ) -> None:
        self.registry = dict(registry) if registry is not None else dict(DEFAULT_REGISTRY)
        self.window_size = int(window)
        self.min_samples = int(min_samples)
        self.severity_floor = float(severity_floor)
        self._buffers: dict[str, _Window] = {}

    # -- ingestion ---------------------------------------------------------

    def register(self, spec: MetricSpec) -> None:
        self.registry[spec.name] = spec

    def observe(self, metric: str, value: float) -> None:
        if metric not in self.registry:
            return
        buf = self._buffers.setdefault(metric, _Window(samples=deque(maxlen=self.window_size)))
        buf.samples.append(float(value))

    def observe_many(self, sample: dict[str, float]) -> None:
        for k, v in sample.items():
            self.observe(k, v)

    # -- detection ---------------------------------------------------------

    def detect(self) -> list[Contradiction]:
        deltas: dict[str, float] = {}
        for name, win in self._buffers.items():
            if len(win.samples) < self.min_samples:
                continue
            half = len(win.samples) // 2
            first = list(win.samples)[:half]
            second = list(win.samples)[half:]
            mean_a = sum(first) / len(first)
            mean_b = sum(second) / len(second)
            base = (abs(mean_a) + abs(mean_b)) / 2 or 1.0
            rel = (mean_b - mean_a) / base
            deltas[name] = rel
        contradictions: list[Contradiction] = []
        items = sorted(deltas.items())  # determinism
        for i, (name_a, delta_a) in enumerate(items):
            spec_a = self.registry[name_a]
            improved_a = _is_improvement(spec_a.direction, delta_a)
            for name_b, delta_b in items[i + 1 :]:
                spec_b = self.registry[name_b]
                improved_b = _is_improvement(spec_b.direction, delta_b)
                if improved_a and not improved_b and abs(delta_b) >= self.severity_floor:
                    contradictions.append(
                        _make_contradiction(spec_a, spec_b, delta_a, delta_b)
                    )
                elif improved_b and not improved_a and abs(delta_a) >= self.severity_floor:
                    contradictions.append(
                        _make_contradiction(spec_b, spec_a, delta_b, delta_a)
                    )
        contradictions.sort(key=lambda c: -c.severity)
        return contradictions

    def reset(self) -> None:
        self._buffers.clear()


def _is_improvement(direction: Direction, relative_delta: float) -> bool:
    if direction == "up_is_good":
        return relative_delta > 0
    return relative_delta < 0


def _make_contradiction(
    improve: MetricSpec, degrade: MetricSpec, d_improve: float, d_degrade: float
) -> Contradiction:
    sev = min(1.0, abs(d_improve) + abs(d_degrade))
    return Contradiction(
        contradiction_id=f"contra_{uuid.uuid4().hex[:12]}",
        improve_metric=improve.name,
        degrade_metric=degrade.name,
        improve_feature_id=improve.triz_feature_id,
        degrade_feature_id=degrade.triz_feature_id,
        severity=float(sev) if not math.isnan(sev) else 0.0,
        evidence={
            "delta_improve_relative": float(d_improve),
            "delta_degrade_relative": float(d_degrade),
        },
    )


def detect_from_samples(
    samples: Iterable[dict[str, float]],
    registry: dict[str, MetricSpec] | None = None,
    *,
    window: int = 100,
    min_samples: int = 8,
) -> list[Contradiction]:
    """Convenience: feed a finite iterable of samples and return contradictions."""
    detector = ContradictionDetector(registry=registry, window=window, min_samples=min_samples)
    for s in samples:
        detector.observe_many(s)
    return detector.detect()


__all__ = [
    "DEFAULT_REGISTRY",
    "Contradiction",
    "ContradictionDetector",
    "MetricSpec",
    "detect_from_samples",
]
