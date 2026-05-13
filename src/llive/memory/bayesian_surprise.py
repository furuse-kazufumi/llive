"""Bayesian surprise gate (MEM-07) — Welford online mean+variance.

`BayesianSurpriseGate` extends the Phase 1 `SurpriseGate` by treating
each surprise measurement as a sample from a running univariate Gaussian
distribution (Welford's algorithm, single pass, numerically stable).
Threshold ``theta`` is **dynamic**: ``theta_t = mu + k * sigma`` of the
running stats, where ``k`` is configurable (default 1.0).

For per-concept stats (LLW-01 ConceptPage `surprise_stats`), instantiate
the gate with `concept_id` and persist via `to_dict / from_dict`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from llive.memory.surprise import SurpriseGate, _l2_normalize


@dataclass
class WelfordStats:
    """Online mean + variance using Welford's algorithm."""

    n: int = 0
    mean: float = 0.0
    m2: float = 0.0  # sum of squared deviations from the mean

    def update(self, value: float) -> None:
        self.n += 1
        delta = value - self.mean
        self.mean += delta / self.n
        delta2 = value - self.mean
        self.m2 += delta * delta2

    @property
    def variance(self) -> float:
        if self.n < 2:
            return 0.0
        return self.m2 / (self.n - 1)

    @property
    def stddev(self) -> float:
        return math.sqrt(self.variance)

    def to_dict(self) -> dict[str, float | int]:
        return {"n": self.n, "mean": self.mean, "m2": self.m2}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WelfordStats:
        return cls(n=int(data.get("n", 0)), mean=float(data.get("mean", 0.0)), m2=float(data.get("m2", 0.0)))


class BayesianSurpriseGate:
    """Dynamic-threshold surprise gate built on running Welford stats.

    Parameters
    ----------
    k : float
        Threshold multiplier. Higher = fewer writes pass the gate.
    min_samples : int
        Until the gate has seen this many samples, falls back to a constant
        threshold so the gate is well-behaved on cold start.
    cold_start_theta : float
        Constant threshold used while ``n < min_samples``.
    """

    def __init__(
        self,
        k: float = 1.0,
        min_samples: int = 8,
        cold_start_theta: float = 0.3,
    ) -> None:
        self.k = float(k)
        self.min_samples = int(min_samples)
        self.cold_start_theta = float(cold_start_theta)
        self.stats = WelfordStats()

    # -- statistics --------------------------------------------------------

    def update(self, surprise: float) -> None:
        self.stats.update(float(surprise))

    @property
    def threshold(self) -> float:
        if self.stats.n < self.min_samples:
            return self.cold_start_theta
        return self.stats.mean + self.k * self.stats.stddev

    # -- surprise computation (shared with Phase 1) -----------------------

    def compute_surprise(
        self,
        new_embedding: np.ndarray,
        memory_embeddings: np.ndarray | None,
    ) -> float:
        """Compute raw surprise (`1 - max cosine`), identical to Phase 1."""
        if memory_embeddings is None or memory_embeddings.size == 0:
            return 1.0
        new = _l2_normalize(np.atleast_2d(new_embedding))
        mem = _l2_normalize(np.atleast_2d(memory_embeddings))
        sims = (new @ mem.T).flatten()
        max_sim = float(sims.max()) if sims.size else -1.0
        return float(max(0.0, min(1.0, 1.0 - max_sim)))

    def should_write(self, surprise: float, *, update_stats: bool = True) -> bool:
        """Decide whether to write, optionally updating stats first.

        Note: when ``update_stats`` is True, the gate sees this sample and
        the threshold may shift; this is the correct online behaviour but
        users running batch decisions may want ``update_stats=False`` to
        compare a whole batch against a fixed threshold.
        """
        theta = self.threshold
        passed = float(surprise) >= theta
        if update_stats:
            self.update(surprise)
        return passed

    # -- persistence ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "k": self.k,
            "min_samples": self.min_samples,
            "cold_start_theta": self.cold_start_theta,
            "stats": self.stats.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BayesianSurpriseGate:
        gate = cls(
            k=float(data.get("k", 1.0)),
            min_samples=int(data.get("min_samples", 8)),
            cold_start_theta=float(data.get("cold_start_theta", 0.3)),
        )
        gate.stats = WelfordStats.from_dict(data.get("stats", {}))
        return gate


__all__ = [
    "BayesianSurpriseGate",
    "SurpriseGate",  # re-export for convenience
    "WelfordStats",
]
