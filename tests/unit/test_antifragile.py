# SPDX-License-Identifier: Apache-2.0
"""EVO-ANTIFRAGILE: AntifragileController panic state machine.

fail-closed default / opt-in / cooldown / surprise 回復 / user_stop /
探索増幅 / 対立 pair unlock / audit chain 記録 / honest disclosure を網羅。
"""

from __future__ import annotations

from llive.evolution.antifragile import (
    AUTO_ENV_VAR,
    DEFAULT_CONFLICT_PAIRS,
    AntifragileConfig,
    AntifragileController,
    ConflictPair,
    PanicState,
)
from llive.memory.bayesian_surprise import BayesianSurpriseGate


class FakeClock:
    """注入可能な単調時計。``advance`` で任意に時間を進める。"""

    def __init__(self, start: float = 0.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += float(dt)


class FakeAudit:
    """AuditTrail 互換の in-memory fake (append(actor, action, payload))。"""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def append(self, actor: str, action: str, payload: dict | None = None):
        entry = {"seq": len(self.entries), "actor": actor, "action": action, "payload": payload or {}}
        self.entries.append(entry)
        return entry

    def actions(self) -> list[str]:
        return [e["action"] for e in self.entries]


def _enabled(**overrides) -> AntifragileConfig:
    overrides.setdefault("enabled", True)
    overrides.setdefault("cold_threshold", 0.8)
    return AntifragileConfig(**overrides)


# -- config validation -----------------------------------------------------


def test_default_config_is_fail_closed():
    cfg = AntifragileConfig()
    assert cfg.enabled is False
    assert cfg.exploration_multiplier == 10.0
    assert cfg.conflict_pairs == DEFAULT_CONFLICT_PAIRS


def test_config_rejects_bad_params():
    import pytest

    with pytest.raises(ValueError):
        AntifragileConfig(exploration_multiplier=0.5)
    with pytest.raises(ValueError):
        AntifragileConfig(recovery_ratio=0.0)
    with pytest.raises(ValueError):
        AntifragileConfig(recovery_ratio=1.5)
    with pytest.raises(ValueError):
        AntifragileConfig(cooldown_s=0.0)
    with pytest.raises(ValueError):
        AntifragileConfig(ucb_clip=-1.0)


def test_from_env_enables_on_truthy(monkeypatch):
    for token in ("1", "true", "TRUE", "yes", "On"):
        cfg = AntifragileConfig.from_env({AUTO_ENV_VAR: token})
        assert cfg.enabled is True
    for token in ("0", "false", "", "no", "off"):
        cfg = AntifragileConfig.from_env({AUTO_ENV_VAR: token})
        assert cfg.enabled is False


def test_from_env_override_beats_env():
    cfg = AntifragileConfig.from_env({AUTO_ENV_VAR: "true"}, enabled=False)
    assert cfg.enabled is False
    cfg2 = AntifragileConfig.from_env({AUTO_ENV_VAR: "false"}, enabled=True)
    assert cfg2.enabled is True


def test_from_env_reads_os_environ_by_default(monkeypatch):
    monkeypatch.setenv(AUTO_ENV_VAR, "true")
    assert AntifragileConfig.from_env().enabled is True
    monkeypatch.delenv(AUTO_ENV_VAR, raising=False)
    assert AntifragileConfig.from_env().enabled is False


# -- fail-closed ------------------------------------------------------------


def test_disabled_never_panics_but_counts_suppressed():
    ctrl = AntifragileController(AntifragileConfig(enabled=False, cold_threshold=0.5))
    assert ctrl.observe_surprise(0.99) is False
    assert ctrl.observe_surprise(0.99) is False
    assert ctrl.is_panic is False
    d = ctrl.disclosure()
    assert d["enabled"] is False
    assert d["suppressed_triggers"] == 2
    assert d["episodes"] == 0


def test_disabled_does_not_record_normal_ops():
    audit = FakeAudit()
    ctrl = AntifragileController(AntifragileConfig(enabled=False), audit_trail=audit)
    ctrl.record_change_op("noop")
    assert audit.entries == []


# -- enter / exit transitions ----------------------------------------------


def test_enters_panic_above_threshold():
    clock = FakeClock()
    audit = FakeAudit()
    ctrl = AntifragileController(_enabled(), audit_trail=audit, clock=clock)
    assert ctrl.observe_surprise(0.85) is True
    assert ctrl.state is PanicState.PANIC
    assert ctrl.current_episode is not None
    assert ctrl.current_episode.trigger_surprise == 0.85
    assert "panic_enter" in audit.actions()


def test_stays_normal_below_threshold():
    ctrl = AntifragileController(_enabled(), clock=FakeClock())
    assert ctrl.observe_surprise(0.5) is False
    assert ctrl.state is PanicState.NORMAL
    assert ctrl.episodes == []


def test_cooldown_elapsed_exits_panic():
    clock = FakeClock()
    audit = FakeAudit()
    ctrl = AntifragileController(_enabled(cooldown_s=300.0), audit_trail=audit, clock=clock)
    ctrl.observe_surprise(0.9)
    assert ctrl.is_panic
    clock.advance(299.0)
    assert ctrl.tick() is True  # まだ cooldown 内
    clock.advance(2.0)  # 合計 301s > 300s
    assert ctrl.tick() is False
    assert ctrl.state is PanicState.NORMAL
    ep = ctrl.episodes[0]
    assert ep.exit_reason == "cooldown_elapsed"
    assert ep.duration_s == 301.0
    assert "panic_exit" in audit.actions()


def test_surprise_recovery_exits_panic_with_hysteresis():
    ctrl = AntifragileController(
        _enabled(cold_threshold=1.0, recovery_ratio=0.8), clock=FakeClock()
    )
    ctrl.observe_surprise(1.0)
    assert ctrl.is_panic
    # 0.85 は threshold(1.0)*0.8=0.8 を上回るのでまだ panic 継続
    assert ctrl.observe_surprise(0.85) is True
    # 0.75 < 0.8 → 回復
    assert ctrl.observe_surprise(0.75) is False
    assert ctrl.episodes[0].exit_reason == "surprise_recovered"


def test_user_stop_exits_panic():
    ctrl = AntifragileController(_enabled(), clock=FakeClock())
    ctrl.observe_surprise(0.9)
    assert ctrl.is_panic
    assert ctrl.stop() is True
    assert ctrl.state is PanicState.NORMAL
    assert ctrl.episodes[0].exit_reason == "user_stop"
    # 既に NORMAL なら False
    assert ctrl.stop() is False


def test_can_re_enter_panic_after_exit():
    clock = FakeClock()
    ctrl = AntifragileController(_enabled(cooldown_s=10.0), clock=clock)
    ctrl.observe_surprise(0.9)
    clock.advance(11.0)
    ctrl.tick()
    assert ctrl.state is PanicState.NORMAL
    ctrl.observe_surprise(0.95)
    assert ctrl.is_panic
    assert len(ctrl.episodes) == 2
    assert ctrl.episodes[1].index == 1


# -- panic-mode parameters --------------------------------------------------


def test_exploration_constant_amplified_only_in_panic():
    ctrl = AntifragileController(_enabled(exploration_multiplier=10.0), clock=FakeClock())
    assert ctrl.exploration_constant(1.4) == 1.4  # NORMAL: 素通し
    ctrl.observe_surprise(0.9)
    assert ctrl.exploration_constant(1.4) == 14.0  # PANIC: 10x
    assert ctrl.mutation_rate_multiplier == 10.0


def test_exploration_constant_clamped_to_ucb_bound():
    ctrl = AntifragileController(
        _enabled(exploration_multiplier=10.0, ucb_clip=4.0), clock=FakeClock()
    )
    ctrl.observe_surprise(0.9)
    assert ctrl.exploration_constant(1.4) == 4.0  # 14.0 を 4.0 に clamp


def test_conflict_pairs_unlocked_only_in_panic():
    ctrl = AntifragileController(_enabled(), clock=FakeClock())
    assert ctrl.unlocked_conflict_pairs() == ()
    ctrl.observe_surprise(0.9)
    pairs = ctrl.unlocked_conflict_pairs()
    assert pairs == DEFAULT_CONFLICT_PAIRS
    assert any(p.principle_a == 1 and p.principle_b == 40 for p in pairs)


def test_custom_conflict_pairs():
    custom = (ConflictPair(3, 4, "A", "B", "test"),)
    ctrl = AntifragileController(_enabled(conflict_pairs=custom), clock=FakeClock())
    ctrl.observe_surprise(0.9)
    assert ctrl.unlocked_conflict_pairs() == custom


# -- change-op auditing -----------------------------------------------------


def test_panic_ops_recorded_to_audit_chain():
    audit = FakeAudit()
    ctrl = AntifragileController(_enabled(), audit_trail=audit, clock=FakeClock())
    ctrl.observe_surprise(0.9)
    ctrl.record_change_op("op-1", outcome="success")
    ctrl.record_change_op("op-2", outcome="loss")
    change_ops = [e for e in audit.entries if e["action"] == "change_op"]
    assert len(change_ops) == 2
    assert change_ops[0]["payload"]["panic"] is True
    assert change_ops[0]["payload"]["outcome"] == "success"
    assert change_ops[0]["payload"]["episode"] == 0
    ep = ctrl.episodes[0]
    assert ep.n_ops == 2
    assert ep.n_success == 1
    assert ep.n_loss == 1


def test_normal_ops_not_recorded_by_default():
    audit = FakeAudit()
    ctrl = AntifragileController(_enabled(), audit_trail=audit, clock=FakeClock())
    ctrl.record_change_op("op-normal")
    assert [e for e in audit.entries if e["action"] == "change_op"] == []


def test_audit_all_ops_records_normal_ops():
    audit = FakeAudit()
    ctrl = AntifragileController(
        _enabled(audit_all_ops=True), audit_trail=audit, clock=FakeClock()
    )
    ctrl.record_change_op("op-normal")
    recorded = [e for e in audit.entries if e["action"] == "change_op"]
    assert len(recorded) == 1
    assert recorded[0]["payload"]["panic"] is False


def test_record_change_op_describes_change_op_objects():
    class FakeOp:
        target_container = "ctr-1"

    audit = FakeAudit()
    ctrl = AntifragileController(_enabled(), audit_trail=audit, clock=FakeClock())
    ctrl.observe_surprise(0.9)
    ctrl.record_change_op(FakeOp())
    op_entry = next(e for e in audit.entries if e["action"] == "change_op")
    assert op_entry["payload"]["op"] == "FakeOp(target=ctr-1)"


def test_works_without_audit_trail():
    ctrl = AntifragileController(_enabled(), clock=FakeClock())
    ctrl.observe_surprise(0.9)
    assert ctrl.record_change_op("op", outcome="success") is None
    assert ctrl.episodes[0].n_ops == 1  # episode カウンタは audit 無しでも進む


# -- gate integration -------------------------------------------------------


def test_uses_bayesian_gate_dynamic_threshold():
    # cold_start_theta=0.3, min_samples=3。warmup 後は mean+k*sigma の動的閾値。
    gate = BayesianSurpriseGate(k=1.0, min_samples=3, cold_start_theta=0.3)
    ctrl = AntifragileController(_enabled(), gate=gate, clock=FakeClock())
    # cold start: threshold=0.3。0.2 < 0.3 → NORMAL、gate 更新。
    assert ctrl.observe_surprise(0.2) is False
    assert ctrl.observe_surprise(0.2) is False
    # 動的閾値は低い (mean≈0.2, sigma≈0) ので高 surprise で panic。
    assert ctrl.observe_surprise(0.9) is True


def test_gate_threshold_evaluated_before_update():
    # 更新前の閾値で評価する (should_write と同順序) ことの確認。
    gate = BayesianSurpriseGate(k=1.0, min_samples=2, cold_start_theta=0.5)
    ctrl = AntifragileController(_enabled(), gate=gate, clock=FakeClock())
    # cold_start theta=0.5。0.6>=0.5 → panic。observe 後 gate.stats.n は 1 増える。
    assert ctrl.observe_surprise(0.6) is True
    assert gate.stats.n == 1


def test_update_gate_false_does_not_mutate_stats():
    gate = BayesianSurpriseGate(k=1.0, min_samples=2, cold_start_theta=0.5)
    ctrl = AntifragileController(_enabled(), gate=gate, clock=FakeClock())
    ctrl.observe_surprise(0.6, update_gate=False)
    assert gate.stats.n == 0


# -- honest disclosure ------------------------------------------------------


def test_disclosure_aggregates_episodes():
    clock = FakeClock()
    ctrl = AntifragileController(_enabled(cooldown_s=100.0), clock=clock)
    # episode 0
    ctrl.observe_surprise(0.9)
    ctrl.record_change_op("a", outcome="success")
    ctrl.record_change_op("b", outcome="success")
    ctrl.record_change_op("c", outcome="loss")
    clock.advance(50.0)
    ctrl.stop()
    # episode 1
    ctrl.observe_surprise(0.95)
    ctrl.record_change_op("d", outcome="loss")
    clock.advance(30.0)
    ctrl.stop()

    d = ctrl.disclosure()
    assert d["episodes"] == 2
    assert d["panic_ops_total"] == 4
    assert d["panic_ops_success"] == 2
    assert d["panic_ops_loss"] == 2
    assert d["success_rate"] == 0.5
    assert d["loss_rate"] == 0.5
    assert d["mean_panic_duration_s"] == 40.0  # (50+30)/2
    assert d["active_episode"] is False
    assert "honest_note" in d


def test_disclosure_rates_none_when_no_decided_ops():
    ctrl = AntifragileController(_enabled(), clock=FakeClock())
    ctrl.observe_surprise(0.9)
    ctrl.record_change_op("x")  # outcome=None
    d = ctrl.disclosure()
    assert d["success_rate"] is None
    assert d["loss_rate"] is None
    assert d["active_episode"] is True


def test_episode_to_dict_roundtrip_fields():
    ctrl = AntifragileController(_enabled(), clock=FakeClock())
    ctrl.observe_surprise(0.9)
    ctrl.stop()
    ep = ctrl.episodes[0].to_dict()
    assert ep["index"] == 0
    assert ep["exit_reason"] == "user_stop"
    assert ep["trigger_surprise"] == 0.9
    assert set(ep) >= {"started_at", "ended_at", "duration_s", "n_ops"}
