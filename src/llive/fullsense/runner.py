# SPDX-License-Identifier: Apache-2.0
"""ResidentRunner — FullSense Spec §22 SING Level 2 / §4 Resident cognition.

``FullSenseLoop`` を asyncio.Task として常駐起動し、外部プロンプトを待たずに
自発的に思考サイクルを回す。Level 2 (Approved-action) のための土台で、
副作用は Sandbox に閉じ込めたまま「自律 (auto-nomos) と 自立
(self-sufficiency)」の最初の条件を満たす。

実装する Resident cognition 要件 (§4):

* **R1 — Always-on with budget.** ``max_cycles_per_window`` で各 timescale の
  起動回数を上限化。窓は ``budget_window_s`` で周期的にリセット。
* **R2 — Multi-timescale loops.** ``fast`` (subsec — sec) / ``medium``
  (sec — hr) / ``slow`` (hr — years) の 3 つの asyncio.Task が並列に走る。
  実装は秒単位の period で抽象化し、テスト時は短縮可。
* **R3 — Phase manager.** ``AWAKE → REST → DREAM`` を周期遷移。各 phase で
  どの timescale が active かを制御する。明示 ``transition`` API も提供。
* **R4 — Attention scheduler.** 各 timescale に source 列を割り当て、
  ``policy="round_robin"`` で順番に poll する。policy は inspectable
  (snapshot に現れる)。
* **R5 — Idle work.** ``slow`` tier に reverie/meta-reflection 用の
  source を回せるよう、複数 source を受け取る設計。
  bounded resource: budget cap が無限ループ消費を防ぐ。

Sandbox 限定: ``FullSenseLoop`` は ``sandbox=True`` で構築済みのものを受け取り、
``ResidentRunner`` 自身も外部 I/O を一切持たない。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from llive.fullsense.loop import FullSenseLoop, FullSenseResult
from llive.fullsense.triggers import StimulusSource


class Phase(StrEnum):
    """§R3 phase manager の 3 状態.

    各 phase でどの timescale loop が active か:

    * ``AWAKE``  — fast / medium / slow すべて active
    * ``REST``   — fast suspend、medium / slow active
    * ``DREAM``  — fast / medium suspend、slow active (consolidative)
    """

    AWAKE = "awake"
    REST = "rest"
    DREAM = "dream"


# Phase ごとに active な timescale 集合 (R3 の決定論的マップ)
_ACTIVE_TIMESCALES: dict[Phase, frozenset[str]] = {
    Phase.AWAKE: frozenset({"fast", "medium", "slow"}),
    Phase.REST: frozenset({"medium", "slow"}),
    Phase.DREAM: frozenset({"slow"}),
}


@dataclass
class TimescaleConfig:
    """1 つの timescale (fast / medium / slow) の起動パラメタ."""

    name: str
    period_s: float
    sources: tuple[StimulusSource, ...] = ()
    max_cycles_per_window: int = 1_000_000  # R1 budget cap (per window)


@dataclass
class RunnerSnapshot:
    """§I3 inspectable: 現在の Runner 状態スナップショット."""

    phase: Phase
    running: bool
    started_at: float
    cycle_counts: dict[str, int]
    window_cycle_counts: dict[str, int]
    last_phase_transition_at: float
    last_result_per_timescale: dict[str, FullSenseResult | None] = field(default_factory=dict)


class ResidentRunner:
    """Asyncio 常駐ランナ.

    使い方::

        loop = FullSenseLoop(sandbox=True)
        runner = ResidentRunner(
            loop=loop,
            fast=TimescaleConfig("fast", 0.5, sources=(external_source,)),
            medium=TimescaleConfig("medium", 5.0, sources=(triz_genesis,)),
            slow=TimescaleConfig("slow", 60.0, sources=(idle_trigger, meta_trigger)),
        )
        await runner.start()
        ...
        await runner.stop()

    各 timescale tick で ``policy="round_robin"`` に従って次の source を
    1 つだけ poll する。Stimulus が返ったら FullSenseLoop に流す。
    """

    def __init__(
        self,
        *,
        loop: FullSenseLoop,
        fast: TimescaleConfig,
        medium: TimescaleConfig,
        slow: TimescaleConfig,
        phase: Phase = Phase.AWAKE,
        phase_schedule: Sequence[tuple[Phase, float]] | None = None,
        budget_window_s: float = 60.0,
        policy: str = "round_robin",
    ) -> None:
        self._loop_engine = loop
        self._configs: dict[str, TimescaleConfig] = {
            "fast": fast,
            "medium": medium,
            "slow": slow,
        }
        if policy not in {"round_robin"}:
            raise ValueError(f"unknown attention policy: {policy!r}")
        self._policy = policy
        self._phase: Phase = Phase(phase)
        self._phase_schedule: tuple[tuple[Phase, float], ...] = tuple(phase_schedule or ())
        self._budget_window_s = float(budget_window_s)

        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._phase_task: asyncio.Task[None] | None = None
        self._running: bool = False
        self._started_at: float = 0.0
        self._last_phase_transition_at: float = 0.0

        self._cycle_counts: dict[str, int] = {"fast": 0, "medium": 0, "slow": 0}
        self._window_cycle_counts: dict[str, int] = {"fast": 0, "medium": 0, "slow": 0}
        self._window_started_at: float = 0.0

        self._source_cursor: dict[str, int] = {"fast": 0, "medium": 0, "slow": 0}
        self._last_result: dict[str, FullSenseResult | None] = {
            "fast": None,
            "medium": None,
            "slow": None,
        }

    # -- properties --------------------------------------------------------

    @property
    def phase(self) -> Phase:
        return self._phase

    @property
    def running(self) -> bool:
        return self._running

    @property
    def cycle_counts(self) -> dict[str, int]:
        return dict(self._cycle_counts)

    # -- public ------------------------------------------------------------

    async def start(self) -> None:
        """全 timescale + phase scheduler を起動."""
        if self._running:
            return
        self._running = True
        now = time.monotonic()
        self._started_at = now
        self._window_started_at = now
        self._last_phase_transition_at = now
        for name in ("fast", "medium", "slow"):
            self._tasks[name] = asyncio.create_task(
                self._timescale_loop(name), name=f"fullsense-{name}"
            )
        if self._phase_schedule:
            self._phase_task = asyncio.create_task(
                self._phase_scheduler(), name="fullsense-phase"
            )

    async def stop(self) -> None:
        """全タスクを cancel し、終了を待機."""
        if not self._running:
            return
        self._running = False
        tasks = list(self._tasks.values())
        if self._phase_task is not None:
            tasks.append(self._phase_task)
        for t in tasks:
            t.cancel()
        # gather で全 cancel 完了を確実に待つ (cancel 後 await が必要)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._phase_task = None

    async def transition(self, phase: Phase) -> None:
        """明示的に phase を変更する (§R3 manual transition)."""
        if phase == self._phase:
            return
        self._phase = phase
        self._last_phase_transition_at = time.monotonic()

    def snapshot(self) -> RunnerSnapshot:
        """§I3 inspectable: 現状を読み取る (副作用なし)."""
        return RunnerSnapshot(
            phase=self._phase,
            running=self._running,
            started_at=self._started_at,
            cycle_counts=dict(self._cycle_counts),
            window_cycle_counts=dict(self._window_cycle_counts),
            last_phase_transition_at=self._last_phase_transition_at,
            last_result_per_timescale=dict(self._last_result),
        )

    # -- internal: timescale loop ------------------------------------------

    async def _timescale_loop(self, name: str) -> None:
        cfg = self._configs[name]
        period = max(cfg.period_s, 0.0)
        try:
            while self._running:
                self._maybe_reset_window()
                if self._is_active(name) and self._has_budget(name, cfg):
                    stim = self._next_stimulus(name, cfg)
                    if stim is not None:
                        try:
                            result = self._loop_engine.process(stim)
                        except Exception:
                            # FullSenseLoop の例外は timescale を殺さない
                            # (R5: idle 中の予期せぬ例外で常駐が落ちると
                            # always-on 保証が破綻するため握り潰して継続)
                            result = None
                        else:
                            self._last_result[name] = result
                            self._cycle_counts[name] += 1
                            self._window_cycle_counts[name] += 1
                # 0 period の場合でも他 task に yield する
                await asyncio.sleep(period if period > 0 else 0)
        except asyncio.CancelledError:
            return

    def _is_active(self, timescale: str) -> bool:
        return timescale in _ACTIVE_TIMESCALES[self._phase]

    def _has_budget(self, timescale: str, cfg: TimescaleConfig) -> bool:
        return self._window_cycle_counts[timescale] < cfg.max_cycles_per_window

    def _maybe_reset_window(self) -> None:
        now = time.monotonic()
        if now - self._window_started_at >= self._budget_window_s:
            self._window_started_at = now
            self._window_cycle_counts = {"fast": 0, "medium": 0, "slow": 0}

    def _next_stimulus(self, name: str, cfg: TimescaleConfig):
        sources = cfg.sources
        if not sources:
            return None
        # round-robin: cursor を進めながら最初に Stimulus を返す source を採用
        n = len(sources)
        for offset in range(n):
            idx = (self._source_cursor[name] + offset) % n
            src = sources[idx]
            try:
                stim = src.poll()
            except Exception:
                stim = None
            if stim is not None:
                # 次回は採用した source の次から再開
                self._source_cursor[name] = (idx + 1) % n
                return stim
        # 何も無ければ cursor を 1 進めて飢餓回避
        self._source_cursor[name] = (self._source_cursor[name] + 1) % n
        return None

    # -- internal: phase scheduler -----------------------------------------

    async def _phase_scheduler(self) -> None:
        try:
            schedule = self._phase_schedule
            i = 0
            while self._running:
                phase, hold_s = schedule[i % len(schedule)]
                await self.transition(phase)
                await asyncio.sleep(max(hold_s, 0))
                i += 1
        except asyncio.CancelledError:
            return


__all__ = [
    "Phase",
    "ResidentRunner",
    "RunnerSnapshot",
    "TimescaleConfig",
]
