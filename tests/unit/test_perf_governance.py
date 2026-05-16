# SPDX-License-Identifier: Apache-2.0
"""Tests for llive.perf.governance (C-10 APO ApprovalBus glue)."""

from __future__ import annotations

from llive.approval.bus import ApprovalBus, Verdict
from llive.approval.policy import AllowList
from llive.perf import (
    ApplyResult,
    Issue,
    Modification,
    apply_with_approval,
)


def _issue() -> Issue:
    return Issue(
        metric="loop.tick.ms", stat="p95", observed=240.0, threshold=200.0,
        severity="warn", reason="test",
    )


def _mod(target: str = "profiler.threshold.x", proposed: float = 110.0) -> Modification:
    return Modification(
        target=target, current=100.0, proposed=proposed, rationale=_issue()
    )


# ---------------------------------------------------------------------------
# Policy auto-approves
# ---------------------------------------------------------------------------


def test_auto_approve_applies_each_modification() -> None:
    bus = ApprovalBus(policy=AllowList({"apo.modify"}))
    applied: list[Modification] = []
    mods = [_mod(), _mod(target="profiler.threshold.y")]

    result = apply_with_approval(bus, mods, applier=applied.append)

    assert isinstance(result, ApplyResult)
    assert len(result.applied) == 2
    assert applied == mods
    assert result.denied == ()
    assert result.errors == ()


def test_auto_deny_does_not_run_applier() -> None:
    class DenyEverything:
        def evaluate(self, _req: object) -> Verdict:
            return Verdict.DENIED

    bus = ApprovalBus(policy=DenyEverything())
    applied: list[Modification] = []
    result = apply_with_approval(bus, [_mod()], applier=applied.append)

    assert applied == []
    assert len(result.denied) == 1
    assert result.applied == ()


# ---------------------------------------------------------------------------
# Pending / silence
# ---------------------------------------------------------------------------


def test_pending_request_is_treated_as_denial_by_bus() -> None:
    # No policy → request stays pending. ``current_verdict`` returns
    # DENIED via §AB4 silence rule, so the applier must NOT run.
    bus = ApprovalBus()
    applied: list[Modification] = []
    result = apply_with_approval(bus, [_mod()], applier=applied.append)
    assert applied == []
    # Either denied or skipped_unknown depending on Verdict; both leave
    # the applier untouched.
    assert all(o.status != "applied" for o in result.outcomes)


# ---------------------------------------------------------------------------
# Applier failure capture
# ---------------------------------------------------------------------------


def test_applier_exception_is_captured_not_raised() -> None:
    bus = ApprovalBus(policy=AllowList({"apo.modify"}))

    def boom(_: Modification) -> None:
        raise RuntimeError("apply backend down")

    result = apply_with_approval(bus, [_mod()], applier=boom)
    assert len(result.errors) == 1
    assert "apply backend down" in result.errors[0].reason


# ---------------------------------------------------------------------------
# Payload shape
# ---------------------------------------------------------------------------


def test_request_payload_carries_change_context() -> None:
    bus = ApprovalBus(policy=AllowList({"apo.modify"}))
    seen_payloads: list[dict[str, object]] = []

    real_request = bus.request

    def capture(action, payload, *, principal="agent", timeout_s=5.0):
        seen_payloads.append(payload)
        return real_request(action, payload, principal=principal, timeout_s=timeout_s)

    bus.request = capture  # type: ignore[assignment]

    apply_with_approval(bus, [_mod()], applier=lambda _m: None)

    assert seen_payloads, "request was never called"
    payload = seen_payloads[0]
    assert payload["target"] == "profiler.threshold.x"
    assert payload["current"] == 100.0
    assert payload["proposed"] == 110.0
    assert payload["delta"] == 10.0
    rationale = payload["rationale"]
    assert isinstance(rationale, dict)
    assert rationale["metric"] == "loop.tick.ms"
    assert rationale["severity"] == "warn"


def test_principal_and_action_are_overridable() -> None:
    bus = ApprovalBus(policy=AllowList({"custom.action"}))
    applied: list[Modification] = []
    result = apply_with_approval(
        bus,
        [_mod()],
        applier=applied.append,
        principal="apo-experimental",
        action="custom.action",
    )
    assert len(result.applied) == 1


def test_empty_modifications_round_trips_to_empty_result() -> None:
    bus = ApprovalBus(policy=AllowList({"apo.modify"}))
    result = apply_with_approval(bus, [], applier=lambda _m: None)
    assert result.outcomes == ()
    assert result.applied == ()
    assert result.denied == ()
