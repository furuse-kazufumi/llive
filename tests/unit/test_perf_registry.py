# SPDX-License-Identifier: Apache-2.0
"""Tests for llive.perf.registry — APO applier reference (C-11)."""

from __future__ import annotations

import pytest

from llive.approval.bus import ApprovalBus
from llive.approval.policy import AllowList
from llive.perf import (
    Diagnostics,
    Optimizer,
    Profiler,
    Threshold,
    ThresholdRegistry,
    Verifier,
    apply_with_approval,
    default_invariants,
    raise_threshold_strategy,
)


def test_registry_canonical_target() -> None:
    assert (
        ThresholdRegistry.canonical_target("loop.tick.ms", "p95")
        == "profiler.threshold.loop.tick.ms.p95"
    )


def test_registry_register_and_get() -> None:
    t = Threshold("loop.tick.ms", "p95", max_value=200.0)
    reg = ThresholdRegistry([t])
    key = ThresholdRegistry.canonical_target("loop.tick.ms", "p95")
    assert reg.get(key) is t
    assert reg.snapshot() == {key: 200.0}


def test_registry_apply_mutates_max_value() -> None:
    t = Threshold("loop.tick.ms", "p95", max_value=200.0)
    reg = ThresholdRegistry([t])

    # Construct a Modification that targets the registered threshold.
    from llive.perf import Issue, Modification

    issue = Issue(
        metric="loop.tick.ms", stat="p95", observed=240.0, threshold=200.0,
        severity="warn", reason="x",
    )
    key = ThresholdRegistry.canonical_target("loop.tick.ms", "p95")
    mod = Modification(target=key, current=200.0, proposed=220.0, rationale=issue)

    reg.apply(mod)
    assert reg.snapshot()[key] == 220.0
    # live_thresholds reflects the new value
    updated = reg.live_thresholds[0]
    assert updated.max_value == 220.0
    # Other fields are preserved.
    assert updated.metric == "loop.tick.ms"
    assert updated.severity == "warn"


def test_registry_apply_rejects_unknown_target() -> None:
    reg = ThresholdRegistry()
    from llive.perf import Issue, Modification

    issue = Issue(
        metric="m", stat="p95", observed=1.0, threshold=1.0,
        severity="warn", reason="",
    )
    bogus = Modification(target="not.registered", current=1.0, proposed=2.0, rationale=issue)
    with pytest.raises(KeyError):
        reg.apply(bogus)


# ---------------------------------------------------------------------------
# End-to-end APO lane: Profiler → Diagnostics → Optimizer → Verifier →
# ApprovalBus → ThresholdRegistry.apply
# ---------------------------------------------------------------------------


def test_apo_end_to_end_relaxes_threshold_under_approval() -> None:
    # 1. Profiler with regressed latency.
    p = Profiler(window=100)
    for v in (210, 220, 230, 240, 250):
        p.record("loop.tick.ms", v)

    # 2. Registry seeds Diagnostics with the absolute threshold.
    initial = Threshold("loop.tick.ms", "p95", max_value=200.0)
    registry = ThresholdRegistry([initial])
    d = Diagnostics(p, thresholds=registry.live_thresholds)
    issues = d.check()
    assert len(issues) == 1  # threshold breached

    # 3. Optimizer proposes a small relaxation.
    opt = Optimizer(strategies=(raise_threshold_strategy(bump=1.10),))
    proposals = opt.propose(issues)
    assert len(proposals) == 1
    assert proposals[0].proposed == pytest.approx(220.0)

    # 4. Verifier vets the proposal under default invariants.
    v = Verifier(invariants=tuple(default_invariants()))
    accepted = v.verify(proposals).accepted
    assert len(accepted) == 1

    # 5. ApprovalBus auto-approves apo.modify; registry applies the change.
    bus = ApprovalBus(policy=AllowList({"apo.modify"}))
    result = apply_with_approval(bus, accepted, applier=registry.apply)
    assert len(result.applied) == 1

    # 6. Diagnostics with the new threshold no longer flags the same issue.
    d2 = Diagnostics(p, thresholds=registry.live_thresholds)
    assert d2.check() == []


def test_apo_end_to_end_blocks_unsafe_proposal() -> None:
    """A proposal that violates an invariant (e.g. > 50% step) is rejected
    before reaching the ApprovalBus, so the registry stays untouched."""
    p = Profiler(window=100)
    for v in (1000, 1100, 1200, 1300):  # huge p95
        p.record("loop.tick.ms", v)

    registry = ThresholdRegistry(
        [Threshold("loop.tick.ms", "p95", max_value=100.0)]
    )
    d = Diagnostics(p, thresholds=registry.live_thresholds)
    issues = d.check()
    # Strategy proposes a 12× relaxation (1200 / 100); bounded_step rejects it.
    opt = Optimizer(strategies=(raise_threshold_strategy(bump=12.0),))
    proposals = opt.propose(issues)
    v = Verifier(invariants=tuple(default_invariants()))
    result = v.verify(proposals)
    assert result.accepted == ()
    assert len(result.rejected) == 1
    # Registry unchanged.
    assert registry.snapshot()[
        ThresholdRegistry.canonical_target("loop.tick.ms", "p95")
    ] == 100.0
