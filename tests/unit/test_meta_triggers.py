# SPDX-License-Identifier: Apache-2.0
"""Meta-trigger source (A-3) — §3.4 T-M1..3 の単体テスト.

最小依存で動かすため、ResidentRunner は実起動せず snapshot を直接構築可能な
fake で代替する。SandboxOutputBus は実物を使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from llive.fullsense.meta_triggers import MetaTriggerConfig, MetaTriggerSource
from llive.fullsense.runner import Phase, RunnerSnapshot
from llive.fullsense.sandbox import SandboxOutputBus, SandboxRecord
from llive.fullsense.types import (
    ActionDecision,
    ActionPlan,
    EpistemicType,
    Stimulus,
    Thought,
)


@dataclass
class FakeRunner:
    """ResidentRunner snapshot のみ提供する最小 stub."""

    counts: dict[str, int] = field(default_factory=lambda: {"fast": 0, "medium": 0, "slow": 0})
    phase: Phase = Phase.AWAKE

    def snapshot(self) -> RunnerSnapshot:
        return RunnerSnapshot(
            phase=self.phase,
            running=True,
            started_at=0.0,
            cycle_counts=dict(self.counts),
            window_cycle_counts=dict(self.counts),
            last_phase_transition_at=0.0,
        )


def _emit(
    bus: SandboxOutputBus,
    *,
    decision: ActionDecision = ActionDecision.SILENT,
    content: str = "x",
    triz: list[int] | None = None,
) -> None:
    bus.emit(
        SandboxRecord(
            stim=Stimulus(content=content, source="manual", surprise=0.5),
            plan=ActionPlan(
                decision=decision,
                rationale="r",
                thought=Thought(text="t", triz_principles=triz or []),
            ),
        )
    )


# ---------------------------------------------------------------------------
# T-M1 reflective
# ---------------------------------------------------------------------------


def test_t_m1_silent_bias_detected() -> None:
    bus = SandboxOutputBus()
    for _ in range(10):
        _emit(bus, decision=ActionDecision.SILENT, content=f"varied-{_}")
    meta = MetaTriggerSource(runner=FakeRunner(), output_bus=bus)
    s = meta.detect_t_m1()
    assert s is not None
    assert "silent" in s.content.lower() or "SILENT" in s.content
    assert s.source == "meta:t-m1:silent-bias"
    assert s.epistemic_type is EpistemicType.NORMATIVE


def test_t_m1_repeat_pattern_detected() -> None:
    bus = SandboxOutputBus()
    # silent ratio を 70% 未満にしつつ繰り返し閾値を超える
    for _ in range(5):
        _emit(bus, decision=ActionDecision.NOTE, content="same-stim")
    for _ in range(5):
        _emit(bus, decision=ActionDecision.PROPOSE, content="varied")
    meta = MetaTriggerSource(runner=FakeRunner(), output_bus=bus)
    s = meta.detect_t_m1()
    assert s is not None
    assert "recurs" in s.content
    assert s.source == "meta:t-m1:repeat"


def test_t_m1_no_fire_when_balanced() -> None:
    bus = SandboxOutputBus()
    for i in range(10):
        _emit(
            bus,
            decision=ActionDecision.NOTE if i % 2 == 0 else ActionDecision.PROPOSE,
            content=f"unique-{i}",
        )
    meta = MetaTriggerSource(runner=FakeRunner(), output_bus=bus)
    s = meta.detect_t_m1()
    assert s is None


# ---------------------------------------------------------------------------
# T-M2 spec-drift
# ---------------------------------------------------------------------------


def test_t_m2_f3_drift_detected_after_no_triz_streak() -> None:
    bus = SandboxOutputBus()
    for _ in range(15):
        _emit(bus, decision=ActionDecision.NOTE, content="x", triz=[])
    meta = MetaTriggerSource(runner=FakeRunner(), output_bus=bus)
    s = meta.detect_t_m2()
    assert s is not None
    assert "T-M2" in s.content
    assert "F3" in s.content or "TRIZ" in s.content
    assert s.source == "meta:t-m2:f3-drift"


def test_t_m2_no_drift_when_triz_recent() -> None:
    bus = SandboxOutputBus()
    for _ in range(15):
        _emit(bus, decision=ActionDecision.NOTE, content="x", triz=[1, 15])
    meta = MetaTriggerSource(runner=FakeRunner(), output_bus=bus)
    s = meta.detect_t_m2()
    assert s is None


def test_t_m2_tier_imbalance_detected() -> None:
    bus = SandboxOutputBus()
    # triz は出させて F3 drift を回避
    for _ in range(20):
        _emit(bus, decision=ActionDecision.NOTE, content="x", triz=[1])
    fake = FakeRunner(counts={"fast": 100, "medium": 1, "slow": 0})
    meta = MetaTriggerSource(
        runner=fake,
        output_bus=bus,
        config=MetaTriggerConfig(drift_window=20),
    )
    s = meta.detect_t_m2()
    assert s is not None
    assert "tier" in s.content.lower() or "imbalance" in s.content.lower()
    assert s.source == "meta:t-m2:tier-imbalance"


# ---------------------------------------------------------------------------
# T-M3 succession
# ---------------------------------------------------------------------------


def test_t_m3_fires_on_long_run_with_high_silent() -> None:
    bus = SandboxOutputBus()
    for _ in range(20):
        _emit(bus, decision=ActionDecision.SILENT, content=f"u-{_}")
    fake = FakeRunner(counts={"fast": 400, "medium": 100, "slow": 50})
    meta = MetaTriggerSource(runner=fake, output_bus=bus)
    s = meta.detect_t_m3()
    assert s is not None
    assert "T-M3" in s.content
    assert "succession" in s.content.lower()
    assert s.source == "meta:t-m3:long-run"


def test_t_m3_no_fire_when_total_cycles_low() -> None:
    bus = SandboxOutputBus()
    for _ in range(20):
        _emit(bus, decision=ActionDecision.SILENT)
    fake = FakeRunner(counts={"fast": 10, "medium": 5, "slow": 2})
    meta = MetaTriggerSource(runner=fake, output_bus=bus)
    s = meta.detect_t_m3()
    assert s is None


def test_t_m3_no_fire_when_silent_rate_low() -> None:
    bus = SandboxOutputBus()
    for i in range(20):
        _emit(
            bus,
            decision=ActionDecision.NOTE if i < 18 else ActionDecision.SILENT,
        )
    fake = FakeRunner(counts={"fast": 400, "medium": 100, "slow": 50})
    meta = MetaTriggerSource(runner=fake, output_bus=bus)
    s = meta.detect_t_m3()
    assert s is None


# ---------------------------------------------------------------------------
# poll() priority
# ---------------------------------------------------------------------------


def test_poll_priority_t_m2_over_others() -> None:
    bus = SandboxOutputBus()
    for _ in range(15):
        _emit(bus, decision=ActionDecision.SILENT, content="x", triz=[])
    fake = FakeRunner(counts={"fast": 400, "medium": 100, "slow": 50})
    meta = MetaTriggerSource(runner=fake, output_bus=bus)
    s = meta.poll()
    assert s is not None
    assert s.source.startswith("meta:t-m2")


def test_poll_returns_none_when_no_trigger() -> None:
    bus = SandboxOutputBus()
    meta = MetaTriggerSource(runner=FakeRunner(), output_bus=bus)
    assert meta.poll() is None


def test_cooldown_prevents_t_m1_refire() -> None:
    bus = SandboxOutputBus()
    for _ in range(10):
        _emit(bus, decision=ActionDecision.SILENT)
    meta = MetaTriggerSource(
        runner=FakeRunner(),
        output_bus=bus,
        config=MetaTriggerConfig(cooldown_s=10.0),
    )
    first = meta.detect_t_m1()
    second = meta.detect_t_m1()
    assert first is not None
    assert second is None
