# SPDX-License-Identifier: Apache-2.0
"""E.17 PersonaOverlapPenalty + MAP-Elites grid (CE-25 / CE-26).

ユーザー指示 (2026-05-21):
    「派生集団内で persona の被りを罰し、思考軸を空間的に分散させる。MAP-Elites
     grid で persona × thought_factor の 4 軸 quality-diversity archive を作る」

CE-25 と CE-26 は同じ集団に対する 2 つの異なる多様性圧:

- **PersonaOverlapPenalty (CE-25)** — fitness 軸に persona dissimilarity の
  集団平均を加算する。λ=0 で挙動は通常の fitness と同じ。λ を上げるほど
  集団内の persona overlap が penalty として効く。
- **MAPElitesGrid (CE-26)** — persona 2 軸 × thought_factor 2 軸 = 4 次元 grid
  を作り、各 cell に「これまでに submit された中で最大 fitness の個体」を残す。
  Mouret & Clune 2015 の MAP-Elites を 4 軸化したもの。`coverage` で
  archive の埋まり具合、`best_per_persona_slice` で persona 2 軸の各 cell に
  おける best variant を取得できる。

設計判断:

- Individual class を改変しない (既存 1497 PASS の test 構造を壊さない)。
  fitness と PersonaComposition を **外部から渡す** 形にする
- feature 抽出は generic にし、デフォルト実装 `default_map_elites_features` は
  PersonaComposition 単体から 4 次元 (mean, std, structurize, exploration) を抽出
- 既存 ``diversity.py`` (E.14-E.16/E.18) と分離: あちらは novelty 用、
  こちらは MAP-Elites / overlap penalty 用

要件根拠:
- ``docs/requirements_v0.E_competitive_coevolution.md`` 0.8 節 CE-25/CE-26
- [[project_llive_v0E_coevolution]] memory

参照:
- Mouret & Clune (2015). Illuminating search spaces by mapping elites.
- Goldberg & Richardson (1987). Fitness sharing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.persona import (
    PersonaComposition,
    THOUGHT_FACTORS,
    persona_dissimilarity,
)

# ---------------------------------------------------------------------------
# CE-25 — PersonaOverlapPenalty
# ---------------------------------------------------------------------------


@dataclass
class PersonaOverlapPenalty:
    """`fitness' = fitness + λ × mean_dissimilarity(self, others)`.

    集団内の persona overlap を罰し、思考軸の被りを fitness 軸で抑える。
    λ=0 で挙動は base_fitness と同じ。λ を上げるほど集団内で persona が
    被っていない個体ほど高い実効 fitness を得る。

    Notes
    -----
    `mean_dissimilarity` は **自分を除く他 N-1 人** との dissimilarity の
    平均。集団 size=1 のときは bonus 0 (== base_fitness)。

    Attributes
    ----------
    lambda_ : float
        多様性ボーナス係数. 0 以上.
    """

    lambda_: float = 0.5

    def __post_init__(self) -> None:
        if self.lambda_ < 0:
            raise ValueError(f"lambda_ must be >= 0, got {self.lambda_}")

    def apply(
        self,
        compositions: Sequence[PersonaComposition],
        base_fitnesses: Sequence[float] | np.ndarray,
    ) -> np.ndarray:
        """N 個 composition と base_fitness から effective fitness を返す.

        Returns
        -------
        np.ndarray
            shape (N,) effective fitness ベクトル.
        """
        n = len(compositions)
        if len(base_fitnesses) != n:
            raise ValueError(
                f"compositions ({n}) と base_fitnesses ({len(base_fitnesses)}) "
                "の長さが一致しない"
            )
        if n == 0:
            return np.zeros(0, dtype=np.float64)
        base = np.asarray(base_fitnesses, dtype=np.float64)
        if n == 1 or self.lambda_ == 0.0:
            return base.copy()

        diss = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            for j in range(i + 1, n):
                d = persona_dissimilarity(compositions[i], compositions[j])
                diss[i, j] = d
                diss[j, i] = d
        mean_diss = diss.sum(axis=1) / (n - 1)
        return base + self.lambda_ * mean_diss

    def mean_dissimilarity(
        self,
        compositions: Sequence[PersonaComposition],
    ) -> np.ndarray:
        """per-individual mean dissimilarity vector (debugging / observability 用)."""
        n = len(compositions)
        if n <= 1:
            return np.zeros(n, dtype=np.float64)
        diss = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            for j in range(i + 1, n):
                d = persona_dissimilarity(compositions[i], compositions[j])
                diss[i, j] = d
                diss[j, i] = d
        return diss.sum(axis=1) / (n - 1)


# ---------------------------------------------------------------------------
# CE-26 — MAP-Elites grid (4-axis: 2 persona × 2 thought_factor)
# ---------------------------------------------------------------------------


@dataclass
class MAPElitesCell:
    """1 cell に保存される best individual + feature snapshot."""

    individual: Individual
    fitness: float
    features: tuple[float, float, float, float]
    generation: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "individual": self.individual.to_dict(),
            "fitness": float(self.fitness),
            "features": list(self.features),
            "generation": int(self.generation),
        }


@dataclass
class MAPElitesGrid:
    """4 軸 MAP-Elites archive (Mouret & Clune 2015) の llive 向け実装.

    Axes (ユーザー仕様):
        0, 1 — persona 2 軸 (例: mean affinity / std affinity)
        2, 3 — thought_factor 2 軸 (例: factor_structurize / factor_exploration)

    Cell key は (bin_0, bin_1, bin_2, bin_3) tuple of ints. 各 cell に
    submit された個体のうち最大 fitness のものを保持する。

    Attributes
    ----------
    n_bins_per_axis : int
        各軸の bin 数. デフォルト 5 (5^4 = 625 cells).
    feature_ranges : tuple[(float, float), ...]
        各軸の (low, high). 軸ごとに別範囲を許す.
    cells : dict[tuple[int,int,int,int], MAPElitesCell]
        現在の archive 状態.
    """

    n_bins_per_axis: int = 5
    feature_ranges: tuple[tuple[float, float], ...] = (
        (0.0, 1.0),
        (0.0, 1.0),
        (0.0, 1.0),
        (0.0, 1.0),
    )
    cells: dict[tuple[int, int, int, int], MAPElitesCell] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.n_bins_per_axis < 1:
            raise ValueError(
                f"n_bins_per_axis must be >= 1, got {self.n_bins_per_axis}"
            )
        if len(self.feature_ranges) != 4:
            raise ValueError(
                "MAP-Elites requires 4 feature ranges "
                "(2 persona axes + 2 thought_factor axes)"
            )
        for low, high in self.feature_ranges:
            if not (high > low):
                raise ValueError(
                    f"invalid feature range ({low}, {high}); high must be > low"
                )

    # -- key / bin --------------------------------------------------------

    def _bin(self, value: float, axis: int) -> int:
        low, high = self.feature_ranges[axis]
        if value <= low:
            return 0
        if value >= high:
            return self.n_bins_per_axis - 1
        norm = (value - low) / (high - low)
        idx = int(norm * self.n_bins_per_axis)
        return min(idx, self.n_bins_per_axis - 1)

    def key(
        self, features: Sequence[float]
    ) -> tuple[int, int, int, int]:
        if len(features) != 4:
            raise ValueError(
                f"features must be length 4, got {len(features)}"
            )
        return (
            self._bin(features[0], 0),
            self._bin(features[1], 1),
            self._bin(features[2], 2),
            self._bin(features[3], 3),
        )

    # -- submit / query ---------------------------------------------------

    def submit(
        self,
        individual: Individual,
        fitness: float,
        features: Sequence[float],
        *,
        generation: int = 0,
    ) -> bool:
        """1 個体を archive に投入. 改善があれば True.

        - cell が空 → 必ず採用.
        - cell に既存個体がいる → fitness 比較 (大きい方を残す).
        """
        k = self.key(features)
        feats_tuple: tuple[float, float, float, float] = (
            float(features[0]),
            float(features[1]),
            float(features[2]),
            float(features[3]),
        )
        existing = self.cells.get(k)
        if existing is None or fitness > existing.fitness:
            self.cells[k] = MAPElitesCell(
                individual=individual,
                fitness=float(fitness),
                features=feats_tuple,
                generation=int(generation),
            )
            return True
        return False

    def submit_many(
        self,
        items: Sequence[tuple[Individual, float, Sequence[float]]],
        *,
        generation: int = 0,
    ) -> int:
        """複数個体を一括 submit. 採用された数を返す."""
        accepted = 0
        for ind, fit, feats in items:
            if self.submit(ind, fit, feats, generation=generation):
                accepted += 1
        return accepted

    # -- metrics ----------------------------------------------------------

    @property
    def n_filled(self) -> int:
        return len(self.cells)

    @property
    def n_cells_total(self) -> int:
        return self.n_bins_per_axis ** 4

    @property
    def coverage(self) -> float:
        """archive 占有率 [0, 1]. = n_filled / n_cells_total."""
        total = self.n_cells_total
        return self.n_filled / total if total > 0 else 0.0

    @property
    def best(self) -> MAPElitesCell | None:
        """archive 全体での最大 fitness cell."""
        if not self.cells:
            return None
        return max(self.cells.values(), key=lambda c: c.fitness)

    def best_per_persona_slice(self) -> dict[tuple[int, int], MAPElitesCell]:
        """persona 2 軸 (axis 0, 1) の各 (bin, bin) で thought_factor 軸を
        marginalize した best cell を返す.

        Returns
        -------
        dict[(int, int), MAPElitesCell]
            persona 軸の cell index → 最大 fitness の cell.
        """
        slices: dict[tuple[int, int], MAPElitesCell] = {}
        for k, cell in self.cells.items():
            pkey = (k[0], k[1])
            if pkey not in slices or cell.fitness > slices[pkey].fitness:
                slices[pkey] = cell
        return slices

    def fitness_grid(self) -> np.ndarray:
        """4D ndarray (n_bins, n_bins, n_bins, n_bins). 未埋め cell は -inf.

        観察 / 可視化 (heatmap) 用. 大きな grid だと O(n^4) メモリに注意.
        """
        nb = self.n_bins_per_axis
        arr = np.full((nb, nb, nb, nb), -np.inf, dtype=np.float64)
        for k, cell in self.cells.items():
            arr[k] = cell.fitness
        return arr

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_bins_per_axis": int(self.n_bins_per_axis),
            "feature_ranges": [list(r) for r in self.feature_ranges],
            "cells": {
                ",".join(str(x) for x in k): v.to_dict()
                for k, v in self.cells.items()
            },
        }


# ---------------------------------------------------------------------------
# Default feature extractors
# ---------------------------------------------------------------------------


# Per CLAUDE.md: factor_structurize は THOUGHT_FACTORS[0],
# factor_exploration は THOUGHT_FACTORS[5]. これらを thought_factor 2 軸の
# デフォルトに据える (要件 doc Phase E.10 で導入された persona ontology の
# effective_factor_affinity を利用).
_FACTOR_STRUCTURIZE_IDX = THOUGHT_FACTORS.index("factor_structurize")
_FACTOR_EXPLORATION_IDX = THOUGHT_FACTORS.index("factor_exploration")


def default_persona_features(
    composition: PersonaComposition | None,
) -> tuple[float, float]:
    """persona 2 軸 feature の既定実装.

    axis 0 = effective_factor_affinity の **平均**
        ("どれくらい多くの因子を均等にカバーするか" を粗く表現).
    axis 1 = effective_factor_affinity の **標準偏差**
        ("特定因子に偏った specialization か, 均等な generalist か").

    composition=None のときは中央値 (0.5, 0.0) を返し grid 中央寄りに落とす.
    """
    if composition is None:
        return (0.5, 0.0)
    aff = composition.effective_factor_affinity()
    return (float(aff.mean()), float(aff.std()))


def default_thought_features(
    composition: PersonaComposition | None,
) -> tuple[float, float]:
    """thought_factor 2 軸 feature の既定実装.

    axis 0 = effective_factor_affinity[factor_structurize]
    axis 1 = effective_factor_affinity[factor_exploration]

    "構造化と探索の 2 軸" は llive 10 思考因子のうち代表的な対立軸として
    [[project_llive_cog_fx_factors]] で繰り返し言及されている.
    """
    if composition is None:
        return (0.5, 0.5)
    aff = composition.effective_factor_affinity()
    return (
        float(aff[_FACTOR_STRUCTURIZE_IDX]),
        float(aff[_FACTOR_EXPLORATION_IDX]),
    )


def default_map_elites_features(
    composition: PersonaComposition | None,
) -> tuple[float, float, float, float]:
    """4 軸 feature をまとめて返すヘルパ. MAPElitesGrid.submit に直接渡せる."""
    p1, p2 = default_persona_features(composition)
    t1, t2 = default_thought_features(composition)
    return (p1, p2, t1, t2)


__all__ = [
    "MAPElitesCell",
    "MAPElitesGrid",
    "PersonaOverlapPenalty",
    "default_map_elites_features",
    "default_persona_features",
    "default_thought_features",
]
