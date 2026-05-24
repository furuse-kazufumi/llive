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
