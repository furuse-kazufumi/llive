# SPDX-License-Identifier: Apache-2.0
"""VRB-05 — EvalSpec / MetricsRegistry / StopCondition / EvalEvaluator tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llive.brief import (
    BriefLedger,
    EvalEvaluator,
    EvalReport,
    EvalSpec,
    Metric,
    MetricsRegistry,
    StopCondition,
)


def test_metric_passes_with_higher_is_better() -> None:
    m = Metric(name="accuracy", threshold=0.9)
    assert m.passes(0.95)
    assert not m.passes(0.8)


def test_metric_passes_with_lower_is_better() -> None:
    m = Metric(name="latency_ms", threshold=100.0, lower_is_better=True)
    assert m.passes(50.0)
    assert not m.passes(150.0)


def test_metric_no_threshold_always_passes() -> None:
    assert Metric(name="x").passes(123.0)


def test_stop_condition_rejects_bad_operator() -> None:
    with pytest.raises(ValueError):
        StopCondition(condition_id="s1", metric_name="m", operator="===", value=0.0)


def test_stop_condition_met_by_dispatch() -> None:
    c = StopCondition(condition_id="s1", metric_name="err_rate", operator=">=", value=0.5)
    assert c.met_by({"err_rate": 0.7})
    assert not c.met_by({"err_rate": 0.1})


def test_stop_condition_missing_metric_returns_false() -> None:
    c = StopCondition(condition_id="s1", metric_name="missing", operator=">", value=0.0)
    assert not c.met_by({"other": 1.0})


def test_registry_freeze_for_brief() -> None:
    reg = MetricsRegistry()
    reg.register_metric(Metric(name="acc", threshold=0.9))
    reg.register_stop(StopCondition(
        condition_id="cost_cap", metric_name="cost_usd", operator=">", value=10.0,
    ))
    spec = reg.freeze_for("brief-1")
    assert isinstance(spec, EvalSpec)
    assert spec.brief_id == "brief-1"
    assert spec.metrics[0].name == "acc"
    assert spec.stop_conditions[0].condition_id == "cost_cap"


def test_registry_rejects_duplicates() -> None:
    reg = MetricsRegistry()
    reg.register_metric(Metric(name="acc"))
    with pytest.raises(ValueError):
        reg.register_metric(Metric(name="acc"))
    reg.register_stop(StopCondition(condition_id="s1", metric_name="acc", operator=">", value=0))
    with pytest.raises(ValueError):
        reg.register_stop(StopCondition(condition_id="s1", metric_name="acc", operator=">", value=0))


def test_registry_save_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "reg.json"
    reg = MetricsRegistry(path=path)
    reg.register_metric(Metric(name="latency", unit="ms", threshold=100, lower_is_better=True))
    reg.save()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["metrics"][0]["unit"] == "ms"


def test_evaluator_pass_fail_per_metric() -> None:
    spec = EvalSpec(
        brief_id="x",
        metrics=(
            Metric(name="acc", threshold=0.9),
            Metric(name="latency", threshold=100, lower_is_better=True),
        ),
    )
    report = EvalEvaluator().evaluate(spec, {"acc": 0.95, "latency": 50})
    assert report.all_passed
    assert not report.should_stop


def test_evaluator_triggers_stop_condition() -> None:
    spec = EvalSpec(
        brief_id="x",
        metrics=(),
        stop_conditions=(
            StopCondition(condition_id="cost", metric_name="cost", operator=">", value=10.0),
        ),
    )
    report = EvalEvaluator().evaluate(spec, {"cost": 20.0})
    assert report.should_stop
    assert "cost" in report.triggered_stop_conditions


def test_evaluator_missing_observation_fails_metric() -> None:
    spec = EvalSpec(
        brief_id="x",
        metrics=(Metric(name="acc", threshold=0.9),),
    )
    report = EvalEvaluator().evaluate(spec, {"other": 1.0})
    assert not report.all_passed


def test_evaluator_ledger_event(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "ev.jsonl")
    spec = EvalSpec(brief_id="x", metrics=(Metric(name="acc", threshold=0.9),))
    EvalEvaluator(ledger=ledger).evaluate(spec, {"acc": 0.95})
    events = [r for r in ledger.read() if r.event == "eval_spec_evaluated"]
    assert events
    tg = ledger.trace_graph()
    assert any(d["event"] == "eval_spec_evaluated" for d in tg.decision_chain)
