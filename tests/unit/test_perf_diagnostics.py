# SPDX-License-Identifier: Apache-2.0
"""Tests for llive.perf.diagnostics (C-7 APO Diagnostics)."""

from __future__ import annotations

import pytest

from llive.perf import (
    Diagnostics,
    Issue,
    Profiler,
    RegressionRule,
    Threshold,
)


@pytest.fixture
def profiler() -> Profiler:
    return Profiler(window=100)


# ---------------------------------------------------------------------------
# Threshold rules
# ---------------------------------------------------------------------------


def test_clean_run_yields_no_issues(profiler: Profiler) -> None:
    for v in (10, 12, 11, 13):
        profiler.record("loop.tick.ms", v)
    d = Diagnostics(
        profiler,
        thresholds=(Threshold("loop.tick.ms", "p95", max_value=200.0),),
    )
    assert d.check() == []
    assert d.verdict() is None


def test_threshold_violation_produces_issue(profiler: Profiler) -> None:
    for v in (10, 200, 250, 220):
        profiler.record("loop.tick.ms", v)
    d = Diagnostics(profiler)
    d.add_threshold(Threshold("loop.tick.ms", "p95", max_value=200.0, severity="warn"))
    issues = d.check()
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, Issue)
    assert issue.metric == "loop.tick.ms"
    assert issue.stat == "p95"
    assert issue.observed > 200
    assert issue.threshold == 200.0
    assert issue.severity == "warn"


def test_missing_metric_silently_passes(profiler: Profiler) -> None:
    d = Diagnostics(
        profiler,
        thresholds=(Threshold("never.recorded", "p95", max_value=1.0),),
    )
    assert d.check() == []


def test_missing_stat_silently_passes(profiler: Profiler) -> None:
    profiler.incr("triz.hits")
    # Counter snapshot only carries "count", not "p95".
    d = Diagnostics(
        profiler,
        thresholds=(Threshold("triz.hits", "p95", max_value=1.0),),
    )
    assert d.check() == []


def test_multiple_thresholds_all_evaluated(profiler: Profiler) -> None:
    for v in (300, 400, 350):
        profiler.record("loop.tick.ms", v)
    profiler.set_gauge("phase", 99.0)
    d = Diagnostics(
        profiler,
        thresholds=(
            Threshold("loop.tick.ms", "p95", 200.0, severity="error"),
            Threshold("phase", "value", 10.0, severity="warn"),
        ),
    )
    issues = d.check()
    metrics = sorted(i.metric for i in issues)
    assert metrics == ["loop.tick.ms", "phase"]


# ---------------------------------------------------------------------------
# Regression rules
# ---------------------------------------------------------------------------


def test_set_baseline_freezes_current_snapshot(profiler: Profiler) -> None:
    for v in (10, 12, 14):
        profiler.record("loop.tick.ms", v)
    d = Diagnostics(profiler)
    d.set_baseline()
    assert "loop.tick.ms" in d.baseline


def test_regression_triggers_when_exceeding_tolerance(profiler: Profiler) -> None:
    for v in (10, 10, 10, 10):
        profiler.record("loop.tick.ms", v)
    d = Diagnostics(profiler)
    d.set_baseline()  # baseline ~10ms

    for v in (50, 60, 70):
        profiler.record("loop.tick.ms", v)
    d.add_regression(RegressionRule("loop.tick.ms", "p95", tolerance=0.2))

    issues = d.check()
    regression_issues = [i for i in issues if "regressed" in i.reason]
    assert len(regression_issues) == 1
    assert regression_issues[0].observed > regression_issues[0].threshold


def test_regression_no_trigger_within_tolerance(profiler: Profiler) -> None:
    for v in (10, 10, 10):
        profiler.record("loop.tick.ms", v)
    d = Diagnostics(profiler)
    d.set_baseline()
    for v in (11, 11, 11):  # +10% < 20% tolerance
        profiler.record("loop.tick.ms", v)
    d.add_regression(RegressionRule("loop.tick.ms", "p95", tolerance=0.2))
    assert d.check() == []


def test_regression_against_zero_baseline_is_skipped(profiler: Profiler) -> None:
    # Baseline is empty, current grows — regression cannot be computed.
    d = Diagnostics(profiler)
    d.set_baseline({"loop.tick.ms": {"p95": 0.0}})
    profiler.record("loop.tick.ms", 100)
    d.add_regression(RegressionRule("loop.tick.ms", "p95"))
    assert d.check() == []


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def test_verdict_picks_highest_severity(profiler: Profiler) -> None:
    for v in (300, 400, 350):
        profiler.record("loop.tick.ms", v)
    profiler.set_gauge("phase", 50.0)
    d = Diagnostics(
        profiler,
        thresholds=(
            Threshold("loop.tick.ms", "p95", 200.0, severity="warn"),
            Threshold("phase", "value", 10.0, severity="error"),
        ),
    )
    assert d.verdict() == "error"


def test_verdict_returns_none_when_clean(profiler: Profiler) -> None:
    d = Diagnostics(profiler)
    assert d.verdict() is None


def test_verdict_accepts_provided_issues(profiler: Profiler) -> None:
    issue = Issue(
        metric="x", stat="p95", observed=1.0, threshold=0.5,
        severity="error", reason="manual",
    )
    d = Diagnostics(profiler)
    assert d.verdict([issue]) == "error"
