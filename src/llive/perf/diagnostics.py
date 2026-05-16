# SPDX-License-Identifier: Apache-2.0
"""APO Diagnostics — production self-correction layer on top of Profiler.

Spec §APO requires the loop to detect its own performance degradation
**before** invoking optimisation. The Profiler already collects metrics
without side effects; ``Diagnostics`` turns a snapshot into a list of
``Issue`` objects by checking each metric against:

* **Absolute thresholds** — declared ``Threshold`` objects (``p95_max``,
  ``mean_max``, etc.)
* **Regression vs. a baseline snapshot** — ratio thresholds against a
  previously-captured snapshot. Catches drift that absolute thresholds
  would miss.

The output (``list[Issue]``) is consumed by §E2 ``Optimizer`` (bounded
modification) and §E3 ``Verifier`` (formal pre-check). Those layers
remain skeleton-only for now; this module is the deterministic
input that lets them be designed against a stable contract.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from llive.perf.profiler import Profiler

Severity = Literal["info", "warn", "error"]
_SEVERITY_RANK: dict[Severity, int] = {"info": 0, "warn": 1, "error": 2}


@dataclass(frozen=True)
class Threshold:
    """Absolute upper bound for one numeric metric key.

    ``metric`` is the Profiler key (e.g. ``"loop.tick.ms"``).
    ``stat`` is the key inside the snapshot dict (e.g. ``"p95"``,
    ``"mean"``, ``"max"``, ``"value"``, ``"count"``).
    ``max_value`` is the inclusive upper bound. ``severity`` controls
    how the resulting ``Issue`` is classified.
    """

    metric: str
    stat: str
    max_value: float
    severity: Severity = "warn"


@dataclass(frozen=True)
class RegressionRule:
    """Relative bound vs. a baseline snapshot.

    Triggers when ``current[stat] > baseline[stat] * (1 + tolerance)``.
    Useful for catching "slowly creeping" degradation.
    """

    metric: str
    stat: str
    tolerance: float = 0.20  # 20 % regression allowed
    severity: Severity = "warn"


@dataclass(frozen=True)
class Issue:
    """One detected anomaly emitted by ``Diagnostics.check``."""

    metric: str
    stat: str
    observed: float
    threshold: float
    severity: Severity
    reason: str


@dataclass
class Diagnostics:
    """Apply thresholds and regression rules to a Profiler snapshot."""

    profiler: Profiler
    thresholds: tuple[Threshold, ...] = field(default_factory=tuple)
    regressions: tuple[RegressionRule, ...] = field(default_factory=tuple)
    baseline: dict[str, dict[str, float]] = field(default_factory=dict)

    def add_threshold(self, t: Threshold) -> None:
        self.thresholds = (*self.thresholds, t)

    def add_regression(self, r: RegressionRule) -> None:
        self.regressions = (*self.regressions, r)

    def set_baseline(self, snapshot: dict[str, dict[str, float]] | None = None) -> None:
        """Freeze a baseline snapshot. ``None`` ⇒ capture from the profiler now."""
        self.baseline = (
            {k: dict(v) for k, v in snapshot.items()}
            if snapshot is not None
            else {k: dict(v) for k, v in self.profiler.snapshot().items()}
        )

    def check(self) -> list[Issue]:
        """Run all configured rules against the profiler's current snapshot."""
        snap = self.profiler.snapshot()
        issues: list[Issue] = []

        for t in self.thresholds:
            metric_snap = snap.get(t.metric)
            if metric_snap is None or t.stat not in metric_snap:
                continue
            observed = float(metric_snap[t.stat])
            if observed > t.max_value:
                issues.append(
                    Issue(
                        metric=t.metric,
                        stat=t.stat,
                        observed=observed,
                        threshold=t.max_value,
                        severity=t.severity,
                        reason=(
                            f"{t.metric}.{t.stat}={observed:.4g} > "
                            f"absolute_max={t.max_value:.4g}"
                        ),
                    )
                )

        for r in self.regressions:
            base = self.baseline.get(r.metric)
            cur = snap.get(r.metric)
            if not base or not cur or r.stat not in base or r.stat not in cur:
                continue
            baseline_v = float(base[r.stat])
            if baseline_v <= 0:
                continue  # cannot compute relative regression vs zero/negative
            observed = float(cur[r.stat])
            limit = baseline_v * (1.0 + r.tolerance)
            if observed > limit:
                issues.append(
                    Issue(
                        metric=r.metric,
                        stat=r.stat,
                        observed=observed,
                        threshold=limit,
                        severity=r.severity,
                        reason=(
                            f"{r.metric}.{r.stat}={observed:.4g} regressed "
                            f">{int(r.tolerance * 100)}% vs baseline "
                            f"{baseline_v:.4g}"
                        ),
                    )
                )

        return issues

    def verdict(self, issues: Iterable[Issue] | None = None) -> Severity | None:
        """Highest severity among the supplied (or freshly checked) issues.

        ``None`` if the run is clean.
        """
        seq = list(issues) if issues is not None else self.check()
        if not seq:
            return None
        return max(seq, key=lambda i: _SEVERITY_RANK[i.severity]).severity


__all__ = [
    "Diagnostics",
    "Issue",
    "RegressionRule",
    "Severity",
    "Threshold",
]
