# SPDX-License-Identifier: Apache-2.0
"""Genome3D persona founders + proxy fitness adapter (G4 + G3).

Proves the multi-layer persona evolution is *ready to run*: founders carry the
persona's factor affinity in the c_factors layer, the proxy fitness scores a
Genome3D, and the pieces compose into a real EvolutionLoop run — while the flat
proxy fitness is numerically unchanged.
"""

from __future__ import annotations

import numpy as np

from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.genome_3d_operators import (
    Genome3DCrossover,
    Genome3DMutation,
)
from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.loop import EvolutionConfig, EvolutionLoop
from llive.perf.evolutionary.persona import (
    RESEARCH_METHODOLOGY_PERSONA_IDS,
    get_persona,
)
from llive.perf.evolutionary.persona_evolution import (
    _proxy_fitness,
    build_founder_genome,
    build_founder_genome_3d,
    build_founder_individuals_3d,
    is_founder,
    run_persona_evolution,
)
from llive.perf.evolutionary.population import Population


# --- G4: Genome3D founders --------------------------------------------------


def test_founder_genome_3d_carries_affinity_in_factor_layer() -> None:
    pid = RESEARCH_METHODOLOGY_PERSONA_IDS[0]
    persona = get_persona(pid)
    g = build_founder_genome_3d(pid)  # uniform broadcast
    assert isinstance(g, Genome3D)
    # uniform broadcast: every layer == affinity, so the per-layer mean == affinity
    mean_over_layers = g.c_factors.as_array().mean(axis=1)
    np.testing.assert_allclose(mean_over_layers, np.asarray(persona.factor_affinity), atol=1e-9)


def test_founder_individuals_3d_are_tagged_founders() -> None:
    ids = RESEARCH_METHODOLOGY_PERSONA_IDS[:3]
    founders = build_founder_individuals_3d(ids)
    assert len(founders) == 3
    assert all(is_founder(ind) for ind in founders)
    assert all(isinstance(ind.genome, Genome3D) for ind in founders)
    assert founders[0].individual_id == f"founder:{ids[0]}"


# --- G3: proxy fitness adapter ----------------------------------------------


def test_proxy_fitness_scores_genome3d() -> None:
    g = build_founder_genome_3d(RESEARCH_METHODOLOGY_PERSONA_IDS[0])
    report = _proxy_fitness(g)
    assert np.isfinite(report.score)
    assert "PROXY" in report.notes
    assert set(report.breakdown) >= {"balance", "provenance", "factor_mean", "factor_std"}


def test_proxy_fitness_flat_unchanged() -> None:
    # flat path must be numerically identical to the pre-adapter behaviour.
    g = build_founder_genome(RESEARCH_METHODOLOGY_PERSONA_IDS[0])
    arr = g.as_array()
    factors = arr[:10]
    mean, std = float(factors.mean()), float(factors.std())
    expect_balance = max(0.0, min(1.0, mean * (1.0 - std)))
    report = _proxy_fitness(g)
    assert report.breakdown["balance"] == expect_balance


# --- G3+G4+G2: composes into a real Genome3D persona run --------------------


def test_genome3d_persona_evolution_composes(tmp_path) -> None:
    ids = RESEARCH_METHODOLOGY_PERSONA_IDS
    founders = build_founder_individuals_3d(ids)
    rng = np.random.default_rng(0)
    padding = [
        Individual.from_genome(Genome3D.default().sample_neighborhood(rng, step_size=0.3))
        for _ in range(max(0, 10 - len(founders)))
    ]
    pop = Population(
        individuals=founders + padding,
        bounds=None,
        seed=0,
        generation_seeds=[0],
    )
    loop = EvolutionLoop(
        fitness_fn=_proxy_fitness,
        crossover=Genome3DCrossover(mode="intra"),
        mutation=Genome3DMutation(step_size=0.1),
    )
    result = loop.run(
        pop,
        EvolutionConfig(max_generations=5, patience=99, diversity_floor=0.0, log_progress=False),
    )
    assert np.isfinite(result.best_score)
    assert isinstance(result.best_individual.genome, Genome3D)
    assert len(result.stats_history) >= 1


# --- turnkey driver: run_persona_evolution(genome3d=True) -------------------


def test_turnkey_genome3d_run_produces_genome3d(tmp_path) -> None:
    res = run_persona_evolution(
        population_size=10,
        generations=5,
        seed=0,
        out_dir=tmp_path,
        genome3d=True,
        patience=99,
        diversity_floor=0.0,
    )
    assert isinstance(res.evolution_result.best_individual.genome, Genome3D)
    assert res.used_proxy_fitness is True
    assert res.winners_path is not None and res.winners_path.exists()
    assert res.lineage_path is not None and res.lineage_path.exists()


def test_turnkey_flat_mode_unchanged_by_default(tmp_path) -> None:
    # genome3d defaults to False → flat Genome population (regression).
    from llive.perf.evolutionary.genome import Genome

    res = run_persona_evolution(population_size=8, generations=3, seed=0)
    assert isinstance(res.evolution_result.best_individual.genome, Genome)


def test_turnkey_genome3d_resume(tmp_path) -> None:
    common = dict(population_size=8, seed=1, genome3d=True, patience=99, diversity_floor=0.0)
    run_persona_evolution(
        generations=3, out_dir=tmp_path, persist_generation_log=True,
        checkpoint_every=1, **common,
    )
    res = run_persona_evolution(generations=1, resume_from=tmp_path, **common)
    final = res.evolution_result.final_population
    assert all(isinstance(ind.genome, Genome3D) for ind in final.individuals)
    assert final.generation >= 3


def test_collapse_guard_stops_identical_population() -> None:
    # No-op operators model "evolution produces no change": the population stays a
    # single identical genome (distinct==1) every generation. With patience and
    # diversity_floor both disabled, only the hard collapse guard can stop the run.
    from llive.perf.evolutionary.loop import EvolutionConfig, EvolutionLoop

    clone = Genome3D.default()
    pop = Population(
        individuals=[Individual.from_genome(clone) for _ in range(6)],
        bounds=None,
        seed=0,
    )

    def _no_op_crossover(a, b, rng):  # noqa: ANN001 - returns a parent unchanged
        return a

    def _no_op_mutation(g, rng):  # noqa: ANN001 - returns the genome unchanged
        return g

    loop = EvolutionLoop(
        fitness_fn=_proxy_fitness,
        crossover=_no_op_crossover,
        mutation=_no_op_mutation,
    )
    result = loop.run(
        pop,
        EvolutionConfig(
            max_generations=1000, patience=10**9, diversity_floor=0.0,
            max_stall_generations=5, log_progress=False,
        ),
    )
    assert "population_collapsed" in result.stopped_reason
    assert result.final_population.generation < 1000  # stopped early, not the cap


def test_collapse_guard_off_by_default_in_loop() -> None:
    # EvolutionConfig.max_stall_generations defaults to None → guard disabled
    # (backward compatible; existing EvolutionLoop tests unaffected).
    from llive.perf.evolutionary.loop import EvolutionConfig

    assert EvolutionConfig().max_stall_generations is None
