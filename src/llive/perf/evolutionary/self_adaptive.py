# SPDX-License-Identifier: Apache-2.0
"""Self-Adaptive Evolution Strategy mutation (llive v0.D Phase 1, SR-01).

Promptbreeder (DeepMind, arXiv:2309.16797) の "mutation 自体を進化させる"
発想を **数値 genome 版** に翻案. Schwefel 1981 / Bäck & Schwefel 1993 の
self-adaptive evolution strategy (σSA-ES) を実装.

Genome 構造:

``genome.values = (x_0, x_1, ..., x_{n-1}, σ_0, σ_1, ..., σ_{n-1})``

- 前半 ``n_object_dims`` は通常の object variables (思考因子 weight 等).
- 後半 ``n_object_dims`` は各 object var に対応する mutation σ_i.

世代ごとに:

1. σ_i' = σ_i * exp(τ' * N_global + τ * N_i)         (log-normal σ update)
2. x_i' = x_i + σ_i' * N(0, 1) * width_i            (object var update)

両者とも bounds で clip. σ の bounds は ``Genome.bounds`` の後半 n に
そのまま入れる (例: lower=1e-4, upper=2.0).

学習率の default は Schwefel 推奨:

- ``τ' = 1 / sqrt(2 * sqrt(n))``  (global)
- ``τ  = 1 / sqrt(2 * n)``        (per-dim)

参照:

- Schwefel, H.-P. (1981). *Numerical Optimization of Computer Models*.
- Bäck, T. & Schwefel, H.-P. (1993). *An Overview of Evolutionary
  Algorithms for Parameter Optimization*. Evolutionary Computation 1(1).
- Fernando, C. et al. (2023). [Promptbreeder](https://arxiv.org/abs/2309.16797).
- llive `docs/requirements_v0.D_self_referential_and_llm_operators.md` SR-01.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from llive.perf.evolutionary.genome import Genome, GenomeBounds


@dataclass(frozen=True)
class SelfAdaptiveGaussianMutation:
    """Schwefel-style σSA-ES mutation.

    Genome の前半 ``n_object_dims`` を object variables, 後半 ``n_object_dims``
    を σ として扱う. **Genome 全体は 2 * n_object_dims 次元**.

    Attributes
    ----------
    n_object_dims : int
        前半の object 変数の数. genome.n_dims は 2 * n_object_dims でなければ
        ならない.
    tau_global : float | None
        global 学習率 τ'. None なら Schwefel 推奨 ``1/sqrt(2*sqrt(n))``.
    tau_local : float | None
        per-dim 学習率 τ. None なら Schwefel 推奨 ``1/sqrt(2*n)``.
    p : float
        各 dim を mutate する確率. self-adaptive ES の標準は p=1.0 (全 dim 更新).
        部分更新したい場合は p<1.0.
    relative_to_width : bool
        True (default) なら object var の noise を width_i * σ_i * N(0,1) で
        スケール. False なら σ_i * N(0,1) のみ. llive `GaussianMutation` と
        互換性を取るため default True.
    """

    n_object_dims: int
    tau_global: float | None = None
    tau_local: float | None = None
    p: float = 1.0
    relative_to_width: bool = True

    def __post_init__(self) -> None:
        if self.n_object_dims <= 0:
            raise ValueError("n_object_dims must be > 0")
        if not (0.0 < self.p <= 1.0):
            raise ValueError("p must be in (0, 1]")

    # ---------- public API ----------------------------------------------

    def __call__(self, genome: Genome, rng: np.random.Generator) -> Genome:
        n = self.n_object_dims
        if genome.n_dims != 2 * n:
            raise ValueError(
                f"genome.n_dims ({genome.n_dims}) must equal 2 * n_object_dims "
                f"({2 * n}). Pack object vars and σ together."
            )
        values = genome.as_array()
        x = values[:n].copy()
        sigma = values[n:].copy()

        tau_g = (
            self.tau_global
            if self.tau_global is not None
            else 1.0 / math.sqrt(2.0 * math.sqrt(n))
        )
        tau_l = (
            self.tau_local if self.tau_local is not None else 1.0 / math.sqrt(2.0 * n)
        )

        # 1. log-normal σ update — global noise + per-dim noise
        n_global = float(rng.normal(0.0, 1.0))
        n_local = rng.normal(0.0, 1.0, size=n)
        sigma_new = sigma * np.exp(tau_g * n_global + tau_l * n_local)

        # σ の bounds で clip (numerical stability)
        sigma_lower = np.asarray(genome.bounds.lower[n:], dtype=np.float64)
        sigma_upper = np.asarray(genome.bounds.upper[n:], dtype=np.float64)
        sigma_new = np.clip(sigma_new, sigma_lower, sigma_upper)

        # 2. object variable update — N(0, σ_i) per dim
        if self.relative_to_width:
            obj_lower = np.asarray(genome.bounds.lower[:n], dtype=np.float64)
            obj_upper = np.asarray(genome.bounds.upper[:n], dtype=np.float64)
            width = obj_upper - obj_lower
            scale = sigma_new * width
        else:
            scale = sigma_new
        noise = rng.normal(0.0, 1.0, size=n) * scale

        # mask: per-dim mutation probability
        if self.p < 1.0:
            mask = rng.random(size=n) < self.p
            x_new = np.where(mask, x + noise, x)
        else:
            x_new = x + noise

        new_values = np.concatenate([x_new, sigma_new])
        return Genome.from_values(new_values, bounds=genome.bounds, labels=genome.labels)


# ---------------------------------------------------------------------------
# helper: bounds と genome の packing/unpacking
# ---------------------------------------------------------------------------


def pack_self_adaptive_bounds(
    object_bounds: GenomeBounds,
    *,
    sigma_lower: float = 1e-4,
    sigma_upper: float = 2.0,
    sigma_labels_prefix: str = "sigma_",
    object_labels: tuple[str, ...] = (),
) -> tuple[GenomeBounds, tuple[str, ...]]:
    """object bounds から σ-augmented bounds を作る.

    Parameters
    ----------
    object_bounds : GenomeBounds
        前半 n dim の bounds.
    sigma_lower, sigma_upper : float
        各 σ_i の bounds (全 σ 共通). σ は relative 0..1 想定なので
        default は 1e-4 〜 2.0.
    sigma_labels_prefix : str
        σ 次元の label prefix. default "sigma_".
    object_labels : tuple[str, ...]
        object 次元の label. 空なら "dim_0" 等を assign.

    Returns
    -------
    GenomeBounds, tuple[str, ...]
        2n dim の bounds と labels.
    """
    n = object_bounds.n_dims
    lower = list(object_bounds.lower) + [sigma_lower] * n
    upper = list(object_bounds.upper) + [sigma_upper] * n
    if object_labels:
        if len(object_labels) != n:
            raise ValueError("object_labels length must equal object_bounds.n_dims")
        obj_lbl = list(object_labels)
    else:
        obj_lbl = [f"dim_{i}" for i in range(n)]
    sigma_lbl = [f"{sigma_labels_prefix}{lbl}" for lbl in obj_lbl]
    return GenomeBounds(lower=tuple(lower), upper=tuple(upper)), tuple(obj_lbl + sigma_lbl)


def initial_sigma_values(
    n_object_dims: int,
    *,
    sigma_init: float = 0.1,
) -> np.ndarray:
    """σ 初期値の (n,) ndarray を返す. default 0.1."""
    if sigma_init <= 0:
        raise ValueError("sigma_init must be > 0")
    return np.full(n_object_dims, sigma_init, dtype=np.float64)


__all__ = [
    "SelfAdaptiveGaussianMutation",
    "initial_sigma_values",
    "pack_self_adaptive_bounds",
]
