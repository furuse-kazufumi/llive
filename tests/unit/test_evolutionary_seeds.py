# SPDX-License-Identifier: Apache-2.0
"""Per-individual sub-seed 派生 (Phase 3.5) — 単体テスト."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    FitnessReport,
    Genome,
    GenomeBounds,
    Individual,
)
from llive.perf.evolutionary.seeds import (
    call_fitness_with_seed,
    derive_sub_seed,
    fitness_accepts_seed,
)


def test_derive_sub_seed_deterministic() -> None:
    a = derive_sub_seed(42, "abc123def")
    b = derive_sub_seed(42, "abc123def")
    assert a == b
    assert 0 <= a < 2**31


def test_derive_sub_seed_changes_with_parent_seed() -> None:
    s1 = derive_sub_seed(42, "fixed_id")
    s2 = derive_sub_seed(43, "fixed_id")
    assert s1 != s2


def test_derive_sub_seed_changes_with_individual_id() -> None:
    s1 = derive_sub_seed(42, "id_a")
    s2 = derive_sub_seed(42, "id_b")
    assert s1 != s2


def test_derive_sub_seed_rejects_negative() -> None:
    with pytest.raises(ValueError):
        derive_sub_seed(-1, "x")


def test_derive_sub_seed_rejects_empty_id() -> None:
    with pytest.raises(ValueError):
        derive_sub_seed(0, "")


def test_fitness_accepts_seed_detection() -> None:
    def with_seed(g: Genome, seed: int) -> FitnessReport:
        return FitnessReport(score=float(seed))

    def without_seed(g: Genome) -> FitnessReport:
        return FitnessReport(score=0.0)

    assert fitness_accepts_seed(with_seed) is True
    assert fitness_accepts_seed(without_seed) is False


def test_call_fitness_with_seed_dispatch() -> None:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    ind = Individual.from_genome(Genome.from_values([0.5], bounds=bounds))

    def with_seed(g: Genome, seed: int) -> FitnessReport:
        # seed を score に乗せて caller がそれを観測できるようにする
        return FitnessReport(score=float(seed))

    def without_seed(g: Genome) -> FitnessReport:
        return FitnessReport(score=-1.0)

    report_with = call_fitness_with_seed(with_seed, ind, parent_seed=42)
    report_without = call_fitness_with_seed(without_seed, ind, parent_seed=42)
    expected_seed = derive_sub_seed(42, ind.individual_id)
    assert report_with.score == float(expected_seed)
    assert report_without.score == -1.0  # seed が渡されない


def test_call_fitness_with_seed_deterministic_across_runs() -> None:
    """同一 (genome, parent_seed, individual_id) なら結果が完全一致."""
    bounds = GenomeBounds(lower=(-1.0,), upper=(1.0,))
    ind = Individual.from_genome(Genome.from_values([0.5], bounds=bounds))

    def stochastic_fitness(g: Genome, seed: int) -> FitnessReport:
        rng = np.random.default_rng(seed)
        sample = rng.normal(0.0, 1.0)
        return FitnessReport(score=float(sample))

    a = call_fitness_with_seed(stochastic_fitness, ind, parent_seed=99)
    b = call_fitness_with_seed(stochastic_fitness, ind, parent_seed=99)
    assert a.score == b.score
