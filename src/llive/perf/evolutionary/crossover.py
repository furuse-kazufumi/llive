# SPDX-License-Identifier: Apache-2.0
"""Crossover — 親 2 体から子 genome を作る (llive v0.B EV-04).

2 種: Uniform (各 dim 独立に親から sample) / Blend (線形補間 + α 拡張).
すべて bounds で clip して返す.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from llive.perf.evolutionary.genome import Genome


@dataclass(frozen=True)
class UniformCrossover:
    """各 dim を独立に親 A / B からサンプリング (p の確率で A から)."""

    p: float = 0.5

    def __post_init__(self) -> None:
        if not (0.0 <= self.p <= 1.0):
            raise ValueError("p must be in [0, 1]")

    def __call__(
        self, parent_a: Genome, parent_b: Genome, rng: np.random.Generator
    ) -> Genome:
        if parent_a.bounds != parent_b.bounds:
            raise ValueError("parents have different bounds")
        a = parent_a.as_array()
        b = parent_b.as_array()
        mask = rng.random(size=a.shape) < self.p
        child = np.where(mask, a, b)
        return Genome.from_values(child, bounds=parent_a.bounds, labels=parent_a.labels)


@dataclass(frozen=True)
class BlendCrossover:
    """親値の線形補間 + α 拡張 (BLX-α). 連続パラメータ用 GA 標準."""

    alpha: float = 0.5

    def __post_init__(self) -> None:
        if self.alpha < 0:
            raise ValueError("alpha must be >= 0")

    def __call__(
        self, parent_a: Genome, parent_b: Genome, rng: np.random.Generator
    ) -> Genome:
        if parent_a.bounds != parent_b.bounds:
            raise ValueError("parents have different bounds")
        a = parent_a.as_array()
        b = parent_b.as_array()
        lo = np.minimum(a, b)
        hi = np.maximum(a, b)
        diff = hi - lo
        sample_lo = lo - self.alpha * diff
        sample_hi = hi + self.alpha * diff
        child = rng.uniform(low=sample_lo, high=sample_hi)
        return Genome.from_values(child, bounds=parent_a.bounds, labels=parent_a.labels)


__all__ = ["BlendCrossover", "UniformCrossover"]
