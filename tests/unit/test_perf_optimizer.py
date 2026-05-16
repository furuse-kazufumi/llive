# SPDX-License-Identifier: Apache-2.0
"""Tests for llive.perf.optimizer (C-8 APO Optimizer / §E2)."""

from __future__ import annotations

import pytest

from llive.perf import (
    Issue,
    Modification,
    ModificationBound,
    Optimizer,
    raise_threshold_strategy,
    reduce_load_strategy,
)


def _issue(
    metric: str = "loop.tick.ms",
    stat: str = "p95",
    observed: float = 240.0,
    threshold: float = 200.0,
    severity: str = "warn",
) -> Issue:
    return Issue(
        metric=metric,
        stat=stat,
        observed=observed,
        threshold=threshold,
        severity=severity,  # type: ignore[arg-type]
        reason="test",
    )


# ---------------------------------------------------------------------------
# raise_threshold_strategy
# ---------------------------------------------------------------------------


def test_raise_threshold_proposes_relaxation() -> None:
    opt = Optimizer(strategies=(raise_threshold_strategy(bump=1.1),))
    mods = opt.propose([_issue(threshold=200.0)])
    assert len(mods) == 1
    m = mods[0]
    assert m.current == 200.0
    assert m.proposed == pytest.approx(220.0)
    assert m.target == "profiler.threshold.loop.tick.ms.p95"
    assert m.delta == pytest.approx(20.0)


def test_raise_threshold_skips_zero_threshold() -> None:
    opt = Optimizer(strategies=(raise_threshold_strategy(),))
    assert opt.propose([_issue(threshold=0.0)]) == []


# ---------------------------------------------------------------------------
# reduce_load_strategy
# ---------------------------------------------------------------------------


def test_reduce_load_proposes_lower_concurrency() -> None:
    opt = Optimizer(
        strategies=(reduce_load_strategy(current_concurrency=4, floor=1),)
    )
    mods = opt.propose([_issue()])
    assert len(mods) == 1
    assert mods[0].target == "scheduler.concurrency"
    assert mods[0].current == 4.0
    assert mods[0].proposed == 3.0


def test_reduce_load_skips_unrelated_metric() -> None:
    opt = Optimizer(strategies=(reduce_load_strategy(current_concurrency=4),))
    assert opt.propose([_issue(metric="triz.hits", stat="count")]) == []


def test_reduce_load_skips_when_at_floor() -> None:
    opt = Optimizer(
        strategies=(reduce_load_strategy(current_concurrency=1, floor=1),)
    )
    assert opt.propose([_issue()]) == []


# ---------------------------------------------------------------------------
# Strategy chaining + bounds + cap
# ---------------------------------------------------------------------------


def test_first_non_none_strategy_wins() -> None:
    def always_none(_: Issue) -> Modification | None:
        return None

    opt = Optimizer(
        strategies=(always_none, raise_threshold_strategy()),
    )
    mods = opt.propose([_issue()])
    assert len(mods) == 1


def test_bound_rejects_out_of_envelope_proposal() -> None:
    opt = Optimizer(
        strategies=(raise_threshold_strategy(bump=10.0),),  # 200 → 2000
        bounds=(
            ModificationBound(
                target="profiler.threshold.loop.tick.ms.p95",
                min_value=0.0,
                max_value=500.0,
            ),
        ),
    )
    assert opt.propose([_issue()]) == []


def test_bound_accepts_in_envelope_proposal() -> None:
    opt = Optimizer(
        strategies=(raise_threshold_strategy(bump=1.5),),  # 200 → 300
        bounds=(
            ModificationBound(
                target="profiler.threshold.loop.tick.ms.p95",
                min_value=0.0,
                max_value=500.0,
            ),
        ),
    )
    assert len(opt.propose([_issue()])) == 1


def test_unbounded_targets_pass_through_by_default() -> None:
    opt = Optimizer(strategies=(raise_threshold_strategy(),))
    # no bounds configured ⇒ proposal still emitted
    assert len(opt.propose([_issue()])) == 1


def test_max_modifications_caps_output_with_severity_first() -> None:
    opt = Optimizer(
        strategies=(raise_threshold_strategy(),),
        max_modifications=2,
    )
    issues = [
        _issue(metric=f"m{i}", severity=("error" if i == 4 else "info"), threshold=100.0)
        for i in range(5)
    ]
    mods = opt.propose(issues)
    assert len(mods) == 2
    # The error-severity one ranked first must appear.
    assert any(m.rationale.metric == "m4" for m in mods)


def test_zero_max_modifications_is_legal_and_returns_nothing() -> None:
    opt = Optimizer(strategies=(raise_threshold_strategy(),), max_modifications=0)
    assert opt.propose([_issue()]) == []


def test_negative_max_modifications_rejected() -> None:
    with pytest.raises(ValueError):
        Optimizer(max_modifications=-1)


def test_no_strategy_means_no_proposal() -> None:
    opt = Optimizer()
    assert opt.propose([_issue()]) == []


def test_modification_delta() -> None:
    issue = _issue(threshold=100.0)
    mod = Modification(target="x", current=100.0, proposed=130.0, rationale=issue)
    assert mod.delta == 30.0
