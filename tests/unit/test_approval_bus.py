"""ApprovalBus (§AB) の単体テスト."""

from __future__ import annotations

import pytest

from llive.approval.bus import ApprovalBus, Verdict


def test_silence_equals_denial() -> None:
    """§AB4: 沈黙は不承認."""
    bus = ApprovalBus()
    req = bus.request("shell:ls", {"args": ["ls"]})
    # 何も応答しない
    assert bus.current_verdict(req.request_id) is Verdict.DENIED


def test_approve_and_query() -> None:
    bus = ApprovalBus()
    req = bus.request("shell:ls", {})
    bus.approve(req.request_id, by="human:furuse", rationale="safe read-only")
    assert bus.current_verdict(req.request_id) is Verdict.APPROVED


def test_deny_and_query() -> None:
    bus = ApprovalBus()
    req = bus.request("shell:rm -rf", {})
    bus.deny(req.request_id, by="policy:forbidden", rationale="dangerous")
    assert bus.current_verdict(req.request_id) is Verdict.DENIED


def test_revoke_after_approve() -> None:
    bus = ApprovalBus()
    req = bus.request("mouse:click", {"x": 10, "y": 20})
    bus.approve(req.request_id, by="human")
    bus.revoke(req.request_id, by="human", rationale="changed mind")
    assert bus.current_verdict(req.request_id) is Verdict.REVOKED


def test_unknown_request_raises() -> None:
    bus = ApprovalBus()
    with pytest.raises(KeyError):
        bus.approve("nonexistent", by="x")


def test_pending_clears_after_approve() -> None:
    bus = ApprovalBus()
    req = bus.request("a", {})
    assert len(bus.pending()) == 1
    bus.approve(req.request_id, by="x")
    assert bus.pending() == []


def test_replay_reproduces_verdict_sequence() -> None:
    """§AB1 replayable."""
    bus = ApprovalBus()
    r1 = bus.request("a", {})
    r2 = bus.request("b", {})
    bus.approve(r1.request_id, by="x")
    bus.deny(r2.request_id, by="y")
    seq = bus.replay()
    assert seq == [(r1.request_id, Verdict.APPROVED), (r2.request_id, Verdict.DENIED)]


def test_ledger_records_principal() -> None:
    """§AB2 principal identification."""
    bus = ApprovalBus()
    req = bus.request("a", {})
    bus.approve(req.request_id, by="human:furuse")
    led = bus.ledger()
    assert len(led) == 1
    assert led[0].by == "human:furuse"
