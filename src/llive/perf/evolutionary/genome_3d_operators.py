# SPDX-License-Identifier: Apache-2.0
"""Genome3D-aware operators for EvolutionLoop injection (G2).

EvolutionLoop takes injected ``crossover`` / ``mutation`` callables. The flat
operators in :mod:`crossover` / :mod:`mutation` assume a flat ``Genome``
(``.as_array()`` + ``Genome.from_values``). These wrap the Genome3D-native
genetic ops (``intra_layer_crossover`` / ``cross_layer_crossover`` /
``Genome3D.sample_neighborhood``) in the *same* callable shape, so a Genome3D run
plugs into the **unchanged** EvolutionLoop breed path::

    loop = EvolutionLoop(
        fitness_fn=...,
        crossover=Genome3DCrossover(mode="intra"),
        mutation=Genome3DMutation(step_size=0.1),
    )

The loop's ``_breed_next_generation`` calls ``self.crossover(a, b, rng)`` then
``self.mutation(child, rng)`` polymorphically (its type aliases are already
``Callable[[object, ...], object]``), so no loop change is needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from llive.perf.evolutionary.genome_3d import (
    Genome3D,
    cross_layer_crossover,
    intra_layer_crossover,
)


@dataclass(frozen=True)
class Genome3DCrossover:
    """Crossover over Genome3D. ``mode`` picks the layer-mixing strategy.

    - ``"intra"`` — :func:`intra_layer_crossover`: each of the 4 layers chosen
      50/50 from either parent (2^4 equal-probability combinations).
    - ``"cross"`` — :func:`cross_layer_crossover`: impl always from A, prompt
      always from B, meta 50/50, factors mixed per-factor (cross-substrate
      exchange).
    """

    mode: Literal["intra", "cross"] = "intra"

    def __post_init__(self) -> None:
        if self.mode not in ("intra", "cross"):
            raise ValueError(f"mode must be 'intra' or 'cross', got {self.mode!r}")

    def __call__(
        self, parent_a: Genome3D, parent_b: Genome3D, rng: np.random.Generator
    ) -> Genome3D:
        if self.mode == "cross":
            return cross_layer_crossover(parent_a, parent_b, rng)
        return intra_layer_crossover(parent_a, parent_b, rng)


@dataclass(frozen=True)
class Genome3DMutation:
    """Mutation over Genome3D via per-chromosome neighbourhood sampling.

    Wraps :meth:`Genome3D.sample_neighborhood` (a Gaussian step on each of the 4
    chromosomes at the shared ``step_size``) into the ``(genome, rng)`` mutation
    callable shape EvolutionLoop expects.
    """

    step_size: float = 0.1

    def __post_init__(self) -> None:
        if self.step_size < 0:
            raise ValueError("step_size must be >= 0")

    def __call__(self, genome: Genome3D, rng: np.random.Generator) -> Genome3D:
        return genome.sample_neighborhood(rng, step_size=self.step_size)


__all__ = ["Genome3DCrossover", "Genome3DMutation"]
