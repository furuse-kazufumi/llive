# SPDX-License-Identifier: Apache-2.0
"""MetaMutation — strategy 選択を genome 内に埋め込む meta-evolution (llive v0.D SR-02).

Promptbreeder (DeepMind 2023, arXiv:2309.16797) では「mutation prompt 自体を
進化させる」発想を採る. 数値 genome 版では **mutation の種類自体を genome
の 1 dim に含める** ことで, 集団内で複数の mutation 戦略が並走し, 世代と
共に **dominant strategy が浮上** する meta-evolution を実現する.

設計:

- ``strategy_dim`` で genome 内の strategy_id index を指定 (慣例: 最終 dim).
- strategy_id ∈ [0, 1, 2, ...] を ``round(value)`` で整数化.
- ``MetaMutation(strategies=(GaussianMutation(...), ResetMutation(...), ...))``
  に登録された mutation を strategy_id で dispatch.
- strategy_dim 自体には mutation を **加えない** (戦略選択は別軸で進化).

参照:

- Bäck, T. et al. (1997). *Handbook of Evolutionary Computation*. Ch. C7
  (Self-Adaptation).
- Fernando, C. et al. (2023). [Promptbreeder](https://arxiv.org/abs/2309.16797).
- llive `docs/requirements_v0.D_self_referential_and_llm_operators.md` SR-02.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np

from llive.perf.evolutionary.genome import Genome, GenomeBounds


MutationFn = Callable[[Genome, np.random.Generator], Genome]


@dataclass(frozen=True)
class MetaMutation:
    """genome[strategy_dim] の値で strategy を dispatch する wrapper.

    Parameters
    ----------
    strategies : tuple[MutationFn, ...]
        登録 mutation 戦略. strategy_id 0 → strategies[0] が呼ばれる.
        最低 2 戦略以上推奨 (1 戦略のみなら単純 wrapper になる).
    strategy_dim : int
        genome 内の strategy_id を保持する dim index. default -1 (最終 dim).
    """

    strategies: tuple[MutationFn, ...]
    strategy_dim: int = -1

    def __post_init__(self) -> None:
        if not self.strategies:
            raise ValueError("strategies must contain at least 1 mutation")

    # ---------- public API ----------------------------------------------

    def __call__(self, genome: Genome, rng: np.random.Generator) -> Genome:
        if genome.n_dims == 0:
            raise ValueError("genome must have at least 1 dim")
        idx = self._resolve_strategy_index(genome)
        # bounds に応じて strategy_id を 0..len(strategies)-1 に clip
        n_strategies = len(self.strategies)
        clipped_id = max(0, min(n_strategies - 1, int(round(genome.values[idx]))))
        strategy = self.strategies[clipped_id]
        return strategy(genome, rng)

    def _resolve_strategy_index(self, genome: Genome) -> int:
        if self.strategy_dim < 0:
            return genome.n_dims + self.strategy_dim
        return self.strategy_dim


def pack_meta_strategy_bounds(
    object_bounds: GenomeBounds,
    *,
    n_strategies: int,
    object_labels: tuple[str, ...] = (),
    strategy_label: str = "strategy_id",
) -> tuple[GenomeBounds, tuple[str, ...]]:
    """object bounds に strategy_id dim を追加した bounds + labels を返す.

    strategy_id の range は ``[0.0, n_strategies - 0.001]``. round() で整数化
    して strategy index に使う.
    """
    if n_strategies < 1:
        raise ValueError("n_strategies must be >= 1")
    n = object_bounds.n_dims
    lower = list(object_bounds.lower) + [0.0]
    upper = list(object_bounds.upper) + [max(0.001, n_strategies - 0.001)]
    if object_labels:
        if len(object_labels) != n:
            raise ValueError("object_labels length must equal object_bounds.n_dims")
        obj_lbl = list(object_labels)
    else:
        obj_lbl = [f"dim_{i}" for i in range(n)]
    return (
        GenomeBounds(lower=tuple(lower), upper=tuple(upper)),
        tuple(obj_lbl + [strategy_label]),
    )


def strategy_distribution(
    individuals: Iterable, *, strategy_dim: int = -1, n_strategies: int = 0
) -> dict[int, int]:
    """集団内の strategy_id 分布を集計 (debug / 観察用).

    Returns
    -------
    dict[int, int]
        strategy_id → 個体数. ``n_strategies > 0`` なら 0..n-1 を全て埋める.
    """
    counts: dict[int, int] = {}
    inds_list = list(individuals)
    for ind in inds_list:
        idx = strategy_dim if strategy_dim >= 0 else ind.genome.n_dims + strategy_dim
        sid = int(round(ind.genome.values[idx]))
        sid = max(0, min(n_strategies - 1, sid)) if n_strategies > 0 else max(0, sid)
        counts[sid] = counts.get(sid, 0) + 1
    if n_strategies > 0:
        for i in range(n_strategies):
            counts.setdefault(i, 0)
    return counts


__all__ = [
    "MetaMutation",
    "pack_meta_strategy_bounds",
    "strategy_distribution",
]
