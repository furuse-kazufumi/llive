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
