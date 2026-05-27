# SPDX-License-Identifier: Apache-2.0
"""Tests for lldarwin Stage2 (proxy) — LLM 苦手軸 Pressure plugin.

設計: fullsense docs/vision/LLDARWIN_DESIGN.md §3。各苦手軸を関連思考因子の
case 群に写像し、lldarwin の ε-lexicase が軸ごとに specialist を保存する。
HONEST: proxy のみ (個体は実 LLM でなく genome)。mechanism feasibility 検証用。
"""
from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.individual import FitnessReport, Individual
from llive.perf.evolutionary.lldarwin import MultiPressureSelector
from llive.perf.evolutionary.population import Population
from llive.perf.evolutionary.pressures import (
    LLM_WEAKNESS_PRESSURES,
    AdaptivePercentileGate,
    ProxyPressure,
    make_pressure_fitness,
)

_BOUNDS = GenomeBounds(lower=(0.0,), upper=(1.0,))


def _ind(breakdown: dict[str, float], value: float = 0.5) -> Individual:
    """breakdown を持つ個体モック (genome 値は AdaptivePercentileGate が使わない)."""
    ind = Individual(genome=Genome(values=(value,), bounds=_BOUNDS))
    ind.record_fitness(FitnessReport(score=0.0, breakdown=breakdown))
    return ind


def test_catalog_factors_are_valid() -> None:
    """カタログの全 pressure が既知の思考因子のみ参照する (__post_init__ 検証)."""
    assert len(LLM_WEAKNESS_PRESSURES) == 5
    names = {p.name for p in LLM_WEAKNESS_PRESSURES}
    assert names == {
        "typo_robustness",
        "polysemy_wsd",
        "multistep_robustness",
        "calibration",
        "context_management",
    }


def test_unknown_factor_rejected() -> None:
    """未知の思考因子を参照する pressure は構築時に弾く (fail-closed)."""
    try:
        ProxyPressure("bad", ("factor_nonexistent",))
    except ValueError:
        return
    raise AssertionError("unknown factor should raise ValueError")


def test_fitness_breakdown_has_all_pressure_cases() -> None:
    """make_pressure_fitness の breakdown に全 pressure の case が入る."""
    fit = make_pressure_fitness()
    report = fit(Genome3D.default())
    # 3+3+3+2+3 = 14 cases
    assert len(report.breakdown) == 14
    assert any(k.startswith("typo_robustness::") for k in report.breakdown)
    assert any(k.startswith("calibration::") for k in report.breakdown)
    assert 0.0 <= report.score <= 1.0
    assert "PROXY" in report.notes


def test_lexicase_preserves_axis_specialists() -> None:
    """ある苦手軸の因子に強い genome が、別軸に強い genome と共存する (specialist 保存)."""
    rng = np.random.default_rng(0)
    fit = make_pressure_fitness()
    # multistep に強い genome (構造化/閉ループ/自己拡張 高) vs calibration に強い genome
    # (不確実性/来歴 高)。c_factors を直接いじって対照的な specialist を作る。
    g_multistep = Genome3D.default()
    g_calib = Genome3D.default()
    fac_m = np.asarray(g_multistep.c_factors.as_array(), dtype=float)
    fac_c = np.asarray(g_calib.c_factors.as_array(), dtype=float)
    fac_m[:] = 0.1
    fac_m[[0, 2, 3], :] = 0.9  # structurize/closed_loop/self_extend
    fac_c[:] = 0.1
    fac_c[[4, 7], :] = 0.9  # uncertainty/provenance

    from llive.perf.evolutionary.thought_factor_per_layer import (
        ThoughtFactorPerLayerChromosome,
    )

    g_multistep = Genome3D(
        c_impl=g_multistep.c_impl,
        c_prompt=g_multistep.c_prompt,
        c_meta=g_multistep.c_meta,
        c_factors=ThoughtFactorPerLayerChromosome.from_array(fac_m),
    )
    g_calib = Genome3D(
        c_impl=g_calib.c_impl,
        c_prompt=g_calib.c_prompt,
        c_meta=g_calib.c_meta,
        c_factors=ThoughtFactorPerLayerChromosome.from_array(fac_c),
    )
    x = Individual(genome=g_multistep)
    y = Individual(genome=g_calib)
    x.record_fitness(fit(g_multistep))
    y.record_fitness(fit(g_calib))
    sel = MultiPressureSelector(epsilon=0.0)
    pop = Population(individuals=[x, y])
    chosen = {sel(pop, rng).individual_id for _ in range(60)}
    assert len(chosen) == 2  # 異なる軸の specialist が両方生存


# ---------------------------------------------------------------------------
# Phase 1-③ — AdaptivePercentileGate (適応難易度 = パーセンタイル動的 MC)
# ---------------------------------------------------------------------------


def test_adaptive_gate_floor_is_population_percentile() -> None:
    """update 後、floor が集団のその軸スコアの指定パーセンタイルになる."""
    gate = AdaptivePercentileGate(percentile=50.0, axes=("a",))
    inds = [_ind({"a": v}) for v in (0.0, 0.25, 0.5, 0.75, 1.0)]
    gate.update(Population(individuals=inds))
    assert gate.thresholds["a"] == pytest.approx(0.5)  # 50 分位 = median


def test_adaptive_gate_passes_after_update() -> None:
    """floor 以上の個体は pass、未満は fail、該当軸が無い個体は skip."""
    gate = AdaptivePercentileGate(percentile=50.0, axes=("a",))
    inds = [_ind({"a": v}) for v in (0.0, 0.25, 0.5, 0.75, 1.0)]
    gate.update(Population(individuals=inds))
    assert gate.passes({"a": 0.75})
    assert not gate.passes({"a": 0.25})
    assert gate.passes({"b": 0.0})  # 該当軸なし → skip


def test_adaptive_gate_empty_before_update() -> None:
    """update 前は floor 未確定 = 全通過 (selector が初手で全滅しない)."""
    gate = AdaptivePercentileGate(axes=("a",))
    assert gate.passes({"a": 0.0})
    assert gate.thresholds == {}


def test_adaptive_gate_ratchet_monotonic() -> None:
    """ratchet=True で floor は単調非減少 (集団が退化しても緩まない = 飽和回避)."""
    gate = AdaptivePercentileGate(percentile=50.0, axes=("a",), ratchet=True)
    high = [_ind({"a": v}) for v in (0.6, 0.7, 0.8, 0.9, 1.0)]
    gate.update(Population(individuals=high, generation=0))
    assert gate.thresholds["a"] == pytest.approx(0.8)
    low = [_ind({"a": v}) for v in (0.0, 0.1, 0.2, 0.3, 0.4)]
    gate.update(Population(individuals=low, generation=1))
    assert gate.thresholds["a"] == pytest.approx(0.8)  # 退化しても維持


def test_adaptive_gate_no_ratchet_follows_population() -> None:
    """ratchet=False なら毎世代分位で上書き (集団追従だが退化時に緩む)."""
    gate = AdaptivePercentileGate(percentile=50.0, axes=("a",), ratchet=False)
    high = [_ind({"a": v}) for v in (0.6, 0.7, 0.8, 0.9, 1.0)]
    gate.update(Population(individuals=high, generation=0))
    low = [_ind({"a": v}) for v in (0.0, 0.1, 0.2, 0.3, 0.4)]
    gate.update(Population(individuals=low, generation=1))
    assert gate.thresholds["a"] == pytest.approx(0.2)  # 集団追従


def test_adaptive_gate_update_once_per_generation() -> None:
    """同一世代署名で再 update しても再計算しない (1 世代 1 回)."""
    gate = AdaptivePercentileGate(percentile=50.0, axes=("a",))
    inds = [_ind({"a": v}) for v in (0.0, 0.5, 1.0)]
    pop = Population(individuals=inds, generation=0)
    gate.update(pop)
    first = gate.thresholds["a"]
    gate.update(pop)  # 同 sig → no-op
    assert gate.thresholds["a"] == first


def test_adaptive_gate_dynamic_axes_excludes_derived() -> None:
    """axes 空なら集団 breakdown から動的抽出 (factor_score 等の導出値は除外)."""
    gate = AdaptivePercentileGate(percentile=50.0)  # axes=()
    inds = [_ind({"a": v, "factor_score": 0.0}) for v in (0.0, 0.5, 1.0)]
    gate.update(Population(individuals=inds))
    assert "a" in gate.thresholds
    assert "factor_score" not in gate.thresholds  # DEFAULT_EXCLUDED_CRITERIA


def test_adaptive_gate_percentile_validation() -> None:
    with pytest.raises(ValueError):
        AdaptivePercentileGate(percentile=-1.0)
    with pytest.raises(ValueError):
        AdaptivePercentileGate(percentile=101.0)


def test_adaptive_gate_driven_by_selector() -> None:
    """MultiPressureSelector が gate.update を毎世代呼び、難易度が集団に追従する."""
    rng = np.random.default_rng(0)
    gate = AdaptivePercentileGate(percentile=50.0, axes=("a",))
    sel = MultiPressureSelector(criteria=("a",), gate=gate)
    inds = [_ind({"a": v}) for v in (0.2, 0.4, 0.6, 0.8, 1.0)]
    sel(Population(individuals=inds, generation=0), rng)
    assert gate.thresholds["a"] == pytest.approx(0.6)  # selector が update した median


def test_adaptive_gate_not_all_fail_collapse() -> None:
    """全員 floor 未満になる退化世代でも selector は gate を無視し全滅しない (SEL-4)."""
    rng = np.random.default_rng(0)
    gate = AdaptivePercentileGate(percentile=50.0, axes=("a",), ratchet=True)
    # gen0: 高い集団で floor を 0.8 に上げる
    high = [_ind({"a": v}) for v in (0.6, 0.7, 0.8, 0.9, 1.0)]
    sel = MultiPressureSelector(criteria=("a",), gate=gate)
    sel(Population(individuals=high, generation=0), rng)
    # gen1: 全員 floor(0.8) 未満 → gate 無視で例外なく選択される
    low = [_ind({"a": v}) for v in (0.1, 0.2, 0.3)]
    chosen = sel(Population(individuals=low, generation=1), rng)
    assert chosen.individual_id in {i.individual_id for i in low}
