# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-08 完成配線テスト — BriefDeque ↔ BriefRunner bridge."""

from __future__ import annotations

from dataclasses import dataclass

from llive.brief.types import Brief, BriefResult, BriefStatus
from llive.cognitive_mesh.brief_runner_bridge import BriefDequeRunnerBridge


@dataclass
class _FakeRunner:
    """submit() を観測する fake."""

    called_with: list[Brief]

    def submit(self, brief: Brief) -> BriefResult:
        self.called_with.append(brief)
        return BriefResult(brief_id=brief.brief_id, status=BriefStatus.COMPLETED)


def _make_brief(brief_id: str = "b-001", goal: str = "test goal") -> Brief:
    return Brief(brief_id=brief_id, goal=goal)


def test_enqueue_and_submit_next() -> None:
    runner = _FakeRunner(called_with=[])
    bridge = BriefDequeRunnerBridge(runner=runner)
    brief = _make_brief()
    ref = bridge.enqueue(brief)

    assert bridge.pending_count() == 1
    assert ref.id == "b-001"
    assert ref.topic == "test goal"
    assert ref.payload is brief

    result = bridge.submit_next()
    assert result is not None
    assert result.brief_id == "b-001"
    assert result.status == BriefStatus.COMPLETED
    assert runner.called_with == [brief]
    assert bridge.pending_count() == 0


def test_submit_next_returns_none_on_empty() -> None:
    runner = _FakeRunner(called_with=[])
    bridge = BriefDequeRunnerBridge(runner=runner)
    assert bridge.submit_next() is None
    assert runner.called_with == []


def test_submit_all_processes_in_fifo_order() -> None:
    runner = _FakeRunner(called_with=[])
    bridge = BriefDequeRunnerBridge(runner=runner)
    b1 = _make_brief("b-001")
    b2 = _make_brief("b-002")
    b3 = _make_brief("b-003")
    bridge.enqueue(b1)
    bridge.enqueue(b2)
    bridge.enqueue(b3)
    results = bridge.submit_all()
    assert [r.brief_id for r in results] == ["b-001", "b-002", "b-003"]
    assert runner.called_with == [b1, b2, b3]
    assert bridge.pending_count() == 0


def test_enqueue_front_overtakes() -> None:
    runner = _FakeRunner(called_with=[])
    bridge = BriefDequeRunnerBridge(runner=runner)
    b1 = _make_brief("b-001")
    b_urgent = _make_brief("b-urgent")
    bridge.enqueue(b1)
    bridge.enqueue_front(b_urgent)  # 緊急介入
    results = bridge.submit_all()
    assert [r.brief_id for r in results] == ["b-urgent", "b-001"]


def test_peek_next_does_not_pop() -> None:
    runner = _FakeRunner(called_with=[])
    bridge = BriefDequeRunnerBridge(runner=runner)
    b1 = _make_brief("b-001")
    bridge.enqueue(b1)
    ref = bridge.peek_next()
    assert ref is not None
    assert ref.id == "b-001"
    assert bridge.pending_count() == 1  # 未 pop


def test_submit_all_propagates_runner_exception() -> None:
    """fail-fast: runner が例外を投げたら残り未処理で停止."""

    class BadRunner:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def submit(self, brief: Brief) -> BriefResult:
            self.calls.append(brief.brief_id)
            if brief.brief_id == "b-002":
                raise RuntimeError("backend down")
            return BriefResult(brief_id=brief.brief_id, status=BriefStatus.COMPLETED)

    runner = BadRunner()
    bridge = BriefDequeRunnerBridge(runner=runner)
    bridge.enqueue(_make_brief("b-001"))
    bridge.enqueue(_make_brief("b-002"))
    bridge.enqueue(_make_brief("b-003"))
    import pytest

    with pytest.raises(RuntimeError, match="backend down"):
        bridge.submit_all()
    # b-001 は完了、b-002 で停止、b-003 は未処理で deque に残る
    assert runner.calls == ["b-001", "b-002"]
    assert bridge.pending_count() == 1  # b-003 残
    peek = bridge.peek_next()
    assert peek is not None
    assert peek.id == "b-003"
