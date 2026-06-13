# SPDX-License-Identifier: Apache-2.0
"""Genome3D × evolution infra integration — frozen-point tests (G1/G7).

Before running a Genome3D evolution we must guarantee that Individual/Population
serialize *and resume* a Genome3D correctly, and that flat behaviour is
untouched (backward compatibility). These tests lock that contract.
"""

from __future__ import annotations

import numpy as np

from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.genome_3d import Genome3D, genome_flat_vector
from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.population import Population


def _flat_genome() -> Genome:
    bounds = GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 1.0))
    return Genome.from_values([0.3, 0.7], bounds, labels=("a", "b"))


def _g3d(rng: np.random.Generator) -> Genome3D:
    return Genome3D.default().sample_neighborhood(rng, step_size=0.2)


# --- genome_type tag (G7) ---------------------------------------------------


def test_individual_to_dict_tags_flat_genome() -> None:
    ind = Individual.from_genome(_flat_genome())
    assert ind.to_dict()["genome_type"] == "Genome"


def test_individual_to_dict_tags_genome3d() -> None:
    ind = Individual.from_genome(Genome3D.default())
    assert ind.to_dict()["genome_type"] == "Genome3D"


# --- round-trip (G7) --------------------------------------------------------


def test_individual_round_trip_flat() -> None:
    ind = Individual.from_genome(_flat_genome())
    back = Individual.from_dict(ind.to_dict())
    assert isinstance(back.genome, Genome)
    assert back.genome.as_array().tolist() == ind.genome.as_array().tolist()


def test_individual_round_trip_genome3d() -> None:
    rng = np.random.default_rng(7)
    g = _g3d(rng)
    ind = Individual.from_genome(g, parent_ids=("p1",), birth_generation=3)
    back = Individual.from_dict(ind.to_dict())
    assert isinstance(back.genome, Genome3D)
    assert back.genome == g  # frozen dataclass equality
    assert back.parent_ids == ("p1",)
    assert back.birth_generation == 3


def test_from_dict_without_tag_defaults_to_flat() -> None:
    # Snapshots written before the Genome3D split carry no genome_type.
    payload = Individual.from_genome(_flat_genome()).to_dict()
    del payload["genome_type"]
    back = Individual.from_dict(payload)
    assert isinstance(back.genome, Genome)


# --- Population with Genome3D + bounds=None (G1/G7) --------------------------


def test_population_genome3d_round_trip_with_none_bounds() -> None:
    rng = np.random.default_rng(11)
    pop = Population(
        individuals=[Individual.from_genome(_g3d(rng)) for _ in range(4)],
        bounds=None,
        seed=11,
        generation_seeds=[11],
    )
    data = pop.to_dict()
    assert data["bounds"] is None
    back = Population.from_dict(data)
    assert back.bounds is None
    assert all(isinstance(ind.genome, Genome3D) for ind in back.individuals)
    assert back.individuals[0].genome == pop.individuals[0].genome


def test_flat_population_round_trip_still_carries_bounds() -> None:
    bounds = GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 1.0))
    pop = Population.random(bounds, size=3, seed=5, labels=("a", "b"))
    back = Population.from_dict(pop.to_dict())
    assert back.bounds is not None
    assert back.bounds.n_dims == 2
    assert all(isinstance(ind.genome, Genome) for ind in back.individuals)


# --- flat-view helper + diversity (G1) --------------------------------------


def test_genome_flat_vector_dispatch() -> None:
    assert genome_flat_vector(_flat_genome()).shape == (2,)
    v3d = genome_flat_vector(Genome3D.default())
    # c_factors default = 10 factors × 4 layers = 40-dim flat view
    assert v3d.shape == (40,)


def test_population_diversity_works_for_genome3d() -> None:
    rng = np.random.default_rng(3)
    pop = Population(
        individuals=[Individual.from_genome(_g3d(rng)) for _ in range(5)],
        bounds=None,
        seed=3,
    )
    stats = pop.compute_stats()
    # distinct neighbourhood-sampled genomes → positive pairwise L2 diversity
    assert stats.diversity_l2 > 0.0
