# SPDX-License-Identifier: Apache-2.0
"""Surprise gate (MEM-04) — embedding nearest-neighbor cosine distance."""

from __future__ import annotations

import numpy as np


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return matrix / norms


class SurpriseGate:
    """Compute `1 - max(cosine_sim(new, existing))` and gate writes by a θ threshold.

    Phase 1: simple deterministic cosine. Phase 2 (MEM-07) で Bayesian (mean+variance) 化。
    """

    def __init__(self, theta: float = 0.3) -> None:
        if not (0.0 <= theta <= 1.0):
            raise ValueError("theta must be in [0, 1]")
        self.theta = float(theta)

    def compute_surprise(
        self,
        new_embedding: np.ndarray,
        memory_embeddings: np.ndarray | None,
    ) -> float:
        """Return surprise ∈ [0, 1]. If no memory yet, returns 1.0 (always write)."""
        if memory_embeddings is None or memory_embeddings.size == 0:
            return 1.0
        new = _l2_normalize(np.atleast_2d(new_embedding))
        mem = _l2_normalize(np.atleast_2d(memory_embeddings))
        sims = (new @ mem.T).flatten()  # (M,)
        max_sim = float(sims.max()) if sims.size else -1.0
        # cosine sim in [-1, 1] → distance in [0, 2]; clamp to [0, 1]
        return float(max(0.0, min(1.0, 1.0 - max_sim)))

    def should_write(self, surprise: float, theta: float | None = None) -> bool:
        theta_use = self.theta if theta is None else float(theta)
        return surprise >= theta_use
