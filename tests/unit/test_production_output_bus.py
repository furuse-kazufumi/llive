# SPDX-License-Identifier: Apache-2.0
"""ProductionOutputBus の単体テスト."""

from __future__ import annotations

from pathlib import Path

from llive.approval import AllowList, ApprovalBus, DenyList, Verdict
from llive.fullsense.sandbox import SandboxOutputBus
from llive.output import ProductionOutputBus


def test_emit_raw_approved_executes_side_effect() -> None:
    bus = ApprovalBus(policy=AllowList.of({"counter:inc"}))
    pbus = ProductionOutputBus(approval=bus)
    counter = [0]

    result = pbus.emit_raw(
        action="counter:inc",
        payload={"step": 1},
        on_approved=lambda: counter.__setitem__(0, counter[0] + 1),
    )
    assert result.approved
    assert counter == [1]
    assert result.record.verdict is Verdict.APPROVED
    assert result.record.side_effect_executed
    assert result.error is None


def test_emit_raw_denied_skips_side_effect() -> None:
    bus = ApprovalBus(policy=DenyList.of({"counter:inc"}))
    pbus = ProductionOutputBus(approval=bus)
    counter = [0]

    result = pbus.emit_raw(
        action="counter:inc",
        payload={},
        on_approved=lambda: counter.__setitem__(0, counter[0] + 1),
    )
    assert not result.approved
    assert counter == [0]  # 副作用なし
    assert result.record.verdict is Verdict.DENIED
    assert not result.record.side_effect_executed


def test_emit_raw_silence_treated_as_denial() -> None:
    bus = ApprovalBus()  # policy なし → silence
    pbus = ProductionOutputBus(approval=bus)
    counter = [0]

    result = pbus.emit_raw(
        action="x",
        payload={},
        on_approved=lambda: counter.__setitem__(0, 1),
    )
    assert not result.approved
    assert counter == [0]
    assert result.record.verdict is Verdict.DENIED


def test_emit_raw_side_effect_error_captured() -> None:
    bus = ApprovalBus(policy=AllowList.of({"boom"}))
    pbus = ProductionOutputBus(approval=bus)

    def fail() -> None:
        raise RuntimeError("transport failed")

    result = pbus.emit_raw(action="boom", payload={}, on_approved=fail)
    assert not result.approved
    assert result.error is not None
    assert isinstance(result.error, RuntimeError)
    assert "transport failed" in result.record.error_repr


def test_emit_file_writes(tmp_path: Path) -> None:
    bus = ApprovalBus(policy=AllowList.of({"file:write"}))
    pbus = ProductionOutputBus(approval=bus)
    target = tmp_path / "subdir" / "out.txt"

    result = pbus.emit_file(target, "hello\n")
    assert result.approved
    assert target.read_text(encoding="utf-8") == "hello\n"


def test_emit_file_denied_no_write(tmp_path: Path) -> None:
    bus = ApprovalBus(policy=DenyList.of({"file:write"}))
    pbus = ProductionOutputBus(approval=bus)
    target = tmp_path / "out.txt"

    result = pbus.emit_file(target, "should not appear")
    assert not result.approved
    assert not target.exists()


def test_emit_mcp_push_uses_injected_fn() -> None:
    bus = ApprovalBus(policy=AllowList.of({"mcp:push"}))
    seen: list[tuple[str, dict[str, object]]] = []
    pbus = ProductionOutputBus(
        approval=bus,
        mcp_push_fn=lambda target, message: seen.append((target, dict(message))),
    )

    result = pbus.emit_mcp_push("server-A", {"event": "hello", "n": 1})
    assert result.approved
    assert seen == [("server-A", {"event": "hello", "n": 1})]


def test_emit_mcp_push_without_fn_raises_captured() -> None:
    bus = ApprovalBus(policy=AllowList.of({"mcp:push"}))
    pbus = ProductionOutputBus(approval=bus)  # mcp_push_fn 未注入

    result = pbus.emit_mcp_push("x", {})
    assert not result.approved
    assert isinstance(result.error, RuntimeError)


def test_emit_llove_push_uses_injected_fn() -> None:
    bus = ApprovalBus(policy=AllowList.of({"llove:push"}))
    seen: list[tuple[str, dict[str, object]]] = []
    pbus = ProductionOutputBus(
        approval=bus,
        llove_push_fn=lambda vid, payload: seen.append((vid, dict(payload))),
    )

    result = pbus.emit_llove_push("audit-view", {"line": "ok"})
    assert result.approved
    assert seen == [("audit-view", {"line": "ok"})]


def test_sandbox_fallback_records_denied_emit() -> None:
    bus = ApprovalBus(policy=DenyList.of({"file:write"}))
    sandbox = SandboxOutputBus()
    pbus = ProductionOutputBus(approval=bus, sandbox=sandbox)

    pbus.emit_file("/tmp/should-not-write.txt", "x")
    pbus.emit_file("/tmp/also-no.txt", "y")

    denied = sandbox.denied_emits()
    assert len(denied) == 2
    assert all(e["action"] == "file:write" for e in denied)
    # sandbox.records() (FullSense 系) は副作用ゼロを保つため空のまま
    assert sandbox.records() == []


def test_records_query_partitions() -> None:
    bus = ApprovalBus(policy=AllowList.of({"ok"}))
    pbus = ProductionOutputBus(approval=bus)
    pbus.emit_raw(action="ok", payload={}, on_approved=lambda: None)
    pbus.emit_raw(action="bad", payload={}, on_approved=lambda: None)

    assert len(pbus.records()) == 2
    assert len(pbus.approved_records()) == 1
    assert len(pbus.denied_records()) == 1
    assert pbus.approved_records()[0].action == "ok"
    assert pbus.denied_records()[0].action == "bad"
