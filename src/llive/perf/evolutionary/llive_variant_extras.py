# SPDX-License-Identifier: Apache-2.0
"""LV × SR 統合 helper — LlivVariantGenome (19 dim) を SelfAdaptive (38 dim)
/ MetaMutation (20 dim) / 両方 (39 dim) に拡張するための high-level API.

設計判断:

- LV 本体 (``llive_variant.py``) の 19 dim 定義は **既存実装互換** を保つため
  変更しない. この extras module で **拡張版** を提供.
- 拡張 genome の前半 19 dim を fitness 評価に使う wrapper を提供
  (``wrap_fitness_for_extended_genome``).
- SelfAdaptive (38 dim) は σ を後半 19 dim に保持. width-relative noise.
- MetaMutation (20 dim) は strategy_id を末尾 1 dim に保持.
- 両方 (39 dim) は object 19 + σ 19 + strategy_id 1.

参照: `docs/requirements_v0.D_self_referential_and_llm_operators.md` SR-01/02.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.individual import FitnessReport
from llive.perf.evolutionary.llive_variant import (
    LIVE_VARIANT_GENOME_BOUNDS,
    LIVE_VARIANT_GENOME_LABELS,
)
from llive.perf.evolutionary.meta_mutation import (
    MetaMutation,
    pack_meta_strategy_bounds,
)
from llive.perf.evolutionary.mutation import GaussianMutation, ResetMutation
from llive.perf.evolutionary.self_adaptive import (
    SelfAdaptiveGaussianMutation,
    initial_sigma_values,
    pack_self_adaptive_bounds,
)

LV_OBJECT_DIMS = 19  # LIVE_VARIANT_GENOME_BOUNDS の n_dims


# ---------------------------------------------------------------------------
# 1. SelfAdaptive 化 (38 dim)
# ---------------------------------------------------------------------------


def build_self_adaptive_variant_bounds(
    *,
    sigma_lower: float = 1e-4,
    sigma_upper: float = 1.0,
) -> tuple[GenomeBounds, tuple[str, ...]]:
    """LV 19 dim を 38 dim (σ-augmented) に拡張した bounds + labels.

    後半 19 dim は各 object dim の σ. ``sigma_lower / sigma_upper`` で
    σ の range を制御. width-relative noise なので [1e-4, 1.0] が穏当.
    """
    return pack_self_adaptive_bounds(
        LIVE_VARIANT_GENOME_BOUNDS,
        sigma_lower=sigma_lower,
        sigma_upper=sigma_upper,
        object_labels=LIVE_VARIANT_GENOME_LABELS,
    )


def make_self_adaptive_variant_mutation(
    *,
    tau_global: float | None = None,
    tau_local: float | None = None,
    p: float = 1.0,
) -> SelfAdaptiveGaussianMutation:
    """LV 19 dim 用の SelfAdaptiveGaussianMutation factory."""
    return SelfAdaptiveGaussianMutation(
        n_object_dims=LV_OBJECT_DIMS,
        tau_global=tau_global,
        tau_local=tau_local,
        p=p,
        relative_to_width=True,
    )


def initialize_self_adaptive_variant_genome_values(
    object_values: np.ndarray,
    *,
    sigma_init: float = 0.1,
) -> np.ndarray:
    """object_values (19,) と σ 初期値 (19,) を連結した 38 dim values を返す.

    object_values は LIVE_VARIANT_GENOME_BOUNDS 内 (uniform random 等).
    """
    if object_values.shape != (LV_OBJECT_DIMS,):
        raise ValueError(
            f"object_values must have shape ({LV_OBJECT_DIMS},), got {object_values.shape}"
        )
    sigmas = initial_sigma_values(LV_OBJECT_DIMS, sigma_init=sigma_init)
    return np.concatenate([object_values, sigmas])


# ---------------------------------------------------------------------------
# 2. MetaMutation 化 (20 dim)
# ---------------------------------------------------------------------------


def default_variant_meta_strategies() -> tuple:
    """LV 用の default 3 戦略 (Gaussian / Reset / Gaussian-aggressive).

    SelfAdaptive はここに混ぜず, **20 dim 版** を提供する場合の選択肢.
    """
    return (
        GaussianMutation(sigma=0.1, p=0.1),
        GaussianMutation(sigma=0.3, p=0.3),  # aggressive
        ResetMutation(p=0.02),
    )


def build_meta_strategy_variant_bounds(
    *, n_strategies: int = 3,
) -> tuple[GenomeBounds, tuple[str, ...]]:
    """LV 19 dim を 20 dim (strategy_id 末尾) に拡張."""
    return pack_meta_strategy_bounds(
        LIVE_VARIANT_GENOME_BOUNDS,
        n_strategies=n_strategies,
        object_labels=LIVE_VARIANT_GENOME_LABELS,
    )


def make_meta_variant_mutation(
    strategies: tuple | None = None,
) -> MetaMutation:
    """LV 用 MetaMutation factory. strategy_dim は 20 dim の最終 (-1)."""
    if strategies is None:
        strategies = default_variant_meta_strategies()
    return MetaMutation(strategies=strategies, strategy_dim=-1)


# ---------------------------------------------------------------------------
# 3. SelfAdaptive + MetaMutation 統合 (39 dim)
# ---------------------------------------------------------------------------


def build_self_adaptive_meta_strategy_variant_bounds(
    *,
    sigma_lower: float = 1e-4,
    sigma_upper: float = 1.0,
    n_strategies: int = 3,
) -> tuple[GenomeBounds, tuple[str, ...]]:
    """LV 19 dim を 39 dim (object 19 + σ 19 + strategy_id 1) に拡張.

    layout: ``[x_0 ... x_18, σ_0 ... σ_18, strategy_id]``.
    """
    sa_bounds, sa_labels = build_self_adaptive_variant_bounds(
        sigma_lower=sigma_lower, sigma_upper=sigma_upper
    )
    # sa_bounds (38 dim) に strategy_id を追加
    lower = list(sa_bounds.lower) + [0.0]
    upper = list(sa_bounds.upper) + [max(0.001, n_strategies - 0.001)]
    labels = list(sa_labels) + ["strategy_id"]
    return GenomeBounds(lower=tuple(lower), upper=tuple(upper)), tuple(labels)


# ---------------------------------------------------------------------------
# 4. Fitness wrapper — extended genome → 19 dim object var → fitness
# ---------------------------------------------------------------------------


def wrap_fitness_for_extended_genome(
    fitness_fn: Callable[[Genome], FitnessReport],
    *,
    n_object_dims: int = LV_OBJECT_DIMS,
) -> Callable[[Genome], FitnessReport]:
    """拡張 genome の前半 ``n_object_dims`` のみで fitness を評価する wrapper.

    ``fitness_fn`` は **19 dim Genome** を受け取る前提 (例: mock_variant_fitness).
    内部で extended Genome の前半 n_object_dims を切り出して 19 dim Genome を
    再構成してから ``fitness_fn`` を呼ぶ.

    σ や strategy_id は fitness 計算に **使われない** が, mutation で世代を
    跨いで進化する.
    """

    def _wrapped(genome: Genome) -> FitnessReport:
        if genome.n_dims < n_object_dims:
            raise ValueError(
                f"extended genome n_dims ({genome.n_dims}) < n_object_dims ({n_object_dims})"
            )
        object_values = np.asarray(genome.values[:n_object_dims])
        # 元の 19 dim bounds を使って Genome を再構成
        object_genome = Genome.from_values(
            object_values,
            bounds=LIVE_VARIANT_GENOME_BOUNDS,
            labels=LIVE_VARIANT_GENOME_LABELS,
        )
        return fitness_fn(object_genome)

    return _wrapped


__all__ = [
    "LV_OBJECT_DIMS",
    "build_meta_strategy_variant_bounds",
    "build_self_adaptive_meta_strategy_variant_bounds",
    "build_self_adaptive_variant_bounds",
    "default_variant_meta_strategies",
    "initialize_self_adaptive_variant_genome_values",
    "make_meta_variant_mutation",
    "make_self_adaptive_variant_mutation",
    "wrap_fitness_for_extended_genome",
]
