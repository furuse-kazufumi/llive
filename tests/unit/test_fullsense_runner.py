"""ResidentRunner (§4 Resident cognition / §22 SING Level 2) の単体テスト.

R1 always-on with budget / R2 multi-timescale / R3 phase manager /
R4 attention policy / R5 idle work + stop 安全性をカバー。

すべて asyncio + Sandbox 限定で完結し、ネットワーク / 外部プロセス不要。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from llive.fullsense import FullSenseLoop
from llive.fullsense.runner import (
    Phase,
    ResidentRunner,
    TimescaleConfig,
)
from llive.fullsense.triggers import QueuedStimulusSource
from llive.fullsense.types import Stimulus


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@dataclass
class CountingSource:
    """テスト用: poll 呼び出し回数を数えながら Stimulus を無限供給する."""

    payload: str = "test-stim"
    surprise: float = 0.9
    polls: int = 0
    label: str = "ext"

    def poll(self) -> Stimulus | None:
        self.polls += 1
        return Stimulus(
            content=f"{self.payload} #{self.polls}",
            source=self.label,
            surprise=self.surprise,
        )


@dataclass
class StarvingSource:
    """常に None を返す source (R5 idle path のテスト用)."""

    polls: int = 0

    def poll(self) -> Stimulus | None:
        self.polls += 1
        return None


@dataclass
class ExplodingSource:
    """poll() で例外を投げる source — runner が握り潰せることを検証."""

    raised: int = 0

    def poll(self) -> Stimulus | None:
        self.raised += 1
        raise RuntimeError("source exploded")


def _make_loop() -> FullSenseLoop:
    # salience_threshold=0 にして CountingSource の出力を必ず通す.
    return FullSenseLoop(salience_threshold=0.0, curiosity_threshold=0.5, sandbox=True)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_runner_rejects_non_sandbox_loop() -> None:
    # FullSenseLoop は sandbox=False を構築時に拒否するので、ここでは
    # 「runner は sandbox 前提の loop しか受けない」ことを間接的に確認する。
    with pytest.raises(ValueError):
        FullSenseLoop(sandbox=False)


@pytest.mark.asyncio
async def test_runner_runs_fast_timescale_in_awake_phase() -> None:
    """R1 + R2: AWAKE 中に fast tier が cycle を消化する."""
    loop = _make_loop()
    fast_src = CountingSource(label="fast")
    runner = ResidentRunner(
        loop=loop,
        fast=TimescaleConfig("fast", period_s=0.0, sources=(fast_src,)),
        medium=TimescaleConfig("medium", period_s=10.0, sources=()),
        slow=TimescaleConfig("slow", period_s=10.0, sources=()),
        phase=Phase.AWAKE,
    )
    await runner.start()
    try:
        # 十分に yield する: 100 サイクル以上は走るはず
        for _ in range(200):
            await asyncio.sleep(0)
    finally:
        await runner.stop()

    snap = runner.snapshot()
    assert snap.phase is Phase.AWAKE
    assert snap.cycle_counts["fast"] >= 5, snap
    assert snap.last_result_per_timescale["fast"] is not None


@pytest.mark.asyncio
async def test_rest_phase_suspends_fast_tier_only() -> None:
    """R3: REST phase では fast tier が止まり medium が走る."""
    loop = _make_loop()
    fast_src = CountingSource(label="fast")
    medium_src = CountingSource(label="med")
    runner = ResidentRunner(
        loop=loop,
        fast=TimescaleConfig("fast", period_s=0.0, sources=(fast_src,)),
        medium=TimescaleConfig("medium", period_s=0.0, sources=(medium_src,)),
        slow=TimescaleConfig("slow", period_s=10.0, sources=()),
        phase=Phase.REST,
    )
    await runner.start()
    try:
        for _ in range(200):
            await asyncio.sleep(0)
    finally:
        await runner.stop()

    snap = runner.snapshot()
    assert snap.cycle_counts["fast"] == 0, "fast must be suspended in REST"
    assert snap.cycle_counts["medium"] >= 1, "medium must run in REST"


@pytest.mark.asyncio
async def test_dream_phase_only_runs_slow() -> None:
    """R3: DREAM phase では slow のみ active."""
    loop = _make_loop()
    fast_src = CountingSource(label="fast")
    med_src = CountingSource(label="med")
    slow_src = CountingSource(label="slow")
    runner = ResidentRunner(
        loop=loop,
        fast=TimescaleConfig("fast", period_s=0.0, sources=(fast_src,)),
        medium=TimescaleConfig("medium", period_s=0.0, sources=(med_src,)),
        slow=TimescaleConfig("slow", period_s=0.0, sources=(slow_src,)),
        phase=Phase.DREAM,
    )
    await runner.start()
    try:
        for _ in range(200):
            await asyncio.sleep(0)
    finally:
        await runner.stop()

    snap = runner.snapshot()
    assert snap.cycle_counts["fast"] == 0
    assert snap.cycle_counts["medium"] == 0
    assert snap.cycle_counts["slow"] >= 1


@pytest.mark.asyncio
async def test_manual_phase_transition() -> None:
    """§R3 manual transition API."""
    loop = _make_loop()
    runner = ResidentRunner(
        loop=loop,
        fast=TimescaleConfig("fast", period_s=10.0, sources=()),
        medium=TimescaleConfig("medium", period_s=10.0, sources=()),
        slow=TimescaleConfig("slow", period_s=10.0, sources=()),
        phase=Phase.AWAKE,
    )
    await runner.start()
    try:
        assert runner.phase is Phase.AWAKE
        await runner.transition(Phase.REST)
        assert runner.phase is Phase.REST
        await runner.transition(Phase.DREAM)
        assert runner.phase is Phase.DREAM
    finally:
        await runner.stop()


@pytest.mark.asyncio
async def test_budget_cap_limits_cycles_per_window() -> None:
    """R1: max_cycles_per_window で 1 ウィンドウあたりの cycle を制限."""
    loop = _make_loop()
    src = CountingSource(label="fast")
    runner = ResidentRunner(
        loop=loop,
        fast=TimescaleConfig("fast", period_s=0.0, sources=(src,), max_cycles_per_window=3),
        medium=TimescaleConfig("medium", period_s=10.0, sources=()),
        slow=TimescaleConfig("slow", period_s=10.0, sources=()),
        phase=Phase.AWAKE,
        budget_window_s=3600.0,  # 試験中はリセットさせない
    )
    await runner.start()
    try:
        for _ in range(500):
            await asyncio.sleep(0)
    finally:
        await runner.stop()

    snap = runner.snapshot()
    assert snap.cycle_counts["fast"] == 3, snap
    assert snap.window_cycle_counts["fast"] == 3


@pytest.mark.asyncio
async def test_round_robin_attention_policy() -> None:
    """R4: 2 つの source を round-robin で公平に poll する."""
    loop = _make_loop()
    a = CountingSource(payload="A", label="a")
    b = CountingSource(payload="B", label="b")
    runner = ResidentRunner(
        loop=loop,
        fast=TimescaleConfig("fast", period_s=0.0, sources=(a, b)),
        medium=TimescaleConfig("medium", period_s=10.0, sources=()),
        slow=TimescaleConfig("slow", period_s=10.0, sources=()),
        phase=Phase.AWAKE,
        budget_window_s=3600.0,
    )
    await runner.start()
    try:
        for _ in range(400):
            await asyncio.sleep(0)
    finally:
        await runner.stop()

    # 両 source とも複数回 poll されているはず + 偏りが少ない
    assert a.polls >= 2
    assert b.polls >= 2
    assert abs(a.polls - b.polls) <= max(a.polls, b.polls) // 2 + 2


@pytest.mark.asyncio
async def test_starving_source_does_not_increment_cycles() -> None:
    """R5: source が常に None を返す = idle 中、cycle 数は増えない."""
    loop = _make_loop()
    starve = StarvingSource()
    runner = ResidentRunner(
        loop=loop,
        fast=TimescaleConfig("fast", period_s=0.0, sources=(starve,)),
        medium=TimescaleConfig("medium", period_s=10.0, sources=()),
        slow=TimescaleConfig("slow", period_s=10.0, sources=()),
        phase=Phase.AWAKE,
    )
    await runner.start()
    try:
        for _ in range(200):
            await asyncio.sleep(0)
    finally:
        await runner.stop()

    snap = runner.snapshot()
    assert snap.cycle_counts["fast"] == 0
    # ただし poll 自体は走っている (idle の検知に必要)
    assert starve.polls > 0


@pytest.mark.asyncio
async def test_exception_in_source_does_not_kill_runner() -> None:
    """R1: source の例外を握り潰し、always-on を維持."""
    loop = _make_loop()
    boom = ExplodingSource()
    good = CountingSource(label="good")
    runner = ResidentRunner(
        loop=loop,
        # 片方が例外でも round-robin で他方が拾える
        fast=TimescaleConfig("fast", period_s=0.0, sources=(boom, good)),
        medium=TimescaleConfig("medium", period_s=10.0, sources=()),
        slow=TimescaleConfig("slow", period_s=10.0, sources=()),
        phase=Phase.AWAKE,
        budget_window_s=3600.0,
    )
    await runner.start()
    try:
        for _ in range(300):
            await asyncio.sleep(0)
    finally:
        await runner.stop()

    snap = runner.snapshot()
    assert snap.cycle_counts["fast"] >= 1, "good source should still produce cycles"
    assert boom.raised >= 1


@pytest.mark.asyncio
async def test_stop_is_idempotent_and_cancels_cleanly() -> None:
    """stop() を二重に呼んでも安全 / await が ALL cancel を待つ."""
    loop = _make_loop()
    runner = ResidentRunner(
        loop=loop,
        fast=TimescaleConfig("fast", period_s=0.05, sources=()),
        medium=TimescaleConfig("medium", period_s=0.05, sources=()),
        slow=TimescaleConfig("slow", period_s=0.05, sources=()),
        phase=Phase.AWAKE,
    )
    await runner.start()
    assert runner.running
    await runner.stop()
    assert not runner.running
    # 二重 stop は no-op
    await runner.stop()


@pytest.mark.asyncio
async def test_phase_schedule_auto_transitions() -> None:
    """R3: phase_schedule を渡すと自動で phase が回る."""
    loop = _make_loop()
    runner = ResidentRunner(
        loop=loop,
        fast=TimescaleConfig("fast", period_s=10.0, sources=()),
        medium=TimescaleConfig("medium", period_s=10.0, sources=()),
        slow=TimescaleConfig("slow", period_s=10.0, sources=()),
        phase=Phase.AWAKE,
        phase_schedule=[(Phase.AWAKE, 0.02), (Phase.REST, 0.02), (Phase.DREAM, 0.02)],
    )
    await runner.start()
    try:
        seen: set[Phase] = set()
        for _ in range(200):
            seen.add(runner.phase)
            await asyncio.sleep(0.005)
            if len(seen) == 3:
                break
    finally:
        await runner.stop()

    assert seen == {Phase.AWAKE, Phase.REST, Phase.DREAM}


@pytest.mark.asyncio
async def test_unknown_policy_is_rejected() -> None:
    loop = _make_loop()
    with pytest.raises(ValueError):
        ResidentRunner(
            loop=loop,
            fast=TimescaleConfig("fast", period_s=0.0),
            medium=TimescaleConfig("medium", period_s=0.0),
            slow=TimescaleConfig("slow", period_s=0.0),
            policy="bogus",
        )


@pytest.mark.asyncio
async def test_snapshot_returns_independent_copy() -> None:
    """§I3 inspectable: snapshot は内部状態を漏らさない (dict は copy)."""
    loop = _make_loop()
    runner = ResidentRunner(
        loop=loop,
        fast=TimescaleConfig("fast", period_s=10.0),
        medium=TimescaleConfig("medium", period_s=10.0),
        slow=TimescaleConfig("slow", period_s=10.0),
    )
    snap = runner.snapshot()
    snap.cycle_counts["fast"] = 999
    # 内部は汚されていない
    assert runner.cycle_counts["fast"] == 0
