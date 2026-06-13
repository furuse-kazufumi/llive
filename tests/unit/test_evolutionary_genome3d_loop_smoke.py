# SPDX-License-Identifier: Apache-2.0
"""EvolutionLoop × Genome3D smoke (G8).

Proves a Genome3D population runs through the *unchanged* EvolutionLoop breed
path (with injected Genome3D operators) and that a snapshot written mid-run
resumes back into a Genome3D population (the G7 frozen point, end-to-end).
"""

from __future__ import annotations

import numpy as np

from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.genome_3d_operators import (
    Genome3DCrossover,
    Genome3DMutation,
)
from llive.perf.evolutionary.individual import FitnessReport, Individual
from llive.perf.evolutionary.loop import EvolutionConfig, EvolutionLoop
from llive.perf.evolutionary.population import Population


def _target_fitness(genome: Genome3D) -> FitnessReport:
    """Higher is better: closeness of the factor layer to a 0.5 target."""
    flat = genome.c_factors.as_flat()
    err = float(np.mean((flat - 0.5) ** 2))
    return FitnessReport(score=-err, breakdown={"factor_mse": err})


def _genome3d_population(size: int, seed: int) -> Population:
    rng = np.random.default_rng(seed)
    individuals = [
        Individual.from_genome(Genome3D.default().sample_neighborhood(rng, step_size=0.3))
        for _ in range(size)
    ]
    return Population(individuals=individuals, bounds=None, seed=seed, generation_seeds=[seed])


def _loop() -> EvolutionLoop:
    return EvolutionLoop(
        fitness_fn=_target_fitness,
        crossover=Genome3DCrossover(mode="intra"),
        mutation=Genome3DMutation(step_size=0.1),
    )


def test_genome3d_evolution_loop_runs(tmp_path) -> None:
    pop = _genome3d_population(size=8, seed=1)
    config = EvolutionConfig(
        max_generations=5,
        patience=99,          # don't early-stop on stagnation in a smoke
        diversity_floor=0.0,  # don't early-stop on diversity
        out_dir=tmp_path,
        log_progress=False,
    )
    result = _loop().run(pop, config)

    assert len(result.stats_history) >= 1
    assert isinstance(result.best_individual.genome, Genome3D)
    assert np.isfinite(result.best_score)
    # snapshots were written for resume
    assert any(tmp_path.glob("snapshot_gen_*.json"))


def test_genome3d_evolution_resume_round_trips(tmp_path) -> None:
    # First run: write snapshots.
    pop = _genome3d_population(size=6, seed=2)
    first = EvolutionConfig(
        max_generations=3, patience=99, diversity_floor=0.0,
        out_dir=tmp_path, log_progress=False,
    )
    _loop().run(pop, first)

    # Second run: resume from the snapshot dir into a fresh population shell.
    fresh = _genome3d_population(size=6, seed=999)
    resumed_cfg = EvolutionConfig(
        max_generations=1, patience=99, diversity_floor=0.0,
        resume_from=tmp_path, log_progress=False,
    )
    result = _loop().run(fresh, resumed_cfg)

    # Resumed individuals are Genome3D (the genome_type tag round-tripped).
    assert all(isinstance(ind.genome, Genome3D) for ind in result.final_population.individuals)
    # Resume picked up the prior generation count (>= the 3 gens advanced before).
    assert result.final_population.generation >= 3


def test_genome3d_cross_mode_also_runs(tmp_path) -> None:
    pop = _genome3d_population(size=6, seed=4)
    loop = EvolutionLoop(
        fitness_fn=_target_fitness,
        crossover=Genome3DCrossover(mode="cross"),
        mutation=Genome3DMutation(step_size=0.1),
    )
    result = loop.run(
        pop,
        EvolutionConfig(max_generations=3, patience=99, diversity_floor=0.0, log_progress=False),
    )
    assert isinstance(result.best_individual.genome, Genome3D)
    assert len(result.stats_history) >= 1
