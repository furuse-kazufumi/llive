"""SqliteLedger と ApprovalBus 永続化 (§AB1) の単体テスト."""

from __future__ import annotations

from pathlib import Path

from llive.approval import (
    AllowList,
    ApprovalBus,
    SqliteLedger,
    Verdict,
)
from llive.approval.ledger import SCHEMA_VERSION


def test_ledger_creates_schema(tmp_path: Path) -> None:
    db = tmp_path / "approval.db"
    with SqliteLedger(db) as ledger:
        assert ledger.schema_version() == SCHEMA_VERSION
    assert db.exists()


def test_ledger_persists_request_and_response(tmp_path: Path) -> None:
    db = tmp_path / "approval.db"
    with SqliteLedger(db) as ledger:
        bus = ApprovalBus(ledger=ledger)
        req = bus.request("shell:ls", {"args": ["ls", "-l"]})
        bus.approve(req.request_id, by="human:furuse", rationale="safe")
    # 別 instance で再 open → 永続化されているはず
    with SqliteLedger(db) as ledger:
        state = ledger.load()
        assert req.request_id in state.requests
        assert state.requests[req.request_id].action == "shell:ls"
        assert state.requests[req.request_id].payload == {"args": ["ls", "-l"]}
        assert len(state.responses) == 1
        assert state.responses[0].verdict is Verdict.APPROVED
        assert state.responses[0].by == "human:furuse"


def test_bus_restores_pending_across_restart(tmp_path: Path) -> None:
    db = tmp_path / "approval.db"
    # round 1: 1 件 request だけ作って response はしない (pending)
    with SqliteLedger(db) as ledger:
        bus1 = ApprovalBus(ledger=ledger)
        req = bus1.request("mouse:click", {"x": 5, "y": 7})
        assert len(bus1.pending()) == 1
    # round 2: 別 bus で再構築 → pending が復元
    with SqliteLedger(db) as ledger:
        bus2 = ApprovalBus(ledger=ledger)
        pending = bus2.pending()
        assert len(pending) == 1
        assert pending[0].request_id == req.request_id
        assert pending[0].action == "mouse:click"
        # 復元後に approve できる
        bus2.approve(req.request_id, by="human")
        assert bus2.current_verdict(req.request_id) is Verdict.APPROVED


def test_bus_replay_consistent_across_restart(tmp_path: Path) -> None:
    db = tmp_path / "approval.db"
    request_ids: list[str] = []
    with SqliteLedger(db) as ledger:
        bus1 = ApprovalBus(ledger=ledger)
        r1 = bus1.request("a", {})
        r2 = bus1.request("b", {})
        bus1.approve(r1.request_id, by="x")
        bus1.deny(r2.request_id, by="y")
        request_ids = [r1.request_id, r2.request_id]
        seq1 = bus1.replay()
    with SqliteLedger(db) as ledger:
        bus2 = ApprovalBus(ledger=ledger)
        seq2 = bus2.replay()
    assert seq1 == seq2
    assert seq2 == [
        (request_ids[0], Verdict.APPROVED),
        (request_ids[1], Verdict.DENIED),
    ]


def test_revoke_persists_and_restores(tmp_path: Path) -> None:
    db = tmp_path / "approval.db"
    with SqliteLedger(db) as ledger:
        bus = ApprovalBus(ledger=ledger)
        req = bus.request("net:fetch", {})
        bus.approve(req.request_id, by="human")
        bus.revoke(req.request_id, by="human", rationale="changed mind")
    with SqliteLedger(db) as ledger:
        bus = ApprovalBus(ledger=ledger)
        assert bus.current_verdict(req.request_id) is Verdict.REVOKED


def test_policy_auto_approval_persists(tmp_path: Path) -> None:
    db = tmp_path / "approval.db"
    policy = AllowList.of({"shell:ls"})
    with SqliteLedger(db) as ledger:
        bus = ApprovalBus(ledger=ledger, policy=policy)
        req = bus.request("shell:ls", {})
        # policy が即承認 → pending には残らない
        assert bus.current_verdict(req.request_id) is Verdict.APPROVED
        assert bus.pending() == []
    with SqliteLedger(db) as ledger:
        bus = ApprovalBus(ledger=ledger)
        # 再起動後も APPROVED が保たれる
        assert bus.current_verdict(req.request_id) is Verdict.APPROVED
        # response に policy:auto が記録されている
        led = bus.ledger()
        assert led[0].by == "policy:auto"
