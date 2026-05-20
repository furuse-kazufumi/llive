# SPDX-License-Identifier: Apache-2.0
"""llive v0.B Scheduler (並列) — picklable / sequential / asyncio の最小 test."""

from __future__ import annotations

import asyncio

import pytest

from llive.perf.evolutionary import (
    AsyncioScheduler,
    EvolutionConfig,
    EvolutionLoop,
    FitnessReport,
    GaussianMutation,
    Genome,
    GenomeBounds,
    Individual,
    MultiprocessingScheduler,
    Population,
    TournamentSelection,
    UniformCrossover,
    serial_scheduler,
    sphere_fitness,
)


def test_serial_scheduler_equivalent_to_direct_call() -> None:
    bounds = GenomeBounds(lower=(-1.0, -1.0), upper=(1.0, 1.0))
    pop = Population.random(bounds=bounds, size=4, seed=0)
    reports = serial_scheduler(sphere_fitness, pop.individuals)
    assert len(reports) == 4
    for ind, rep in zip(pop.individuals, reports, strict=True):
        direct = sphere_fitness(ind.genome)
        assert rep.score == direct.score


@pytest.mark.timeout(30)
def test_multiprocessing_scheduler_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """MultiprocessingScheduler が走ること + 結果が serial と一致することを確認.

    Windows での spawn overhead と pytest との相性を考え, n_workers=2 で軽量実行.
    """
    bounds = GenomeBounds(lower=(-1.0, -1.0), upper=(1.0, 1.0))
    pop = Population.random(bounds=bounds, size=4, seed=0)
    scheduler = MultiprocessingScheduler(n_workers=2)
    reports = scheduler(sphere_fitness, pop.individuals)
    assert len(reports) == 4
    serial_reports = serial_scheduler(sphere_fitness, pop.individuals)
    for r, s in zip(reports, serial_reports, strict=True):
        assert pytest.approx(r.score) == s.score


# ---------------------------------------------------------------------------
# Asyncio
# ---------------------------------------------------------------------------


async def _async_sphere(genome: Genome) -> FitnessReport:
    await asyncio.sleep(0)  # yield
    return sphere_fitness(genome)


def test_asyncio_scheduler_runs() -> None:
    bounds = GenomeBounds(lower=(-1.0,), upper=(1.0,))
    pop = Population.random(bounds=bounds, size=8, seed=0)
    scheduler = AsyncioScheduler(async_fitness=_async_sphere, concurrency_limit=4)
    reports = scheduler(sphere_fitness, pop.individuals)  # sync fitness は不使用
    assert len(reports) == 8


# ---------------------------------------------------------------------------
# Loop と MultiprocessingScheduler の連携
# ---------------------------------------------------------------------------


@pytest.mark.timeout(60)
def test_evolution_loop_with_multiprocessing() -> None:
    bounds = GenomeBounds(lower=(-3.0, -3.0), upper=(3.0, 3.0))
    pop = Population.random(bounds=bounds, size=8, seed=0)
    loop = EvolutionLoop(
        fitness_fn=sphere_fitness,
        selection=TournamentSelection(k=3),
        crossover=UniformCrossover(p=0.5),
        mutation=GaussianMutation(sigma=0.2, p=0.2),
        scheduler=MultiprocessingScheduler(n_workers=2),
    )
    config = EvolutionConfig(max_generations=4, patience=10, log_progress=False)
    result = loop.run(pop, config)
    assert result.best_score > result.stats_history[0].best_score
