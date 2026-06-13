# SPDX-License-Identifier: Apache-2.0
"""EvolutionLoop on_generation_end hook の動作 test."""

from __future__ import annotations

from pathlib import Path

from llive.perf.evolutionary import (
    EvolutionConfig,
    EvolutionLoop,
    GenomeBounds,
    Population,
    sphere_fitness,
    write_winners_jsonl,
    load_winners_jsonl,
)


def test_hook_called_per_generation() -> None:
    """on_generation_end が世代ごとに呼ばれる."""
    calls: list[int] = []

    def hook(pop, stats):
        calls.append(stats.generation)

    pop = Population.random(GenomeBounds(lower=(-1.0,), upper=(1.0,)), size=4, seed=0)
    loop = EvolutionLoop(fitness_fn=sphere_fitness, on_generation_end=hook)
    config = EvolutionConfig(max_generations=3, patience=10, diversity_floor=0.0, log_progress=False)
    loop.run(pop, config)
    # gen 0,1,2,3 で呼ばれる
    assert calls == [0, 1, 2, 3]


def test_hook_integrates_with_lineage(tmp_path: Path) -> None:
    """winners.jsonl auto-append が動く."""
    jsonl = tmp_path / "winners.jsonl"

    def hook(pop, stats):
        write_winners_jsonl(jsonl, pop, top_n=2)

    pop = Population.random(GenomeBounds(lower=(-2.0, -2.0), upper=(2.0, 2.0)), size=10, seed=42)
    loop = EvolutionLoop(fitness_fn=sphere_fitness, on_generation_end=hook)
    config = EvolutionConfig(max_generations=3, patience=10, diversity_floor=0.0, log_progress=False)
    loop.run(pop, config)
    winners = load_winners_jsonl(jsonl)
    # 4 世代 × top_n=2 = 8 件
    assert len(winners) == 8
    # 世代番号 0..3 が含まれる
    gens = {w.generation for w in winners}
    assert gens == {0, 1, 2, 3}


def test_hook_failure_does_not_break_run() -> None:
    """hook が例外を投げても run は止まらない."""
    def bad_hook(pop, stats):
        raise RuntimeError("boom")

    pop = Population.random(GenomeBounds(lower=(-1.0,), upper=(1.0,)), size=4, seed=0)
    loop = EvolutionLoop(fitness_fn=sphere_fitness, on_generation_end=bad_hook)
    config = EvolutionConfig(max_generations=2, patience=10, diversity_floor=0.0, log_progress=False)
    result = loop.run(pop, config)
    # hook が落ちても run は完走する
    assert result.final_population.generation == 2
    assert len(result.stats_history) == 3  # gen 0, 1, 2


def test_hook_none_is_default_noop() -> None:
    pop = Population.random(GenomeBounds(lower=(-1.0,), upper=(1.0,)), size=4, seed=0)
    loop = EvolutionLoop(fitness_fn=sphere_fitness)
    assert loop.on_generation_end is None
    # 通常通り走る
    config = EvolutionConfig(max_generations=2, patience=10, diversity_floor=0.0, log_progress=False)
    result = loop.run(pop, config)
    assert result.final_population.generation == 2
