# SPDX-License-Identifier: Apache-2.0
"""VRB-05 — Eval Spec Editor (Metrics Registry + Stop Conditions).

Brief は元々 ``success_criteria`` を持つが自由テキスト。VRB-05 はそこへ
測定可能な metric / 閾値 / 停止条件を **構造化** で追加できる軽量レイヤ。

設計:

* :class:`Metric` (frozen) — name / unit / threshold / direction (lower_is_better)
* :class:`StopCondition` (frozen) — condition_id / expression / scope
* :class:`MetricsRegistry` — 集合管理 + JSON I/O
* :class:`EvalSpec` — Brief 1 件分の eval contract
* :class:`EvalEvaluator` — 観測値 dict と EvalSpec を突合 → :class:`EvalReport`

Brief 本体を **frozen のまま破壊しない**ように、Spec は side-car として
扱う (Brief.brief_id をキーに紐付け)。これにより既存全 Brief 利用箇所が
無改修で動き続ける。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Mapping

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger


@dataclass(frozen=True)
class Metric:
    """1 つの測定可能 metric。"""

    name: str
    unit: str = ""
    threshold: float | None = None
    lower_is_better: bool = False
    description: str = ""

    def passes(self, value: float) -> bool:
        """``threshold`` 未設定なら常に True。direction を考慮。"""
        if self.threshold is None:
            return True
        if self.lower_is_better:
            return value <= self.threshold
        return value >= self.threshold

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "unit": self.unit,
            "threshold": self.threshold,
            "lower_is_better": self.lower_is_better,
            "description": self.description,
        }


@dataclass(frozen=True)
class StopCondition:
    """eval を停止すべき条件 — 観測値 dict に対する判定。

    deterministic な評価のため expression は限定的 (``name OP literal`` 形式のみ)。
    複雑な式は LLM-driven evaluator に置き換える前提。
    """

    condition_id: str
    metric_name: str
    operator: str   # "<" / "<=" / ">" / ">=" / "==" / "!="
    value: float
    scope: str = "global"

    _OPS = ("<", "<=", ">", ">=", "==", "!=")

    def __post_init__(self) -> None:
        if self.operator not in self._OPS:
            raise ValueError(f"operator must be one of {self._OPS}, got {self.operator!r}")

    def met_by(self, observations: Mapping[str, float]) -> bool:
        if self.metric_name not in observations:
            return False
        v = float(observations[self.metric_name])
        op = self.operator
        if op == "<":
            return v < self.value
        if op == "<=":
            return v <= self.value
        if op == ">":
            return v > self.value
        if op == ">=":
            return v >= self.value
        if op == "==":
            return v == self.value
        return v != self.value

    def to_payload(self) -> dict[str, object]:
        return {
            "condition_id": self.condition_id,
            "metric_name": self.metric_name,
            "operator": self.operator,
            "value": self.value,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class EvalSpec:
    """Brief 1 件分の eval contract — side-car (Brief を改変しない)。"""

    brief_id: str
    metrics: tuple[Metric, ...] = ()
    stop_conditions: tuple[StopCondition, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "brief_id": self.brief_id,
            "metrics": [m.to_payload() for m in self.metrics],
            "stop_conditions": [c.to_payload() for c in self.stop_conditions],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class MetricResult:
    metric_name: str
    observed: float
    threshold: float | None
    passed: bool


@dataclass(frozen=True)
class EvalReport:
    brief_id: str
    metric_results: tuple[MetricResult, ...] = ()
    triggered_stop_conditions: tuple[str, ...] = ()

    @property
    def all_passed(self) -> bool:
        return all(m.passed for m in self.metric_results)

    @property
    def should_stop(self) -> bool:
        return bool(self.triggered_stop_conditions)

    def to_payload(self) -> dict[str, object]:
        return {
            "brief_id": self.brief_id,
            "all_passed": self.all_passed,
            "should_stop": self.should_stop,
            "metric_results": [
                {
                    "metric_name": m.metric_name,
                    "observed": m.observed,
                    "threshold": m.threshold,
                    "passed": m.passed,
                }
                for m in self.metric_results
            ],
            "triggered_stop_conditions": list(self.triggered_stop_conditions),
        }


class MetricsRegistry:
    """Mutable registry of metric / stop_condition definitions per Brief.

    Persistence is opt-in via ``path=``. Mostly used as an in-memory
    builder, then frozen into an :class:`EvalSpec` per Brief.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._metrics: dict[str, Metric] = {}
        self._stops: dict[str, StopCondition] = {}

    def register_metric(self, metric: Metric) -> None:
        if metric.name in self._metrics:
            raise ValueError(f"duplicate metric name: {metric.name!r}")
        self._metrics[metric.name] = metric

    def register_stop(self, condition: StopCondition) -> None:
        if condition.condition_id in self._stops:
            raise ValueError(f"duplicate stop condition id: {condition.condition_id!r}")
        self._stops[condition.condition_id] = condition

    def metrics(self) -> tuple[Metric, ...]:
        return tuple(self._metrics.values())

    def stop_conditions(self) -> tuple[StopCondition, ...]:
        return tuple(self._stops.values())

    def freeze_for(self, brief_id: str) -> EvalSpec:
        return EvalSpec(
            brief_id=brief_id,
            metrics=self.metrics(),
            stop_conditions=self.stop_conditions(),
        )

    def save(self) -> None:
        if self.path is None:
            raise RuntimeError("MetricsRegistry has no path — nothing to save")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "metrics": [m.to_payload() for m in self.metrics()],
            "stop_conditions": [c.to_payload() for c in self.stop_conditions()],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class EvalEvaluator:
    """Apply an :class:`EvalSpec` to an observation dict → :class:`EvalReport`."""

    def __init__(self, *, ledger: "BriefLedger | None" = None) -> None:
        self._ledger = ledger

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        self._ledger = ledger

    def evaluate(self, spec: EvalSpec, observations: Mapping[str, float]) -> EvalReport:
        metric_results: list[MetricResult] = []
        for m in spec.metrics:
            if m.name not in observations:
                # Missing observation — counted as failed unless threshold is None
                metric_results.append(MetricResult(
                    metric_name=m.name,
                    observed=float("nan"),
                    threshold=m.threshold,
                    passed=m.threshold is None,
                ))
                continue
            v = float(observations[m.name])
            metric_results.append(MetricResult(
                metric_name=m.name,
                observed=v,
                threshold=m.threshold,
                passed=m.passes(v),
            ))
        triggered: list[str] = []
        for c in spec.stop_conditions:
            if c.met_by(observations):
                triggered.append(c.condition_id)
        report = EvalReport(
            brief_id=spec.brief_id,
            metric_results=tuple(metric_results),
            triggered_stop_conditions=tuple(triggered),
        )
        if self._ledger is not None:
            self._ledger.append("eval_spec_evaluated", report.to_payload())
        return report


__all__ = [
    "EvalEvaluator",
    "EvalReport",
    "EvalSpec",
    "Metric",
    "MetricResult",
    "MetricsRegistry",
    "StopCondition",
]
