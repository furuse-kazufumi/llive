# SPDX-License-Identifier: Apache-2.0
"""Tests for llive.perf.verifier (C-9 APO Verifier / §E3)."""

from __future__ import annotations

from llive.perf import (
    Issue,
    Modification,
    VerificationResult,
    Verifier,
    bounded_step,
    default_invariants,
    load_reduction_only,
    non_negative,
    relaxation_only,
)


def _issue(metric: str = "loop.tick.ms") -> Issue:
    return Issue(
        metric=metric, stat="p95", observed=240.0, threshold=200.0,
        severity="warn", reason="test",
    )


def _mod(target: str, current: float, proposed: float) -> Modification:
    return Modification(
        target=target, current=current, proposed=proposed, rationale=_issue(),
    )


# ---------------------------------------------------------------------------
# Built-in invariants
# ---------------------------------------------------------------------------


def test_non_negative_accepts_positive() -> None:
    ok, _ = non_negative(_mod("x", 100.0, 50.0))  # type: ignore[misc]
    assert ok


def test_non_negative_rejects_negative() -> None:
    ok, reason = non_negative(_mod("x", 100.0, -5.0))  # type: ignore[misc]
    assert not ok
    assert "< 0" in reason


def test_relaxation_only_accepts_increase() -> None:
    check = relaxation_only()
    ok, _ = check(_mod("profiler.threshold.x.p95", 100.0, 110.0))  # type: ignore[misc]
    assert ok


def test_relaxation_only_rejects_tightening() -> None:
    check = relaxation_only()
    ok, reason = check(_mod("profiler.threshold.x.p95", 100.0, 80.0))  # type: ignore[misc]
    assert not ok
    assert "relaxation_only" in reason


def test_relaxation_only_ignores_non_matching_targets() -> None:
    check = relaxation_only()
    ok, _ = check(_mod("scheduler.concurrency", 4, 2))  # type: ignore[misc]
    assert ok  # not under the relaxation prefix


def test_load_reduction_only_accepts_decrease() -> None:
    check = load_reduction_only()
    ok, _ = check(_mod("scheduler.concurrency", 4, 2))  # type: ignore[misc]
    assert ok


def test_load_reduction_only_rejects_increase() -> None:
    check = load_reduction_only()
    ok, reason = check(_mod("scheduler.concurrency", 4, 6))  # type: ignore[misc]
    assert not ok
    assert "load_reduction_only" in reason


def test_bounded_step_accepts_small_change() -> None:
    check = bounded_step(0.5)
    ok, _ = check(_mod("x", 100.0, 130.0))  # 30 % step  # type: ignore[misc]
    assert ok


def test_bounded_step_rejects_large_change() -> None:
    check = bounded_step(0.5)
    ok, reason = check(_mod("x", 100.0, 200.0))  # type: ignore[misc]
    assert not ok
    assert "bounded_step" in reason or "max_step_ratio" in reason


def test_bounded_step_skips_zero_current() -> None:
    check = bounded_step(0.5)
    ok, _ = check(_mod("x", 0.0, 100.0))  # type: ignore[misc]
    assert ok  # cannot ratio against zero


# ---------------------------------------------------------------------------
# Verifier orchestration
# ---------------------------------------------------------------------------


def test_verifier_accepts_clean_modification() -> None:
    v = Verifier(invariants=tuple(default_invariants()))
    mod = _mod("profiler.threshold.loop.tick.ms.p95", 200.0, 220.0)
    result = v.verify([mod])
    assert isinstance(result, VerificationResult)
    assert result.accepted == (mod,)
    assert result.rejected == ()
    assert result.all_accepted


def test_verifier_rejects_tightening_threshold() -> None:
    v = Verifier(invariants=tuple(default_invariants()))
    bad = _mod("profiler.threshold.loop.tick.ms.p95", 200.0, 100.0)
    result = v.verify([bad])
    assert result.accepted == ()
    assert len(result.rejected) == 1
    assert result.rejected[0].invariant == "relaxation_only"
    assert not result.all_accepted


def test_verifier_rejects_excessive_step() -> None:
    v = Verifier(invariants=tuple(default_invariants()))
    too_big = _mod("profiler.threshold.x.p95", 100.0, 500.0)
    result = v.verify([too_big])
    assert len(result.rejected) == 1
    # bounded_step runs after relaxation_only; both could fire, but our
    # implementation short-circuits on the first failing check.
    assert result.rejected[0].invariant in {"bounded_step", "relaxation_only"}


def test_verifier_separates_accepted_and_rejected() -> None:
    v = Verifier(invariants=tuple(default_invariants()))
    good = _mod("profiler.threshold.x.p95", 100.0, 110.0)
    bad = _mod("scheduler.concurrency", 2, 4)  # load_reduction_only fail
    result = v.verify([good, bad])
    assert good in result.accepted
    assert bad in (rm.modification for rm in result.rejected)


def test_verifier_invariant_exception_is_recorded() -> None:
    def boom(_: Modification) -> bool:
        raise RuntimeError("backend down")

    v = Verifier(invariants=(boom,))
    result = v.verify([_mod("x", 1.0, 2.0)])
    assert len(result.rejected) == 1
    assert "backend down" in result.rejected[0].reason


def test_verifier_no_invariants_means_pass_through() -> None:
    v = Verifier()
    mod = _mod("anything", -5.0, 999.0)
    result = v.verify([mod])
    assert result.accepted == (mod,)


def test_add_invariant_dynamically() -> None:
    v = Verifier()
    v.add(non_negative)
    bad = _mod("x", 100.0, -1.0)
    assert v.verify([bad]).rejected[0].invariant == "non_negative"


def test_verifier_with_plain_bool_invariant() -> None:
    def positive_only(mod: Modification) -> bool:
        return mod.proposed > 0

    v = Verifier(invariants=(positive_only,))
    result = v.verify([_mod("x", 1.0, -1.0)])
    assert len(result.rejected) == 1
    # The bool->reason fallback yields a generic message.
    assert "False" in result.rejected[0].reason


def test_empty_modifications_is_legal() -> None:
    v = Verifier(invariants=tuple(default_invariants()))
    result = v.verify([])
    assert result.accepted == ()
    assert result.rejected == ()
    assert result.all_accepted
