# SPDX-License-Identifier: Apache-2.0
"""Tests for lldarwin Stage1.5 — LineageReservoir (中立貯蔵庫) と
EvolutionLoop.on_population_bred hook.

設計: fullsense docs/research/lldarwin_stage1_results_2026_05_26.md §4.1。
絶滅した保護系統を貯蔵庫 elite で re-inject して系統絶滅を防ぐ。
"""
from __future__ import annotations

import numpy as np

from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.individual import FitnessReport, Individual
from llive.perf.evolutionary.lineage_reservoir import LineageReservoir
from llive.perf.evolutionary.population import Population

_BOUNDS = GenomeBounds(lower=(0.0,), upper=(1.0,))


def _ind(val: float, score: float, parent: str | None = None) -> Individual:
    ind = Individual(
        genome=Genome(values=(val,), bounds=_BOUNDS),
        parent_ids=(parent,) if parent else (),
    )
    ind.record_fitness(FitnessReport(score=score, breakdown={}))
    return ind


def test_register_inherits_lineage_from_parent_a() -> None:
    res = LineageReservoir()
    founder = _ind(0.1, 0.9)
    res.seed_founders({founder.individual_id: "oka"}, {"oka"})
    child = _ind(0.2, 0.5, parent=founder.individual_id)
    res.register([child])
    assert res.lineage(child) == "oka"


def test_update_keeps_best_ever_per_lineage() -> None:
    res = LineageReservoir()
    a = _ind(0.1, 0.4)
    b = _ind(0.2, 0.8)
    res.seed_founders({a.individual_id: "oka", b.individual_id: "oka"}, {"oka"})
    res.update_from_population(Population(individuals=[a, b]))
    assert res.reservoir["oka"][0] == 0.8  # best-ever score


def test_revives_extinct_protected_lineage() -> None:
    """保護系統がbredに居なければ貯蔵庫 elite で再投入される (系統絶滅回避)."""
    rng = np.random.default_rng(0)
    res = LineageReservoir()
    oka = _ind(0.9, 0.7)
    res.seed_founders({oka.individual_id: "oka"}, {"oka"})
    parent_pop = Population(individuals=[oka])  # 評価済 → 貯蔵庫に oka elite
    # bred は oka を継承しない子だけ (oka 系統は絶滅)。
    other = _ind(0.1, 0.0)  # parent 無し → (unknown) 系統
    bred = [other]
    out = res(bred, parent_pop, rng)
    lineages = {res.lineage(i) for i in out}
    assert "oka" in lineages  # oka が再投入された
    assert len(out) == len(bred)  # 個体数は不変


def test_no_reinject_when_lineage_present() -> None:
    rng = np.random.default_rng(0)
    res = LineageReservoir()
    oka = _ind(0.9, 0.7)
    res.seed_founders({oka.individual_id: "oka"}, {"oka"})
    parent_pop = Population(individuals=[oka])
    child = _ind(0.8, 0.6, parent=oka.individual_id)  # oka 系統が存続
    bred = [child]
    out = res(bred, parent_pop, rng)
    assert out is bred  # 変更なし (素通し)


def test_loop_hook_is_optional_and_backward_compatible() -> None:
    """on_population_bred=None (既定) なら従来通り動く."""
    from llive.perf.evolutionary.loop import EvolutionConfig, EvolutionLoop

    def fitness(genome) -> FitnessReport:  # noqa: ANN001
        return FitnessReport(score=float(genome.values[0]), breakdown={})

    pop = Population(
        individuals=[Individual(genome=Genome(values=(v,), bounds=_BOUNDS)) for v in (0.1, 0.5, 0.9)],
        bounds=_BOUNDS,
        seed=0,
    )
    loop = EvolutionLoop(fitness_fn=fitness)  # on_population_bred 未指定
    result = loop.run(pop, EvolutionConfig(max_generations=3, log_progress=False))
    assert result.final_population.generation == 3


def test_loop_hook_transforms_bred_population() -> None:
    """on_population_bred が bred 個体リストを変換できる."""
    from llive.perf.evolutionary.loop import EvolutionConfig, EvolutionLoop

    def fitness(genome) -> FitnessReport:  # noqa: ANN001
        return FitnessReport(score=float(genome.values[0]), breakdown={})

    seen: dict[str, int] = {}

    def hook(bred, population, rng):  # noqa: ANN001
        seen["calls"] = seen.get("calls", 0) + 1
        return bred  # 素通しだが呼ばれたことを記録

    pop = Population(
        individuals=[Individual(genome=Genome(values=(v,), bounds=_BOUNDS)) for v in (0.1, 0.5, 0.9)],
        bounds=_BOUNDS,
        seed=0,
    )
    loop = EvolutionLoop(fitness_fn=fitness, on_population_bred=hook)
    loop.run(pop, EvolutionConfig(max_generations=3, log_progress=False))
    assert seen["calls"] == 3  # 3 世代ぶん breed 後に呼ばれた
