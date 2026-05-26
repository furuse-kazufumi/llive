# SPDX-License-Identifier: Apache-2.0
"""Tests for lldarwin v2 — 確定方策 S1「選択核」の合成プリセット (Phase 1).

設計: fullsense docs/research/lldarwin_v2_poc_marathon_2026_05_26.md §「✅ 決定した方策」S1。
overnight マラソン確定構成 (ε-lexicase + novelty(z-score) + minimal-criterion + 中立貯蔵庫
フック) を **既存部品の合成** で表現したことを検証する (新規アルゴリズムは作らない)。

検証観点:
* 合成器が生成でき、各部品 (lexicase / novelty / gate) が正しく配線されること
* 既定 (default 選択) が不変 = 後方互換 (本構成は完全 opt-in)
* proxy で数世代 smoke が回ること (proxy pressure fitness)
"""
from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.individual import FitnessReport, Individual
from llive.perf.evolutionary.lldarwin import (
    MinimalCriterionGate,
    MultiPressureSelector,
)
from llive.perf.evolutionary.lldarwin_v2 import (
    DEFAULT_MINIMAL_CRITERION,
    LLDarwinV2Config,
    build_lldarwin_v2_selector,
)
from llive.perf.evolutionary.persona import RESEARCH_METHODOLOGY_PERSONA_IDS
from llive.perf.evolutionary.persona_evolution import run_persona_evolution
from llive.perf.evolutionary.population import Population
from llive.perf.evolutionary.pressures import make_pressure_fitness

_BOUNDS = GenomeBounds(lower=(0.0,), upper=(1.0,))


def _ind(score: float, breakdown: dict[str, float], value: float = 0.5) -> Individual:
    ind = Individual(genome=Genome(values=(value,), bounds=_BOUNDS))
    ind.record_fitness(FitnessReport(score=score, breakdown=breakdown))
    return ind


# ---------------------------------------------------------------------------
# config / synthesis
# ---------------------------------------------------------------------------


def test_default_config_is_confirmed_s1() -> None:
    """既定 config が確定 S1 (novelty on / lexicase eps0.01 / 中立貯蔵庫 on) を表す."""
    cfg = LLDarwinV2Config()
    assert cfg.use_novelty is True  # STD-1: novelty(z-score) は S1 の核
    assert cfg.epsilon == 0.01
    assert cfg.novelty_k == 5
    assert cfg.lineage_reservoir is True  # 系統多様性は中立貯蔵庫で別途確保
    assert cfg.map_elites_archive is True  # QD-1/QD-2 成果アーカイブ
    # factor-subspace QD (QD-3) は Phase 1 では未実装の placeholder = 既定 off (honest)。
    assert cfg.factor_subspace_qd is False
    assert cfg.minimal_criterion == DEFAULT_MINIMAL_CRITERION


def test_build_selector_is_multipressure_with_novelty() -> None:
    """合成器は MultiPressureSelector を返し、各部品が配線されている."""
    sel = build_lldarwin_v2_selector()
    assert isinstance(sel, MultiPressureSelector)
    assert sel.use_novelty is True  # novelty 配線
    assert sel.epsilon == 0.01  # ε-lexicase 配線
    assert sel.gate is None  # 既定は gate なし (軸未指定)


def test_build_selector_wires_minimal_criterion_gate() -> None:
    """minimal_criterion_axes を指定すると gate (MinimalCriterionGate) が配線される."""
    cfg = LLDarwinV2Config(
        minimal_criterion_axes=("typo_robustness::factor_consistency",),
        minimal_criterion=0.3,
    )
    sel = build_lldarwin_v2_selector(cfg)
    assert isinstance(sel.gate, MinimalCriterionGate)
    assert sel.gate.criteria == {"typo_robustness::factor_consistency": 0.3}


def test_build_gate_none_when_no_axes() -> None:
    """軸未指定なら gate=None (過剰拘束を避ける既定)."""
    assert LLDarwinV2Config().build_gate() is None


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        LLDarwinV2Config(epsilon=-0.1)
    with pytest.raises(ValueError):
        LLDarwinV2Config(novelty_k=0)
    with pytest.raises(ValueError):
        LLDarwinV2Config(reinject_interval=0)


def test_criteria_override_passed_through() -> None:
    cfg = LLDarwinV2Config(criteria=("a", "b"))
    sel = build_lldarwin_v2_selector(cfg)
    assert sel.criteria == ("a", "b")


# ---------------------------------------------------------------------------
# behavior: lexicase + novelty wiring actually selects
# ---------------------------------------------------------------------------


def test_selector_preserves_specialists() -> None:
    """合成器の ε-lexicase が単一軸 specialist を両方生存させる (SEL-3)."""
    rng = np.random.default_rng(0)
    cfg = LLDarwinV2Config(criteria=("a", "b"), use_novelty=False, epsilon=0.0)
    sel = build_lldarwin_v2_selector(cfg)
    x = _ind(0.5, {"a": 1.0, "b": 0.0})
    y = _ind(0.5, {"a": 0.0, "b": 1.0})
    pop = Population(individuals=[x, y])
    chosen = {sel(pop, rng).individual_id for _ in range(60)}
    assert len(chosen) == 2  # 両 specialist 保存 = 多様性


def test_selector_novelty_writes_breakdown() -> None:
    """use_novelty 配線で novelty が breakdown に書かれ、外れ値が保存される (STD-1)."""
    rng = np.random.default_rng(0)
    sel = build_lldarwin_v2_selector(LLDarwinV2Config(use_novelty=True))
    near = [Individual(genome=Genome(values=(0.50,), bounds=_BOUNDS)) for _ in range(5)]
    outlier = Individual(genome=Genome(values=(0.99,), bounds=_BOUNDS))
    for ind in [*near, outlier]:
        ind.record_fitness(FitnessReport(score=0.5, breakdown={"archetype::a": 1.0}))
    pop = Population(individuals=[*near, outlier])
    sel(pop, rng)  # gen0: archive 蓄積
    pop2 = Population(individuals=[*near, outlier], generation=1)
    chosen = {sel(pop2, rng).individual_id for _ in range(60)}
    assert outlier.individual_id in chosen
    assert "novelty" in outlier.fitness.breakdown


# ---------------------------------------------------------------------------
# backward compatibility: default behavior unchanged
# ---------------------------------------------------------------------------


def test_default_run_unchanged_without_v2() -> None:
    """selection=None (既定) の run は v2 構成を一切通らず従来挙動 (後方互換)."""
    res = run_persona_evolution(
        RESEARCH_METHODOLOGY_PERSONA_IDS,
        population_size=8,
        generations=3,
        seed=0,
        selection=None,  # 既定 Tournament
    )
    assert res.evolution_result.final_population.generation >= 1
    assert res.used_proxy_fitness is True


def test_default_run_is_deterministic() -> None:
    """v2 を導入しても既定経路は決定論的 (同 seed で best_score 再現)."""
    kw = dict(population_size=8, generations=3, seed=7, selection=None)
    a = run_persona_evolution(RESEARCH_METHODOLOGY_PERSONA_IDS, **kw)
    b = run_persona_evolution(RESEARCH_METHODOLOGY_PERSONA_IDS, **kw)
    assert a.evolution_result.best_score == b.evolution_result.best_score


# ---------------------------------------------------------------------------
# smoke: v2 selector drives a few generations on proxy pressure fitness
# ---------------------------------------------------------------------------


def test_v2_selector_proxy_smoke() -> None:
    """v2 合成器を proxy pressure fitness で数世代 smoke (機構が壊れず回る).

    measurement purity: pressure-proxy は実 LLM を呼ばない決定論評価 (Stage2 mechanism
    feasibility)。ここでは「合成構成で世代交代が完走し全滅しない」ことだけを確認する。
    """
    sel = build_lldarwin_v2_selector()
    res = run_persona_evolution(
        RESEARCH_METHODOLOGY_PERSONA_IDS,
        fitness_fn=make_pressure_fitness(),
        is_proxy=True,
        population_size=10,
        generations=4,
        seed=0,
        selection=sel,
    )
    pop = res.evolution_result.final_population
    assert pop.generation >= 2  # 数世代回った
    assert pop.size == 10  # 全滅していない (集団サイズ維持)
    assert res.used_proxy_fitness is True


def test_v2_selector_with_reservoir_smoke() -> None:
    """v2 合成器 + 中立貯蔵庫 hook を併用しても数世代回る (S1 系統多様性フック)."""
    sel = build_lldarwin_v2_selector()
    res = run_persona_evolution(
        RESEARCH_METHODOLOGY_PERSONA_IDS,
        fitness_fn=make_pressure_fitness(),
        is_proxy=True,
        population_size=10,
        generations=4,
        seed=1,
        selection=sel,
        lineage_reservoir=True,  # 確定 S1: 中立貯蔵庫を既定 on
        reinject_interval=1,
    )
    pop = res.evolution_result.final_population
    assert pop.generation >= 2
    assert pop.size == 10
