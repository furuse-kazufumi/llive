# SPDX-License-Identifier: Apache-2.0
"""Mutation — 突然変異 (llive v0.B EV-05).

2 種: Gaussian (N(0, σ) を加算) / Reset (uniform reset).
すべて bounds で clip ([[bounded modification §E2]] 整合).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from llive.perf.evolutionary.genome import Genome


@dataclass(frozen=True)
class GaussianMutation:
    """N(0, sigma) を確率 p で各 dim に加算.

    sigma は bounds 幅に対する **相対値** (例: 0.1 → 各 dim 幅の 10%).
    """

    sigma: float = 0.1
    p: float = 0.05

    def __post_init__(self) -> None:
        if self.sigma <= 0:
            raise ValueError("sigma must be > 0")
        if not (0.0 <= self.p <= 1.0):
            raise ValueError("p must be in [0, 1]")

    def __call__(self, genome: Genome, rng: np.random.Generator) -> Genome:
        values = genome.as_array()
        lower = np.asarray(genome.bounds.lower, dtype=np.float64)
        upper = np.asarray(genome.bounds.upper, dtype=np.float64)
        width = upper - lower
        mask = rng.random(size=values.shape) < self.p
        noise = rng.normal(loc=0.0, scale=self.sigma, size=values.shape) * width
        mutated = np.where(mask, values + noise, values)
        return Genome.from_values(mutated, bounds=genome.bounds, labels=genome.labels)


@dataclass(frozen=True)
class ResetMutation:
    """確率 p で 1 つの dim を uniform reset (局所最適脱出用)."""

    p: float = 0.01

    def __post_init__(self) -> None:
        if not (0.0 <= self.p <= 1.0):
            raise ValueError("p must be in [0, 1]")

    def __call__(self, genome: Genome, rng: np.random.Generator) -> Genome:
        values = genome.as_array()
        lower = np.asarray(genome.bounds.lower, dtype=np.float64)
        upper = np.asarray(genome.bounds.upper, dtype=np.float64)
        for i in range(values.shape[0]):
            if rng.random() < self.p:
                values[i] = rng.uniform(lower[i], upper[i])
        return Genome.from_values(values, bounds=genome.bounds, labels=genome.labels)


@dataclass(frozen=True)
class ChainedMutation:
    """複数 mutation を順に適用するヘルパ (gaussian → reset の併用に便利)."""

    mutations: tuple

    def __call__(self, genome: Genome, rng: np.random.Generator) -> Genome:
        current = genome
        for m in self.mutations:
            current = m(current, rng)
        return current


__all__ = ["ChainedMutation", "GaussianMutation", "ResetMutation"]
