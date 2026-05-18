# SPDX-License-Identifier: Apache-2.0
"""Tests for ProactiveLoop skeleton (COG-MESH-06).

Phase 5 で full 実装する予定だが、現時点で凍結する API 契約:

1. QuietHoursGuard 必須依存 (None だと TypeError)
2. can_speak_now() は QuietHoursGuard.allow('proactive') の薄ラッパ
3. tick() は Quiet Hours 中なら None を返す (即時抑止)
4. tick() は Active 中なら NotImplementedError を投げる (Phase 5 まで)
5. latest_utterances(n) は空 list を返す (skeleton 状態)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from llive.cognitive_mesh.proactive import ProactiveLoop
from llive.cognitive_mesh.quiet_hours import QuietHoursGuard

JST = timezone(timedelta(hours=9))


def _at(hour: int) -> datetime:
    return datetime(2026, 5, 18, hour, 0, tzinfo=JST)


def _make_guard(monkeypatch: pytest.MonkeyPatch) -> QuietHoursGuard:
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    return QuietHoursGuard()


def test_proactive_loop_requires_quiet_hours_guard() -> None:
    """quiet_hours=None で構築すると TypeError (倫理は architecture の一部)."""
    with pytest.raises(TypeError, match="QuietHoursGuard"):
        ProactiveLoop(quiet_hours=None)  # type: ignore[arg-type]


def test_can_speak_now_during_quiet_hours_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(quiet_hours=guard)
    assert loop.can_speak_now(now=_at(2)) is False


def test_can_speak_now_during_active_returns_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(quiet_hours=guard)
    assert loop.can_speak_now(now=_at(10)) is True


def test_tick_during_quiet_hours_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(quiet_hours=guard)
    # Quiet Hours 中は即時 None で抑止 (NotImplementedError 出ない)
    assert loop.tick(now=_at(2)) is None


def test_tick_without_stimulus_source_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stimulus_source 未設定なら tick は NotImplementedError."""
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(quiet_hours=guard)
    with pytest.raises(NotImplementedError, match="stimulus_source"):
        loop.tick(now=_at(10))


def test_tick_with_high_gift_value_returns_utterance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GiftValue が閾値を超えれば ProactiveUtterance を返し履歴に記録."""
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(
        quiet_hours=guard,
        stimulus_source=lambda: "重要な進捗報告: build が完了しました",
    )
    listener = {
        "current_topic": "build",
        "risk_score": 0.8,
        "focus_level": 0.3,
        "in_quiet_hours": False,
    }
    utterance = loop.tick(now=_at(10), listener_state=listener)
    assert utterance is not None
    assert utterance.content.startswith("重要な")
    assert utterance.mode == "timer"
    assert utterance.gift_value >= 0.6
    assert loop.latest_utterances(n=5)[-1] is utterance
    assert loop.latest_suppressed(n=5) == []


def test_tick_with_low_gift_value_returns_none_and_records_suppression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GiftValue が閾値未満なら抑制履歴に記録、tick は None を返す."""
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(
        quiet_hours=guard,
        stimulus_source=lambda: "雑談 (関連無し)",
    )
    # current_topic 不一致 + Quiet Hours 中 (=cost 0.9 で aggregate 大幅下落)
    listener = {
        "current_topic": "build",
        "risk_score": 0.2,
        "focus_level": 0.5,
        "in_quiet_hours": True,
    }
    utterance = loop.tick(now=_at(10), listener_state=listener)
    assert utterance is None
    suppressed = loop.latest_suppressed(n=5)
    assert len(suppressed) == 1
    assert suppressed[0].reason == "gift_value_below_threshold"


def test_latest_utterances_is_empty_initially(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(quiet_hours=guard)
    assert loop.latest_utterances(n=10) == []
    assert loop.latest_suppressed(n=10) == []


def test_is_running_initially_false(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(quiet_hours=guard)
    assert loop.is_running is False


def test_start_sets_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """start() で is_running が True に、stop() で False に."""
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(
        quiet_hours=guard,
        tick_interval_seconds=10.0,  # 長め (テストでは timer 実行を待たない)
        stimulus_source=lambda: "test",
    )
    loop.start()
    try:
        assert loop.is_running is True
    finally:
        loop.stop()
    assert loop.is_running is False


def test_start_twice_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(quiet_hours=guard, tick_interval_seconds=10.0)
    loop.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            loop.start()
    finally:
        loop.stop()


def test_stop_when_not_started_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    """未起動状態で stop() を呼んでもエラーにならない (idempotent)."""
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(quiet_hours=guard)
    loop.stop()  # raise しないこと
    loop.stop()  # 2 回呼んでも OK
    assert loop.is_running is False


def test_autonomous_tick_fires_within_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """短周期で start()→ utterance が記録される (実機 timer 検証)."""
    import time

    # Quiet Hours 無効化 (常に Active)
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "0")
    guard = QuietHoursGuard()

    call_count = {"n": 0}

    def stimulus() -> str:
        call_count["n"] += 1
        return f"important topic update #{call_count['n']}"

    loop = ProactiveLoop(
        quiet_hours=guard,
        tick_interval_seconds=0.05,  # 50ms
        stimulus_source=stimulus,
    )
    loop.start()
    try:
        time.sleep(0.3)  # 6 tick 程度
    finally:
        loop.stop()

    # 少なくとも 1 回は stimulus が呼ばれている
    assert call_count["n"] >= 1
    # 発話 or 抑制履歴のどちらかに残っているはず
    total = len(loop.latest_utterances(n=50)) + len(loop.latest_suppressed(n=50))
    assert total >= 1


# ---------------------------------------------------------------------------
# curiosity mode (COG-MESH-06, Phase 6 M8.7 prototype)
# ---------------------------------------------------------------------------


def test_tick_curiosity_without_coverage_source_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(quiet_hours=guard)
    with pytest.raises(NotImplementedError, match="coverage_source"):
        loop.tick_curiosity(now=_at(10))


def test_tick_curiosity_emits_when_layer_is_thin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = _make_guard(monkeypatch)
    coverage = {"semantic": 0.9, "episodic": 0.2, "structural": 0.6, "parameter": 0.4}
    loop = ProactiveLoop(
        quiet_hours=guard,
        coverage_source=lambda: coverage,
        curiosity_threshold=0.5,
    )
    listener = {
        "current_topic": "memory",
        "risk_score": 0.8,
        "focus_level": 0.3,
        "in_quiet_hours": False,
    }
    utterance = loop.tick_curiosity(now=_at(10), listener_state=listener)
    assert utterance is not None
    assert utterance.mode == "curiosity"
    # 最も薄い layer (episodic 0.2) が話題に
    assert "episodic" in utterance.content
    assert "0.20" in utterance.content


def test_tick_curiosity_returns_none_when_all_layers_covered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = _make_guard(monkeypatch)
    coverage = {"semantic": 0.9, "episodic": 0.8, "structural": 0.7, "parameter": 0.95}
    loop = ProactiveLoop(
        quiet_hours=guard,
        coverage_source=lambda: coverage,
        curiosity_threshold=0.5,
    )
    assert loop.tick_curiosity(now=_at(10)) is None


def test_tick_curiosity_blocked_in_quiet_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = _make_guard(monkeypatch)
    loop = ProactiveLoop(
        quiet_hours=guard,
        coverage_source=lambda: {"semantic": 0.1},
    )
    # Quiet Hours 02:00 → coverage が薄くても発話しない
    assert loop.tick_curiosity(now=_at(2)) is None
