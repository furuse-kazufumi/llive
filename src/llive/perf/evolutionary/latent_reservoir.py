# SPDX-License-Identifier: Apache-2.0
"""LatentReservoirChromosome — 中立貯蔵庫染色体 (「余計な因子」/ neutral genetic material).

ユーザー要件 (2026-05-25): 「保守的なものが生き残る系では新しいアイデアも差別化も生まれない。
進化は突然変異から生まれるので **特異なもの** が生き残るようにしないと成立しない。標準化で
特異なものが生まれるには **余計な因子** も混ざっていないといけない」。

設計意図
--------
意味のある 10 思考因子 (``ThoughtFactorPerLayerChromosome``) だけを標準化して novelty で
選択しても、空間が閉じていて真の新規性は出にくい。本染色体は **意味を割り当てない自由遺伝子の
ベクトル** = 「余計な因子」を導入する。fitness の *品質* 目的はこれを読まない (中立) が、
**novelty 記述子には混ぜる**。すると:

* 変異がここに自由に溜まる (**cryptic variation** / 潜在変異)。
* 特異 (outlier) であることが novelty 選択で報われるので、貯蔵庫で偏った個体が生き残る。
* 後段で latent → 振る舞いへの bridge を足せば **exaptation** (中立材料の転用) が起きる余地。

これは進化生物学の **中立ネットワーク (neutral networks)** / **縮退 (degeneracy)** /
**中立ドリフトによる進化性 (evolvability)** の計算的具現。純粋冗長は進化性が低いが、縮退した
余剰材料は進化性を桁違いに上げる (Whitacre & Bender 2010; Wagner; Kimura 中立説)。
「染色体を増やす」の正しい目的 = 最適化対象を増やすのではなく **変異の貯蔵庫を増やす**。

References:
* Kimura, M. (1968). 中立進化説.
* Schuster & Fontana — RNA neutral networks.
* Whitacre & Bender (2010). Degeneracy: a design principle for robustness and evolvability.
* Lehman & Stanley (2011). Abandoning Objectives (novelty search).

設計判断 (既存 chromosome と整合):
* **frozen=True** + tuple で hashable。Genome3D 合流互換。
* 値域 [0, 1] (他 chromosome と同じ)。novelty 記述子に混ぜる際は標準化される。
* ``default`` は全 0.5 (中立)、``random`` は uniform、``sample_neighborhood`` は Gaussian+clip。
* ``as_array`` / ``as_flat`` を提供し diversity / novelty 記述子へ連結可能にする。
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np

#: 中立貯蔵庫のデフォルト遺伝子数。意味は持たない自由次元。
#: 生物の比率に倣い **ゲノムは大きく** 取る (ヒトは個体間で ~99.9% 同一、差は ~0.1%、
#: コード領域は ~1-2%)。個体差は限られた可変座位からしか生まれない → 大規模貯蔵庫 +
#: 疎変異 (sample_neighborhood が毎世代ごく一部だけ変異) でこの比率を再現する。
DEFAULT_RESERVOIR_SIZE: int = 256
#: 1 回の mutation で変異する座位の割合 (「個体差を決めるのは限られた部分」)。
#: 大半の座位は各世代で不変 = 保守的に共有され、差別化は疎に集中する。稀に可変窓が動くので
#: 貯蔵庫全体は時間をかけて探索可能 (= evolvability を担保)。
DEFAULT_MUTATION_DENSITY: float = 0.05
GENE_LO: float = 0.0
GENE_HI: float = 1.0


@dataclass(frozen=True)
class LatentReservoirChromosome:
    """意味を持たない自由遺伝子ベクトル (中立貯蔵庫 / 「余計な因子」).

    Attributes
    ----------
    genes : tuple[float, ...]
        各値 [0, 1]。fitness の品質目的は読まない (中立) が novelty 記述子に混ぜる。
    """

    genes: tuple[float, ...] = field(
        default_factory=lambda: tuple(0.5 for _ in range(DEFAULT_RESERVOIR_SIZE))
    )

    def __post_init__(self) -> None:
        if len(self.genes) < 1:
            raise ValueError("genes must be non-empty")
        for i, v in enumerate(self.genes):
            fv = float(v)
            if not (GENE_LO <= fv <= GENE_HI):
                raise ValueError(f"genes[{i}] = {fv} out of [{GENE_LO}, {GENE_HI}]")

    # ----- factories ------------------------------------------------------

    @classmethod
    def default(cls, size: int = DEFAULT_RESERVOIR_SIZE) -> LatentReservoirChromosome:
        """全 0.5 (中立) で初期化。"""
        return cls(genes=tuple(0.5 for _ in range(size)))

    @classmethod
    def random(
        cls, rng: np.random.Generator, size: int = DEFAULT_RESERVOIR_SIZE
    ) -> LatentReservoirChromosome:
        """uniform random で各遺伝子 ∈ [0, 1]。padding/初期多様性用。"""
        return cls(genes=tuple(float(v) for v in rng.uniform(GENE_LO, GENE_HI, size=size)))

    @classmethod
    def from_array(cls, arr: np.ndarray) -> LatentReservoirChromosome:
        """ndarray から構築。[0, 1] に clip。"""
        clipped = np.clip(np.asarray(arr, dtype=np.float64).ravel(), GENE_LO, GENE_HI)
        return cls(genes=tuple(float(v) for v in clipped))

    # ----- views ----------------------------------------------------------

    def as_array(self) -> np.ndarray:
        return np.asarray(self.genes, dtype=np.float64)

    def as_flat(self) -> np.ndarray:
        return self.as_array()

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {"genes": list(self.genes)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LatentReservoirChromosome:
        return cls(genes=tuple(float(v) for v in data["genes"]))

    # ----- evolution operators -------------------------------------------

    def sample_neighborhood(
        self,
        rng: np.random.Generator,
        step_size: float = 0.1,
        *,
        density: float = DEFAULT_MUTATION_DENSITY,
    ) -> LatentReservoirChromosome:
        """**疎変異**: 毎回ごく一部の座位 (≈``density``) だけに Gaussian noise を加える。

        「個体差を決めているのは遺伝子のごく限られた部分」(ユーザー 2026-05-25) を再現する。
        大半の座位は世代を跨いで不変 = 保守的に共有され、差別化は疎に集中する。変異する座位は
        毎回ランダムに選ばれるので可変窓が移動し、貯蔵庫全体は時間をかけて探索可能 (evolvability)。
        """
        arr = self.as_array()
        n = arr.shape[0]
        k = max(1, int(round(density * n)))
        idx = rng.choice(n, size=k, replace=False)
        noise = np.zeros(n)
        noise[idx] = rng.normal(0.0, step_size, size=k)
        return self.from_array(arr + noise)

    # ----- complexity ------------------------------------------------------

    def kolmogorov_proxy(self) -> int:
        """gzip 圧縮後 bytes 数 (Genome3D K と加法和を取るため独立に閉じた K)。"""
        payload = json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")
        return len(gzip.compress(payload))


def crossover_uniform_genes(
    parent_a: LatentReservoirChromosome,
    parent_b: LatentReservoirChromosome,
    rng: np.random.Generator,
) -> LatentReservoirChromosome:
    """遺伝子ごと 50/50 で親 A/B から選ぶ uniform crossover。

    長さ不一致時は短い方に合わせる (extensibility: 将来の可変長貯蔵庫に備える)。
    """
    a, b = parent_a.as_array(), parent_b.as_array()
    n = min(a.shape[0], b.shape[0])
    mask = rng.random(n) < 0.5
    return LatentReservoirChromosome.from_array(np.where(mask, a[:n], b[:n]))


__all__ = [
    "DEFAULT_RESERVOIR_SIZE",
    "GENE_HI",
    "GENE_LO",
    "LatentReservoirChromosome",
    "crossover_uniform_genes",
]
