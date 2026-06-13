# SPDX-License-Identifier: Apache-2.0
"""Tests for lldarwin — multi-pressure selection (選択圧コンポーネント).

設計: fullsense docs/vision/LLDARWIN_DESIGN.md。
複数選択圧の多目的淘汰 (ε-lexicase) + minimal-criterion gate (全滅回避) +
per-dim z-score (中央一致除外) を検証する。
"""
from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.individual import FitnessReport, Individual
from llive.perf.evolutionary.lldarwin import (
    MinimalCriterionGate,
    MultiPressureSelector,
    standardize_breakdowns,
)
from llive.perf.evolutionary.population import Population

_BOUNDS = GenomeBounds(lower=(0.0,), upper=(1.0,))


def _ind(score: float, breakdown: dict[str, float]) -> Individual:
    """breakdown を持つ個体モック (genome 値は lldarwin が使わないのでダミー)."""
    ind = Individual(genome=Genome(values=(0.5,), bounds=_BOUNDS))
    ind.record_fitness(FitnessReport(score=score, breakdown=breakdown))
    return ind


def test_gate_passes() -> None:
    gate = MinimalCriterionGate(criteria={"a": 0.5})
    assert gate.passes({"a": 0.6})
    assert not gate.passes({"a": 0.4})
    assert gate.passes({"b": 0.1})  # 該当軸が無い個体はその軸を skip


def test_lexicase_preserves_specialists() -> None:
    """ε-lexicase は単一軸 specialist を両方生存させる (argmax なら片方総取り)."""
    rng = np.random.default_rng(0)
    x = _ind(0.5, {"a": 1.0, "b": 0.0})
    y = _ind(0.5, {"a": 0.0, "b": 1.0})
    sel = MultiPressureSelector(criteria=("a", "b"), epsilon=0.0)
    pop = Population(individuals=[x, y])
    chosen = {sel(pop, rng).individual_id for _ in range(60)}
    assert len(chosen) == 2  # 両 specialist が選ばれる = 多様性保存


def test_gate_ignored_when_all_fail() -> None:
    """全個体が gate fail でも例外でなく選択される (全滅を構造的に回避)."""
    rng = np.random.default_rng(0)
    x = _ind(0.5, {"a": 0.1})
    y = _ind(0.5, {"a": 0.2})
    gate = MinimalCriterionGate(criteria={"a": 0.9})  # 全員 fail
    sel = MultiPressureSelector(criteria=("a",), gate=gate)
    chosen = sel(Population(individuals=[x, y]), rng)
    assert chosen.individual_id in {x.individual_id, y.individual_id}


def test_gate_filters_when_some_pass() -> None:
    """一部が gate を通過するなら通過個体のみが候補になる (SEL-4)."""
    rng = np.random.default_rng(0)
    x = _ind(0.5, {"a": 1.0})  # pass
    y = _ind(0.5, {"a": 0.1})  # fail
    gate = MinimalCriterionGate(criteria={"a": 0.5})
    sel = MultiPressureSelector(criteria=("a",), gate=gate)
    chosen = {sel(Population(individuals=[x, y]), rng).individual_id for _ in range(20)}
    assert chosen == {x.individual_id}


def test_standardize_zscore() -> None:
    x = _ind(0.5, {"a": 1.0})
    y = _ind(0.5, {"a": 3.0})
    z = standardize_breakdowns([x, y], ("a",))
    assert z[x.individual_id]["a"] == pytest.approx(-1.0)
    assert z[y.individual_id]["a"] == pytest.approx(1.0)


def test_standardize_zero_variance_is_neutral() -> None:
    """分散ほぼ 0 の軸 (全個体同値=無特徴) は z=0 で優位を得ない (SEL-1)."""
    x = _ind(0.5, {"a": 2.0})
    y = _ind(0.5, {"a": 2.0})
    z = standardize_breakdowns([x, y], ("a",))
    assert z[x.individual_id]["a"] == 0.0
    assert z[y.individual_id]["a"] == 0.0


def test_infer_criteria_dynamic() -> None:
    """criteria 未指定なら breakdown の数値キーを動的抽出して選択する."""
    rng = np.random.default_rng(0)
    x = _ind(0.5, {"a": 1.0, "b": 0.5})
    y = _ind(0.5, {"a": 0.5, "b": 1.0})
    sel = MultiPressureSelector()  # criteria=()
    chosen = sel(Population(individuals=[x, y]), rng)
    assert chosen.individual_id in {x.individual_id, y.individual_id}


def test_empty_breakdown_random_fallback() -> None:
    """pressure が一つも無くても random fallback で選ぶ (全滅回避の最終手段)."""
    rng = np.random.default_rng(0)
    x = _ind(0.5, {})
    y = _ind(0.5, {})
    sel = MultiPressureSelector()
    chosen = sel(Population(individuals=[x, y]), rng)
    assert chosen.individual_id in {x.individual_id, y.individual_id}


def test_excludes_argmax_and_categorical_criteria() -> None:
    """factor_score (argmax) と nearest_persona_idx (カテゴリ index) は自動抽出時に
    淘汰圧から外す (Stage1, SEL-2 = best=1.0 飽和の真因の除去)."""
    rng = np.random.default_rng(0)
    # y は nearest_persona_idx / factor_score だけ高い。これらが除外されないと
    # lexicase が y を不当に優遇してしまう。実 pressure (archetype::a) は x が上。
    x = _ind(0.5, {"archetype::a": 1.0, "factor_score": 0.5, "nearest_persona_idx": 0.0})
    y = _ind(0.5, {"archetype::a": 0.0, "factor_score": 1.0, "nearest_persona_idx": 7.0})
    sel = MultiPressureSelector()  # criteria=() → 自動抽出 + 既定除外
    chosen = {sel(Population(individuals=[x, y]), rng).individual_id for _ in range(40)}
    # 除外が効けば pressure 軸 archetype::a だけが残り、specialist x が常に勝つ。
    assert chosen == {x.individual_id}


def test_novelty_pressure_preserves_outlier() -> None:
    """use_novelty=True で集団から外れた個体 (高 novelty) が specialist として保存される.

    全個体の archetype 軸が同値 (= fitness 飽和) でも、genome が外れ値の個体は
    novelty case で生き残れる (空きニッチへの探索圧, poc_evolution_env の核機構)."""
    rng = np.random.default_rng(0)
    # archetype 軸は全員同値 (飽和) → novelty が無ければ全員同点で淘汰圧ゼロ。
    near = [
        Individual(genome=Genome(values=(0.50,), bounds=_BOUNDS)) for _ in range(5)
    ]
    outlier = Individual(genome=Genome(values=(0.99,), bounds=_BOUNDS))
    for ind in [*near, outlier]:
        ind.record_fitness(FitnessReport(score=0.5, breakdown={"archetype::a": 1.0}))
    pop = Population(individuals=[*near, outlier])
    sel = MultiPressureSelector(use_novelty=True)
    # 1 世代目は archive 空で novelty=neutral だが、archive 蓄積後は外れ値が高 novelty。
    sel(pop, rng)  # gen 0: archive へ集団を蓄積
    pop2 = Population(individuals=[*near, outlier], generation=1)
    chosen = {sel(pop2, rng).individual_id for _ in range(60)}
    assert outlier.individual_id in chosen  # 外れ値が novelty 圧で生存
    # novelty が breakdown に書かれている (監査可能性)。
    assert "novelty" in outlier.fitness.breakdown


def test_factor_subspace_novelty_blends_into_breakdown() -> None:
    """factor_subspace_weight>0 + factor_extractor で factor 部分空間 novelty が
    全体 novelty とブレンドされ breakdown['novelty'] に反映される (QD-3, PoC#6)."""
    rng = np.random.default_rng(0)

    def _fac(genome: object) -> np.ndarray:  # factor 部分空間 = genome.values (テスト用)
        return np.asarray(genome.values, dtype=float)

    near = [
        Individual(genome=Genome(values=(0.50,), bounds=_BOUNDS)) for _ in range(5)
    ]
    outlier = Individual(genome=Genome(values=(0.99,), bounds=_BOUNDS))
    for ind in [*near, outlier]:
        ind.record_fitness(FitnessReport(score=0.5, breakdown={"archetype::a": 1.0}))
    sel = MultiPressureSelector(
        use_novelty=True, factor_subspace_weight=0.5, factor_extractor=_fac
    )
    pop = Population(individuals=[*near, outlier])
    sel(pop, rng)  # gen0: archive 蓄積 (全体 + factor 部分空間)
    pop2 = Population(individuals=[*near, outlier], generation=1)
    chosen = {sel(pop2, rng).individual_id for _ in range(60)}
    assert outlier.individual_id in chosen  # factor 外れ値も novelty 圧で生存
    assert "novelty" in outlier.fitness.breakdown


def test_factor_subspace_weight_out_of_range_rejected() -> None:
    with pytest.raises(ValueError):
        MultiPressureSelector(factor_subspace_weight=1.5)
    with pytest.raises(ValueError):
        MultiPressureSelector(factor_subspace_weight=-0.1)
