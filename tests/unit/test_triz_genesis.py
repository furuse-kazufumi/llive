# SPDX-License-Identifier: Apache-2.0
"""TRIZ Trigger Genesis (A-2) の単体テスト.

T-Z1..4 4 種すべての検出経路 + StimulusSource protocol 適合 + 既存
ContradictionDetector との統合を確認する。
"""

from __future__ import annotations

from llive.fullsense.triz_genesis import (
    TrizGenesisSource,
    TZ1GoalProgressConfig,
    TZ3OppositePref,
    TZ4ResourceConfig,
)
from llive.fullsense.types import EpistemicType

# ---------------------------------------------------------------------------
# T-Z2 — technical contradiction (既存 detector 経由)
# ---------------------------------------------------------------------------


def test_t_z2_detected_from_existing_detector() -> None:
    g = TrizGenesisSource()
    # 既定 registry にある 2 metric — latency 下げる方向 (improvement) +
    # pollution_ratio が上がる方向 (degrade) のパターンを作る
    for _ in range(10):
        g.observe("pipeline.latency_ms", 200.0)
        g.observe("memory.pollution_ratio", 0.1)
    for _ in range(10):
        g.observe("pipeline.latency_ms", 80.0)        # improvement
        g.observe("memory.pollution_ratio", 0.5)      # degradation
    s = g.poll()
    assert s is not None
    assert s.source.startswith("triz-genesis:t-z2:")
    assert "T-Z2" in s.content
    assert "improving" in s.content.lower()
    assert s.epistemic_type is EpistemicType.NORMATIVE


def test_t_z2_queue_consumed_one_per_poll() -> None:
    """複数矛盾が検出されても 1 poll につき 1 件だけ返る."""
    g = TrizGenesisSource()
    for _ in range(10):
        g.observe("pipeline.latency_ms", 200.0)
        g.observe("pipeline.throughput", 100.0)
        g.observe("memory.pollution_ratio", 0.1)
    for _ in range(10):
        g.observe("pipeline.latency_ms", 80.0)
        g.observe("pipeline.throughput", 200.0)
        g.observe("memory.pollution_ratio", 0.5)
    first = g.poll()
    second = g.poll()
    assert first is not None
    assert second is not None
    # 同じ contradiction_id は二度出ない (queue から取り出し)
    assert first.source != second.source


# ---------------------------------------------------------------------------
# T-Z1 — administrative contradiction (goal stagnation)
# ---------------------------------------------------------------------------


def test_t_z1_fires_when_goal_progress_stagnates() -> None:
    g = TrizGenesisSource(
        goal_progress=TZ1GoalProgressConfig(
            window=10, stagnation_epsilon=0.01, cooldown_s=0.0
        )
    )
    # progress が 0.5 で固定 = 停滞
    for _ in range(10):
        g.observe("goal.progress", 0.5)
    s = g.detect_t_z1()
    assert s is not None
    assert s.source == "triz-genesis:t-z1"
    assert "T-Z1" in s.content
    assert "stagnant" in s.content.lower()


def test_t_z1_does_not_fire_when_progress_grows() -> None:
    g = TrizGenesisSource(
        goal_progress=TZ1GoalProgressConfig(
            window=10, stagnation_epsilon=0.01, cooldown_s=0.0
        )
    )
    for i in range(10):
        g.observe("goal.progress", 0.1 * (i + 1))
    s = g.detect_t_z1()
    assert s is None  # 0.1 -> 1.0 で十分伸びている


def test_t_z1_cooldown_prevents_refire() -> None:
    g = TrizGenesisSource(
        goal_progress=TZ1GoalProgressConfig(
            window=10, stagnation_epsilon=0.01, cooldown_s=10.0
        )
    )
    for _ in range(10):
        g.observe("goal.progress", 0.5)
    first = g.detect_t_z1()
    second = g.detect_t_z1()
    assert first is not None
    assert second is None  # cooldown 中


# ---------------------------------------------------------------------------
# T-Z3 — physical contradiction (opposite preferences)
# ---------------------------------------------------------------------------


def test_t_z3_fires_for_opposite_prefs() -> None:
    pref = TZ3OppositePref(
        metric_name="memory.size",
        pref_a="large for capacity",
        pref_b="small for latency",
    )
    g = TrizGenesisSource(opposite_prefs=[pref])
    g.observe("memory.size", 1024)
    s = g.detect_t_z3()
    assert s is not None
    assert "T-Z3" in s.content
    assert "large for capacity" in s.content
    assert "small for latency" in s.content
    assert s.source == "triz-genesis:t-z3:memory.size"


def test_t_z3_skipped_if_metric_not_observed() -> None:
    pref = TZ3OppositePref(
        metric_name="memory.size",
        pref_a="large",
        pref_b="small",
    )
    g = TrizGenesisSource(opposite_prefs=[pref])
    # 観測なし
    s = g.detect_t_z3()
    assert s is None


# ---------------------------------------------------------------------------
# T-Z4 — resource contradiction (gap between available & access)
# ---------------------------------------------------------------------------


def test_t_z4_fires_on_resource_gap() -> None:
    cfg = TZ4ResourceConfig(
        available_metric="gpu.available",
        access_metric="gpu.accessed",
        gap_threshold=0.3,
    )
    g = TrizGenesisSource(resource_pairs=[cfg])
    g.observe("gpu.available", 0.9)
    g.observe("gpu.accessed", 0.4)
    s = g.detect_t_z4()
    assert s is not None
    assert "T-Z4" in s.content
    assert "gap=0.50" in s.content
    assert s.source == "triz-genesis:t-z4:gpu.available"


def test_t_z4_not_fired_when_gap_small() -> None:
    cfg = TZ4ResourceConfig(
        available_metric="gpu.available",
        access_metric="gpu.accessed",
        gap_threshold=0.3,
    )
    g = TrizGenesisSource(resource_pairs=[cfg])
    g.observe("gpu.available", 0.9)
    g.observe("gpu.accessed", 0.8)
    s = g.detect_t_z4()
    assert s is None


def test_t_z4_skipped_until_both_observed() -> None:
    cfg = TZ4ResourceConfig(
        available_metric="cpu.available",
        access_metric="cpu.accessed",
        gap_threshold=0.3,
    )
    g = TrizGenesisSource(resource_pairs=[cfg])
    g.observe("cpu.available", 0.9)
    # access metric は未観測
    s = g.detect_t_z4()
    assert s is None


# ---------------------------------------------------------------------------
# StimulusSource protocol — poll()
# ---------------------------------------------------------------------------


def test_poll_returns_none_when_nothing() -> None:
    g = TrizGenesisSource()
    assert g.poll() is None


def test_poll_priority_t_z2_over_t_z1() -> None:
    """T-Z2 が出るなら T-Z1 より優先される (severity 期待値が高い順)."""
    g = TrizGenesisSource(
        goal_progress=TZ1GoalProgressConfig(
            window=10, stagnation_epsilon=0.01, cooldown_s=0.0
        )
    )
    # T-Z1 candidate: 停滞 progress
    for _ in range(10):
        g.observe("goal.progress", 0.5)
    # T-Z2 candidate: latency improve / pollution degrade
    for _ in range(10):
        g.observe("pipeline.latency_ms", 200.0)
        g.observe("memory.pollution_ratio", 0.1)
    for _ in range(10):
        g.observe("pipeline.latency_ms", 80.0)
        g.observe("memory.pollution_ratio", 0.5)
    s = g.poll()
    assert s is not None
    assert s.source.startswith("triz-genesis:t-z2:")


def test_poll_falls_back_to_t_z1_when_no_others() -> None:
    g = TrizGenesisSource(
        goal_progress=TZ1GoalProgressConfig(
            window=10, stagnation_epsilon=0.01, cooldown_s=0.0
        )
    )
    for _ in range(10):
        g.observe("goal.progress", 0.5)
    s = g.poll()
    assert s is not None
    assert s.source == "triz-genesis:t-z1"


def test_observe_many_routes_to_each_observer() -> None:
    g = TrizGenesisSource()
    g.observe_many({"pipeline.latency_ms": 100.0, "goal.progress": 0.5})
    # ContradictionDetector の registry に登録された metric は detector へ
    # 渡るが、未登録 (goal.progress) はスキップされる挙動を確認
    assert "pipeline.latency_ms" in g._latest_metrics
    assert "goal.progress" in g._latest_metrics


def test_epistemic_type_can_be_overridden() -> None:
    g = TrizGenesisSource(epistemic_type=EpistemicType.INTERPRETIVE)
    for _ in range(10):
        g.observe("pipeline.latency_ms", 200.0)
        g.observe("memory.pollution_ratio", 0.1)
    for _ in range(10):
        g.observe("pipeline.latency_ms", 80.0)
        g.observe("memory.pollution_ratio", 0.5)
    s = g.poll()
    assert s is not None
    assert s.epistemic_type is EpistemicType.INTERPRETIVE
