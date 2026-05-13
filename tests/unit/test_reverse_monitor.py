"""EVO-07 Reverse-Evolution Monitor tests."""

from __future__ import annotations

import json

from llive.evolution.change_op import InsertSubblock, RemoveSubblock
from llive.evolution.reverse_monitor import (
    RegressionSignal,
    RegressionThresholds,
    ReverseEvolutionMonitor,
)
from llive.schema.models import ContainerSpec, SubBlockRef


def _container() -> ContainerSpec:
    return ContainerSpec(
        schema_version=1,
        container_id="t_v1",
        subblocks=[SubBlockRef(type="pre_norm"),
                   SubBlockRef(type="causal_attention"),
                   SubBlockRef(type="ffn_swiglu")],
    )


def test_no_regression_returns_no_triggers():
    m = ReverseEvolutionMonitor()
    sig = RegressionSignal(
        candidate_id="c1",
        baseline={"bwt": 0.5, "pollution": 0.1, "rollback_rate": 0.1, "latency_p99": 100.0},
        observed={"bwt": 0.51, "pollution": 0.1, "rollback_rate": 0.1, "latency_p99": 105.0},
    )
    assert m.evaluate(sig) == []


def test_bwt_drop_triggers():
    m = ReverseEvolutionMonitor(RegressionThresholds(bwt_drop=0.02))
    sig = RegressionSignal(
        candidate_id="c1",
        baseline={"bwt": 0.5},
        observed={"bwt": 0.46},
    )
    triggers = m.evaluate(sig)
    assert len(triggers) == 1
    assert "bwt dropped" in triggers[0]


def test_pollution_and_rollback_rise_combined():
    m = ReverseEvolutionMonitor(
        RegressionThresholds(bwt_drop=1.0, pollution_rise=0.1, rollback_rate_rise=0.1, latency_p99_factor=10.0)
    )
    sig = RegressionSignal(
        candidate_id="c1",
        baseline={"pollution": 0.1, "rollback_rate": 0.1},
        observed={"pollution": 0.25, "rollback_rate": 0.30},
    )
    triggers = m.evaluate(sig)
    assert any("pollution rose" in t for t in triggers)
    assert any("rollback rate rose" in t for t in triggers)


def test_latency_ratio_triggers():
    m = ReverseEvolutionMonitor(RegressionThresholds(latency_p99_factor=1.5))
    sig = RegressionSignal(
        candidate_id="c1",
        baseline={"latency_p99": 100.0},
        observed={"latency_p99": 200.0},
    )
    triggers = m.evaluate(sig)
    assert any("latency_p99 ratio" in t for t in triggers)


def test_missing_keys_no_crash():
    m = ReverseEvolutionMonitor()
    sig = RegressionSignal(candidate_id="c1", baseline={}, observed={})
    assert m.evaluate(sig) == []


def test_decide_builds_inverse_ops(tmp_path):
    log = tmp_path / "reverse.jsonl"
    m = ReverseEvolutionMonitor(RegressionThresholds(bwt_drop=0.02), log_path=log)
    sig = RegressionSignal(
        candidate_id="c1",
        baseline={"bwt": 0.5},
        observed={"bwt": 0.4},
    )
    before = _container()
    ops = [
        InsertSubblock(target_container="t_v1", after="head",
                       spec=SubBlockRef(type="memory_read", name="r1")),
    ]
    decision = m.decide(sig, before, ops)
    assert decision is not None
    assert len(decision.inverse_ops) == 1
    assert isinstance(decision.inverse_ops[0], RemoveSubblock)
    # log file should be created
    assert log.exists()
    payload = json.loads(log.read_text(encoding="utf-8").strip())
    assert payload["candidate_id"] == "c1"
    assert payload["n_inverse_ops"] == 1


def test_decide_returns_none_when_no_triggers():
    m = ReverseEvolutionMonitor()
    sig = RegressionSignal(candidate_id="c1", baseline={"bwt": 0.5}, observed={"bwt": 0.5})
    assert m.decide(sig, _container(), []) is None


def test_delta_helper():
    sig = RegressionSignal(candidate_id="c1", baseline={"x": 1.0}, observed={"x": 1.5})
    assert sig.delta("x") == 0.5
    assert sig.delta("nope") is None
