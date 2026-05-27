# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/poc_evolutionary_activity_modes.py.

Bedau 進化的活動統計 (evolutionary activity) + 中立シャドウ計器の PoC を検証する。
LLM/Docker/genome ゼロの CPU 純関数 + 決定論 seed 検証:
  * activity 累積 (update_activity) と concentration の単体。
  * 中立シャドウ閾値 (shadow_threshold) が neutral 分布から正しく出る。
  * Bedau メトリクス (diversity / total_activity / new_activity / supra_neutral_count)。
  * 3 レジーム verdict (決定論 seed 固定): adaptive の A_new > neutral の A_new、
    adaptive supra-neutral component 種数 > saturated、modes_detects_openendedness is True。

honest: これは計器の弁別力テストであり実 llive 開放端性の主張ではない
([[feedback_benchmark_honest_disclosure]])。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import poc_evolutionary_activity_modes as eam  # noqa: E402


# ---------------------------------------------------------------------------
# concentration
# ---------------------------------------------------------------------------

def test_concentration_basic_fractions():
    """concentration[i] = i を持つ個体の割合 (presence ベース)。"""
    # 4 個体, component 語彙 4。
    pop = np.array([
        [0, 1],   # 0,1 を持つ
        [0, 2],   # 0,2
        [1, 1],   # 1 (重複は 1 個体 1 回; presence)
        [3, 3],   # 3
    ])
    conc = eam.concentration(pop, n_components=4)
    # component 0: 個体 0,1 が持つ → 2/4 = 0.5
    # component 1: 個体 0,2 → 0.5
    # component 2: 個体 1 → 0.25
    # component 3: 個体 3 → 0.25
    assert conc.tolist() == pytest.approx([0.5, 0.5, 0.25, 0.25])


def test_concentration_multiset_counts_presence_once():
    """同一個体内の重複 component は presence として 1 回しか数えない。"""
    pop = np.array([[2, 2, 2, 2]])  # 1 個体が component 2 を 4 回
    conc = eam.concentration(pop, n_components=4)
    assert conc[2] == pytest.approx(1.0)  # 1/1 個体
    assert conc[0] == 0.0 and conc[1] == 0.0 and conc[3] == 0.0


def test_concentration_empty_population():
    conc = eam.concentration(np.empty((0, 3), dtype=int), n_components=5)
    assert conc.tolist() == [0.0] * 5


def test_concentration_in_unit_range():
    rng = np.random.default_rng(7)
    pop = rng.integers(0, 16, (32, 8))
    conc = eam.concentration(pop, n_components=16)
    assert np.all(conc >= 0.0) and np.all(conc <= 1.0)


# ---------------------------------------------------------------------------
# update_activity (cumulative)
# ---------------------------------------------------------------------------

def test_update_activity_accumulates():
    activity = np.zeros(3)
    conc1 = np.array([0.5, 0.0, 1.0])
    a1 = eam.update_activity(activity, conc1)
    assert a1.tolist() == [0.5, 0.0, 1.0]
    conc2 = np.array([0.25, 1.0, 0.0])
    a2 = eam.update_activity(a1, conc2)
    assert a2.tolist() == [0.75, 1.0, 1.0]


def test_update_activity_is_pure():
    """純関数: 入力配列を破壊しない (新配列を返す)。"""
    activity = np.zeros(3)
    eam.update_activity(activity, np.array([1.0, 1.0, 1.0]))
    assert activity.tolist() == [0.0, 0.0, 0.0]


def test_update_activity_persistent_component_grows_monotonically():
    """毎世代 conc>0 の component は単調増加 (Bedau の核: 持続するほど累積)。"""
    activity = np.zeros(2)
    for _ in range(10):
        activity = eam.update_activity(activity, np.array([0.3, 0.0]))
    assert activity[0] == pytest.approx(3.0)  # 0.3 * 10
    assert activity[1] == 0.0                  # 一度も存在しない → 累積ゼロ


# ---------------------------------------------------------------------------
# diversity / total_activity / mean_cumulative_activity
# ---------------------------------------------------------------------------

def test_diversity_counts_present_components():
    conc = np.array([0.5, 0.0, 0.1, 0.0])
    assert eam.diversity(conc) == 2


def test_total_activity_is_sum():
    activity = np.array([1.0, 2.0, 3.0])
    assert eam.total_activity(activity) == pytest.approx(6.0)


def test_mean_cumulative_activity_over_present_only():
    activity = np.array([4.0, 0.0, 2.0])
    conc = np.array([0.5, 0.0, 0.25])  # component 1 不在 → 平均から除外
    # present = {0, 2}, mean = (4+2)/2 = 3.0
    assert eam.mean_cumulative_activity(activity, conc) == pytest.approx(3.0)


def test_mean_cumulative_activity_no_present_is_zero():
    assert eam.mean_cumulative_activity(np.array([1.0, 2.0]), np.array([0.0, 0.0])) == 0.0


# ---------------------------------------------------------------------------
# new_activity / supra_neutral_count (supra-neutral 計器の核)
# ---------------------------------------------------------------------------

def test_new_activity_sums_supra_shadow_only():
    activity = np.array([10.0, 5.0, 20.0, 1.0])
    # a_shadow=6 → 10 と 20 が超える → 和=30
    assert eam.new_activity(activity, a_shadow=6.0) == pytest.approx(30.0)


def test_new_activity_none_above_shadow_is_zero():
    activity = np.array([1.0, 2.0, 3.0])
    assert eam.new_activity(activity, a_shadow=100.0) == 0.0


def test_supra_neutral_count_counts_above_shadow():
    activity = np.array([10.0, 5.0, 20.0, 1.0, 7.0])
    assert eam.supra_neutral_count(activity, a_shadow=6.0) == 3  # 10, 20, 7


def test_supra_neutral_count_none_above_is_zero():
    assert eam.supra_neutral_count(np.array([1.0, 2.0]), a_shadow=5.0) == 0


# ---------------------------------------------------------------------------
# shadow_threshold (中立シャドウ閾値が neutral 分布から出る)
# ---------------------------------------------------------------------------

def test_shadow_threshold_max_at_percentile_100():
    neutral = np.array([1.0, 5.0, 3.0, 8.0, 2.0])
    assert eam.shadow_threshold(neutral, percentile=100.0) == pytest.approx(8.0)


def test_shadow_threshold_percentile_below_max():
    neutral = np.arange(0.0, 101.0)  # 0..100
    thr = eam.shadow_threshold(neutral, percentile=99.0)
    # 99 パーセンタイル ≒ 99, max(100) より小さい
    assert 98.0 <= thr <= 100.0
    assert thr < eam.shadow_threshold(neutral, percentile=100.0)


def test_shadow_threshold_empty_is_zero():
    assert eam.shadow_threshold(np.array([]), percentile=99.0) == 0.0


def test_shadow_threshold_from_neutral_run_distribution():
    """neutral ラン (無選択) の最終 activity 分布から閾値が出ること (統合)。"""
    tr = eam.run_mode("neutral", gens=120, pop=48, seed=0, a_shadow=0.0)
    final = np.asarray(tr.final_activity)
    thr = eam.shadow_threshold(final, percentile=99.0)
    # 閾値は分布内 (min..max) に収まる正の値。
    assert 0.0 < thr <= float(final.max())


# ---------------------------------------------------------------------------
# run_mode 構造的性質
# ---------------------------------------------------------------------------

def test_run_mode_records_full_series():
    tr = eam.run_mode("adaptive", gens=50, pop=32, seed=1, a_shadow=10.0)
    assert len(tr.diversity) == 50
    assert len(tr.total_activity) == 50
    assert len(tr.new_activity) == 50
    assert len(tr.supra_count) == 50
    assert len(tr.final_activity) == eam.N_COMPONENTS


def test_run_mode_total_activity_non_decreasing():
    """cumulative activity の総和は単調非減少 (各世代 conc>=0 を足すため)。"""
    tr = eam.run_mode("adaptive", gens=80, pop=48, seed=2, a_shadow=10.0)
    ta = np.asarray(tr.total_activity)
    assert np.all(np.diff(ta) >= -1e-9)


def test_run_mode_deterministic_same_seed():
    """同 seed は同結果 (決定論)。"""
    t1 = eam.run_mode("adaptive", gens=60, pop=32, seed=5, a_shadow=10.0)
    t2 = eam.run_mode("adaptive", gens=60, pop=32, seed=5, a_shadow=10.0)
    assert t1.final_activity == t2.final_activity
    assert t1.a_new_tail_mean == t2.a_new_tail_mean


def test_run_mode_different_seed_differs():
    t1 = eam.run_mode("adaptive", gens=60, pop=32, seed=5, a_shadow=10.0)
    t2 = eam.run_mode("adaptive", gens=60, pop=32, seed=6, a_shadow=10.0)
    assert t1.final_activity != t2.final_activity


# ---------------------------------------------------------------------------
# 3 レジーム verdict (決定論; 計器の弁別力)
# ---------------------------------------------------------------------------

def test_compare_modes_adaptive_a_new_exceeds_neutral():
    """命題(1)+(2): adaptive の A_new(tail) は neutral の A_new(tail) を大きく上回る。"""
    traces, verdict = eam.compare_modes(gens=400, pop=96, seed=0)
    assert verdict.a_new_adaptive > verdict.a_new_neutral
    # neutral はほぼゼロ (無選択 → supra-neutral 活動は出ない)。
    assert verdict.a_new_neutral < 10.0
    # adaptive は明確な supra-neutral 活動を持つ。
    assert verdict.a_new_adaptive > 100.0


def test_compare_modes_neutral_near_zero():
    """命題(2): neutral は supra-neutral 活動 ≈ 0。"""
    _, verdict = eam.compare_modes(gens=400, pop=96, seed=0)
    assert verdict.neutral_near_zero is True
    assert verdict.supra_count_neutral < 1.0  # ほぼどの component も shadow を越えない


def test_compare_modes_adaptive_supra_count_exceeds_saturated():
    """命題(3): adaptive は saturated より多くの component が shadow を越える (開放端獲得)。

    A_new (活動和) 単独では saturated も持続成分で膨らむため、種数で区別する (honest)。
    """
    _, verdict = eam.compare_modes(gens=400, pop=96, seed=0)
    assert verdict.supra_count_adaptive > verdict.supra_count_saturated
    assert verdict.supra_count_adaptive > 2.0 * verdict.supra_count_saturated


def test_compare_modes_detects_openendedness_true_seed0():
    """総合 verdict: seed=0 で計器は 3 レジームを区別できる (modes_detects True)。"""
    _, verdict = eam.compare_modes(gens=400, pop=96, seed=0)
    assert verdict.adaptive_supra_neutral is True
    assert verdict.neutral_near_zero is True
    assert verdict.adaptive_exceeds_saturated is True
    assert verdict.modes_detects_openendedness is True


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_compare_modes_robust_seeds(seed):
    """複数 seed で弁別が頑健 (seed 依存の偶然でないことを示す)。"""
    _, verdict = eam.compare_modes(gens=400, pop=96, seed=seed)
    assert verdict.modes_detects_openendedness is True
    assert verdict.a_new_adaptive > verdict.a_new_neutral


def test_compare_modes_returns_all_three_regimes():
    traces, _ = eam.compare_modes(gens=100, pop=48, seed=0)
    assert set(traces.keys()) == {"adaptive", "neutral", "saturated"}


# ---------------------------------------------------------------------------
# main / report 出力 (json schema + verdict)
# ---------------------------------------------------------------------------

def test_main_writes_report(tmp_path):
    out_dir = tmp_path / "modes_out"
    rc = eam.main(["--gens", "120", "--pop", "48", "--seed", "0",
                   "--out", str(out_dir)])
    assert rc == 0
    out_json = out_dir / "modes.json"
    assert out_json.exists()
    import json
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["schema"] == eam._SCHEMA
    assert "proposition" in report
    assert set(report["regimes"].keys()) == {"adaptive", "neutral", "saturated"}
    assert "modes_detects_openendedness" in report["verdict"]
    assert report["honest_notes"]  # honest 留保が記録されている


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
