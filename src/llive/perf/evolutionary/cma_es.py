# SPDX-License-Identifier: Apache-2.0
"""CMA-ES (Covariance Matrix Adaptation Evolution Strategy) adapter — llive v0.B skeleton.

Hansen & Ostermeier (2001) / Hansen (2016) "The CMA Evolution Strategy: A Tutorial"
(arXiv:1604.00772) の **自前実装 skeleton**. numpy のみ依存. pycma / scipy 不使用.

# 位置づけ (taxonomy 優先度 #1)

[[project_ai_algorithms_taxonomy]] §進化計算 第 1 優先. 既存の
:class:`ThoughtFactorPerLayerChromosome` (10 × 4 = **40-dim continuous** genome,
[[project_llive_thought_factor_per_layer]] commit ``f8ff4bf``) の
``sample_neighborhood`` は単純な等方 Gaussian 摂動だが, **CMA-ES は共分散行列
で因子間 / 層間相関を学習**して局所構造に追従する.

# 設計判断

* **EvolutionLoop と疎結合** — 直接 import しない. `ask()` / `tell()` /
  `sample_neighborhood()` の duck-typing で他コンポーネントと連携.
* **`(μ/μ_w, λ)` weighted recombination** (default values per Hansen 2016 §6).
  * λ = 4 + floor(3 ln dim) (population size)
  * μ = floor(λ / 2) (parent size)
  * weights = ln(μ+0.5) - ln(rank), 正規化して Σ=1
* **step-size control (CSA)** — cumulative step-size adaptation の path 累積版.
  簡易版: ``sigma *= exp((cs/damps) * (||p_sigma|| / E||N(0,I)|| - 1))``.
* **rank-μ update** — covariance matrix の rank-μ 更新 (Hansen 2016 eq. 47).
  rank-one (evolution path) も付与.
* **state_dict** で全状態を保存/復元. checkpoint 互換.
* **sample_neighborhood(x, n)** で既存 chromosome の mutation operator 互換
  interface も提供. 入力 x の周りに sigma を局所 scale として候補を生成.

# 既存実装との対比

* :class:`GaussianMutation` (``mutation.py``) — isotropic Gaussian. step-size 固定.
* :class:`SelfAdaptiveGaussianMutation` (``self_adaptive.py``) — 個体ごとの
  sigma を進化. 因子間相関なし.
* :class:`ThoughtFactorPerLayerChromosome.sample_neighborhood` — isotropic.
* **本 module** = 集団レベルで共分散行列を学習 (相関含む). 既存より表現力大.

Status: skeleton — 完全な BIPOP / restart / boundary handling は未実装.
最小限の (μ_w, λ) CMA-ES + state_dict + sample_neighborhood adapter のみ着地.

References:
* Hansen, N. (2016). The CMA Evolution Strategy: A Tutorial. arXiv:1604.00772.
* Hansen, N. & Ostermeier, A. (2001). Completely Derandomized Self-Adaptation
  in Evolution Strategies. Evolutionary Computation, 9(2), 159-195.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = ["CMAESAdapter", "CMAESState"]


@dataclass
class CMAESState:
    """CMA-ES の checkpoint 可能な内部状態 (state_dict round-trip 用)."""

    dim: int
    sigma: float
    sigma0: float
    population_size: int
    mu: int
    mean: np.ndarray  # (dim,)
    C: np.ndarray  # (dim, dim) covariance matrix
    p_sigma: np.ndarray  # (dim,) evolution path for sigma
    p_c: np.ndarray  # (dim,) evolution path for C
    weights: np.ndarray  # (mu,) recombination weights
    mu_eff: float
    cs: float  # step-size cumulation
    cc: float  # covariance cumulation
    c1: float  # rank-one learning rate
    cmu: float  # rank-mu learning rate
    damps: float  # damping for sigma
    generation: int
    chi_n: float  # E[||N(0,I)||]


class CMAESAdapter:
    """CMA-ES (Covariance Matrix Adaptation Evolution Strategy) skeleton adapter.

    Hansen (2016) "The CMA Evolution Strategy: A Tutorial" (arXiv:1604.00772) の
    自前実装. numpy のみ依存. EvolutionLoop と疎結合 (duck-typing 経由).

    Args:
        dim: search space dimension. ``Genome3D.c_factors`` を flatten すると
            10 × 4 = 40 dim. 任意 dim 対応.
        sigma0: initial step-size (mutation strength). 探索空間スケールに合わせる.
        population_size: λ (offspring per generation). None なら Hansen default
            ``4 + floor(3 ln dim)``.
        mean0: initial mean vector. None なら zeros(dim).
        rng: numpy RNG. None なら ``default_rng()``.
        bounds: optional (lo, hi) tuple — ask() 出力を clip する.

    Raises:
        ValueError: dim < 1 / sigma0 < 0 / population_size < 2.
    """

    def __init__(
        self,
        dim: int,
        sigma0: float = 0.3,
        population_size: int | None = None,
        mean0: np.ndarray | None = None,
        rng: np.random.Generator | None = None,
        bounds: tuple[float, float] | None = None,
    ) -> None:
        if dim < 1:
            raise ValueError(f"dim must be >= 1, got {dim}")
        if sigma0 < 0:
            raise ValueError(f"sigma0 must be >= 0, got {sigma0}")

        # population size (Hansen 2016 default)
        if population_size is None:
            population_size = 4 + int(math.floor(3 * math.log(max(dim, 1))))
        if population_size < 2:
            raise ValueError(
                f"population_size must be >= 2, got {population_size}"
            )

        self._dim = int(dim)
        self._sigma = float(sigma0)
        self._sigma0 = float(sigma0)
        self._lambda = int(population_size)
        self._mu = self._lambda // 2  # parent size
        self._rng = rng if rng is not None else np.random.default_rng()
        self._bounds = bounds

        # mean vector
        if mean0 is None:
            self._mean = np.zeros(self._dim, dtype=np.float64)
        else:
            mean_arr = np.asarray(mean0, dtype=np.float64).reshape(-1)
            if mean_arr.shape[0] != self._dim:
                raise ValueError(
                    f"mean0 shape {mean_arr.shape} mismatches dim {self._dim}"
                )
            self._mean = mean_arr.copy()

        # recombination weights — Hansen 2016 §6, eq. (49)
        raw_w = np.log(self._mu + 0.5) - np.log(np.arange(1, self._mu + 1))
        self._weights = raw_w / raw_w.sum()
        self._mu_eff = 1.0 / float(np.sum(self._weights**2))

        # strategy parameters (Hansen 2016 §6)
        n = float(self._dim)
        mu_eff = self._mu_eff
        self._cs = (mu_eff + 2.0) / (n + mu_eff + 5.0)
        self._cc = (4.0 + mu_eff / n) / (n + 4.0 + 2.0 * mu_eff / n)
        self._c1 = 2.0 / ((n + 1.3) ** 2 + mu_eff)
        self._cmu = min(
            1.0 - self._c1,
            2.0 * (mu_eff - 2.0 + 1.0 / mu_eff) / ((n + 2.0) ** 2 + mu_eff),
        )
        # damps: damping for sigma update
        self._damps = (
            1.0
            + 2.0 * max(0.0, math.sqrt((mu_eff - 1.0) / (n + 1.0)) - 1.0)
            + self._cs
        )

        # evolution paths
        self._p_sigma = np.zeros(self._dim, dtype=np.float64)
        self._p_c = np.zeros(self._dim, dtype=np.float64)

        # covariance matrix (identity initially)
        self._C = np.eye(self._dim, dtype=np.float64)

        # expected norm E[||N(0, I)||] (Hansen 2016 eq. 30)
        self._chi_n = math.sqrt(n) * (
            1.0 - 1.0 / (4.0 * n) + 1.0 / (21.0 * n * n)
        )

        self._generation = 0
        self._last_candidates: np.ndarray | None = None

    # ----- properties --------------------------------------------------------

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def sigma(self) -> float:
        return self._sigma

    @property
    def sigma0(self) -> float:
        return self._sigma0

    @property
    def population_size(self) -> int:
        return self._lambda

    @property
    def mu(self) -> int:
        return self._mu

    @property
    def mean(self) -> np.ndarray:
        return self._mean.copy()

    @property
    def C(self) -> np.ndarray:  # noqa: N802 — math notation
        return self._C.copy()

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def mu_eff(self) -> float:
        return self._mu_eff

    @property
    def weights(self) -> np.ndarray:
        return self._weights.copy()

    # ----- core API ----------------------------------------------------------

    def ask(self) -> np.ndarray:
        """Sample λ candidates from the current multivariate Gaussian.

        Returns:
            np.ndarray of shape ``(population_size, dim)``. Each row is
            ``mean + sigma * B @ diag(D) @ z`` for ``z ~ N(0, I)``, where
            ``C = B @ diag(D**2) @ B.T``. If sigma == 0, all rows equal mean.
            If bounds set, output is clipped.
        """
        if self._sigma == 0.0:
            # degenerate — all candidates collapse to the mean
            cands = np.tile(self._mean, (self._lambda, 1))
        else:
            # eigendecomposition of C (symmetric → eigh is stable)
            # ensure symmetry for numerical safety
            C_sym = 0.5 * (self._C + self._C.T)
            try:
                eigvals, B = np.linalg.eigh(C_sym)
            except np.linalg.LinAlgError:
                # fallback: identity
                eigvals = np.ones(self._dim)
                B = np.eye(self._dim)
            # guard against tiny negative eigenvalues from FP noise
            eigvals = np.maximum(eigvals, 1e-20)
            D = np.sqrt(eigvals)

            z = self._rng.standard_normal((self._lambda, self._dim))
            # samples = mean + sigma * (B @ diag(D) @ z.T).T
            cands = self._mean[None, :] + self._sigma * (z * D) @ B.T

        if self._bounds is not None:
            lo, hi = self._bounds
            cands = np.clip(cands, lo, hi)

        self._last_candidates = cands.copy()
        return cands

    def tell(
        self,
        candidates: np.ndarray,
        fitnesses: np.ndarray,
        *,
        minimize: bool = True,
    ) -> None:
        """Update mean, covariance, and sigma using ranked fitness.

        Args:
            candidates: shape ``(population_size, dim)``. ``ask()`` 出力をそのまま
                渡すことを想定 (修正済みでも OK).
            fitnesses: shape ``(population_size,)``. 低いほど良い (minimize=True)
                / 高いほど良い (minimize=False).
            minimize: ``True`` なら fitness 昇順, ``False`` なら降順を採用.

        Raises:
            ValueError: shape mismatch.
        """
        cands = np.asarray(candidates, dtype=np.float64)
        fits = np.asarray(fitnesses, dtype=np.float64).reshape(-1)

        if cands.shape != (self._lambda, self._dim):
            raise ValueError(
                f"candidates shape {cands.shape} != "
                f"({self._lambda}, {self._dim})"
            )
        if fits.shape[0] != self._lambda:
            raise ValueError(
                f"fitnesses length {fits.shape[0]} != {self._lambda}"
            )

        # rank by fitness — best μ
        order = np.argsort(fits) if minimize else np.argsort(-fits)
        selected = cands[order[: self._mu]]  # (mu, dim)

        # weighted recombination — new mean
        old_mean = self._mean.copy()
        new_mean = self._weights @ selected  # (dim,)

        # update evolution paths
        # need C^{-1/2} for p_sigma; if sigma == 0, skip path updates
        if self._sigma == 0.0:
            self._mean = new_mean
            self._generation += 1
            return

        # eigendecomposition (re-use logic from ask)
        C_sym = 0.5 * (self._C + self._C.T)
        try:
            eigvals, B = np.linalg.eigh(C_sym)
        except np.linalg.LinAlgError:
            eigvals = np.ones(self._dim)
            B = np.eye(self._dim)
        eigvals = np.maximum(eigvals, 1e-20)
        D = np.sqrt(eigvals)
        # C^{-1/2} = B @ diag(1/D) @ B.T
        invsqrtC = (B / D) @ B.T

        mean_diff = (new_mean - old_mean) / self._sigma  # (dim,)

        # p_sigma update (Hansen 2016 eq. 42)
        cs = self._cs
        self._p_sigma = (1.0 - cs) * self._p_sigma + math.sqrt(
            cs * (2.0 - cs) * self._mu_eff
        ) * (invsqrtC @ mean_diff)

        # heaviside h_sigma for stalling protection
        norm_p_sigma = float(np.linalg.norm(self._p_sigma))
        h_sigma_threshold = (
            1.4 + 2.0 / (self._dim + 1.0)
        ) * self._chi_n
        # denominator includes time-correction
        denom = math.sqrt(
            1.0 - (1.0 - cs) ** (2 * (self._generation + 1))
        )
        h_sigma = (
            1.0
            if norm_p_sigma / max(denom, 1e-20) < h_sigma_threshold
            else 0.0
        )

        # p_c update (Hansen 2016 eq. 45)
        cc = self._cc
        self._p_c = (1.0 - cc) * self._p_c + h_sigma * math.sqrt(
            cc * (2.0 - cc) * self._mu_eff
        ) * mean_diff

        # covariance update (rank-one + rank-μ, Hansen 2016 eq. 47)
        c1 = self._c1
        cmu = self._cmu
        # rank-one: (1-h_sigma) correction for the stalling case
        rank_one = np.outer(self._p_c, self._p_c)
        # rank-μ: Σ w_i (x_i - old_mean)/sigma (x_i - old_mean)^T / sigma
        diff_scaled = (selected - old_mean) / self._sigma  # (mu, dim)
        rank_mu = (self._weights[:, None] * diff_scaled).T @ diff_scaled
        # apply
        self._C = (
            (1.0 - c1 - cmu) * self._C
            + c1 * (rank_one + (1.0 - h_sigma) * cc * (2.0 - cc) * self._C)
            + cmu * rank_mu
        )

        # sigma update (Hansen 2016 eq. 44)
        self._sigma = self._sigma * math.exp(
            (cs / self._damps)
            * (norm_p_sigma / self._chi_n - 1.0)
        )
        # safety clamp — keep sigma in a sensible range
        self._sigma = max(self._sigma, 1e-30)

        # commit mean
        self._mean = new_mean
        self._generation += 1

    # ----- ThoughtFactorPerLayerChromosome-compat interface ------------------

    def sample_neighborhood(
        self, x: np.ndarray, n: int = 1
    ) -> np.ndarray:
        """Mutation operator interface for chromosome-style genomes.

        Sample ``n`` candidates from ``N(x, sigma^2 * C)``. Matches the
        spirit of :meth:`ThoughtFactorPerLayerChromosome.sample_neighborhood`
        (single-step Gaussian neighborhood) but with the **learned covariance
        matrix** as scale, so directions with high historical fitness gradient
        are explored more aggressively.

        Args:
            x: anchor point. shape ``(dim,)`` or flattened to it.
            n: number of neighbors. ``n >= 1``.

        Returns:
            ``n == 1`` → 1D ndarray shape ``(dim,)``.
            ``n > 1``  → 2D ndarray shape ``(n, dim)``.

        Note:
            Shape contract differs from
            :meth:`ThoughtFactorPerLayerChromosome.sample_neighborhood` which
            returns a new chromosome instance. Here we return raw ndarray —
            the caller is responsible for ``from_array`` wrapping (the
            chromosome class already exposes ``from_array``). This keeps
            CMAESAdapter independent of any concrete genome class.
        """
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        x_arr = np.asarray(x, dtype=np.float64).reshape(-1)
        if x_arr.shape[0] != self._dim:
            raise ValueError(
                f"x shape {x_arr.shape} mismatches dim {self._dim}"
            )

        if self._sigma == 0.0:
            out = np.tile(x_arr, (n, 1))
        else:
            C_sym = 0.5 * (self._C + self._C.T)
            try:
                eigvals, B = np.linalg.eigh(C_sym)
            except np.linalg.LinAlgError:
                eigvals = np.ones(self._dim)
                B = np.eye(self._dim)
            eigvals = np.maximum(eigvals, 1e-20)
            D = np.sqrt(eigvals)
            z = self._rng.standard_normal((n, self._dim))
            out = x_arr[None, :] + self._sigma * (z * D) @ B.T

        if self._bounds is not None:
            lo, hi = self._bounds
            out = np.clip(out, lo, hi)

        if n == 1:
            return out[0]
        return out

    # ----- checkpoint --------------------------------------------------------

    def state_dict(self) -> dict[str, Any]:
        """Snapshot full state. ``load_state_dict`` で完全復元可能.

        ndarray は ``.tolist()`` で json-safe にする (容量は dim x dim だが
        skeleton は dim ~ 40 なので問題なし).
        """
        return {
            "dim": self._dim,
            "sigma": self._sigma,
            "sigma0": self._sigma0,
            "population_size": self._lambda,
            "mu": self._mu,
            "mean": self._mean.tolist(),
            "C": self._C.tolist(),
            "p_sigma": self._p_sigma.tolist(),
            "p_c": self._p_c.tolist(),
            "weights": self._weights.tolist(),
            "mu_eff": self._mu_eff,
            "cs": self._cs,
            "cc": self._cc,
            "c1": self._c1,
            "cmu": self._cmu,
            "damps": self._damps,
            "generation": self._generation,
            "chi_n": self._chi_n,
            "bounds": list(self._bounds) if self._bounds is not None else None,
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Restore from ``state_dict()`` output. In-place.

        Raises:
            ValueError: dim mismatch with current instance.
        """
        if int(state["dim"]) != self._dim:
            raise ValueError(
                f"state dim {state['dim']} != self.dim {self._dim}"
            )
        self._sigma = float(state["sigma"])
        self._sigma0 = float(state["sigma0"])
        self._lambda = int(state["population_size"])
        self._mu = int(state["mu"])
        self._mean = np.asarray(state["mean"], dtype=np.float64)
        self._C = np.asarray(state["C"], dtype=np.float64)
        self._p_sigma = np.asarray(state["p_sigma"], dtype=np.float64)
        self._p_c = np.asarray(state["p_c"], dtype=np.float64)
        self._weights = np.asarray(state["weights"], dtype=np.float64)
        self._mu_eff = float(state["mu_eff"])
        self._cs = float(state["cs"])
        self._cc = float(state["cc"])
        self._c1 = float(state["c1"])
        self._cmu = float(state["cmu"])
        self._damps = float(state["damps"])
        self._generation = int(state["generation"])
        self._chi_n = float(state["chi_n"])
        b = state.get("bounds")
        self._bounds = tuple(b) if b is not None else None  # type: ignore[assignment]

    # ----- convenience -------------------------------------------------------

    def best_so_far(self) -> np.ndarray:
        """Current best estimate of the optimum (= mean vector copy)."""
        return self._mean.copy()

    def reset(self) -> None:
        """Reset to initial state (preserves bounds / population_size / dim)."""
        self._sigma = self._sigma0
        self._mean = np.zeros(self._dim, dtype=np.float64)
        self._p_sigma = np.zeros(self._dim, dtype=np.float64)
        self._p_c = np.zeros(self._dim, dtype=np.float64)
        self._C = np.eye(self._dim, dtype=np.float64)
        self._generation = 0
        self._last_candidates = None
