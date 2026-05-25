# SPDX-License-Identifier: Apache-2.0
"""Genome3D — 多階建てゲノム結合 dataclass (llive v0.F EV-13 + v0.I EV-21 + 2026-05-23 EV-22 join).

着地済みの chromosome (現 4 階建て, class 名は歴史的経緯で ``Genome3D``):

* :class:`ImplChromosome` — 実装的選択 (コード層 / v0.F 柱 A-1)
* :class:`PromptChromosome` — 偉人思想・スキル・ルール (プロンプト層 / v0.F 柱 A-2)
* :class:`MetaChromosome` — 進化アルゴリズム自体 (メタ層 / v0.I §3.2)
* :class:`ThoughtFactorPerLayerChromosome` — 10 思考因子 × メモリ層 2D matrix
  (因子層 / 2026-05-23 ユーザー要件: 「10 因子がゲノム化できているのが理想」).
  既存 ``LIVE_VARIANT_GENOME`` の scalar 10 dim を拡張して層別 (working /
  short_term / long_term / episodic) に強度を持てるよう一段上げたもの.

を **frozen な 1 つの aggregate** にまとめる. v0.F 要件 §2 (2 階建てゲノム),
v0.I 要件 §3.3 (3 階建てゲノム / cross-substrate self-improvement),
そして因子 × 層構造 (本セッション) の結節点.

設計方針:

- ``Genome3D`` は **完全に state-less** な遺伝表現. EvolutionLoop / 評価関数 /
  selector は touch しない. 3 つの sub-chromosome は frozen のため,
  ``Genome3D`` も自動的に frozen / hashable.
- ``Genome3D.kolmogorov_proxy()`` は 3 chromosome の gzip K の **加法和**
  (Schmidhuber 2003 / Cilibrasi & Vitanyi 2005 系の連結近似). 厳密な K(joint)
  ≠ Σ K(piece) だが計算可能な上界として扱う.
- ``sample_neighborhood(rng, step_size)`` は 3 chromosome を独立に同じ
  step_size で sample. 層別 step_size が必要になったら MetaChromosome の
  ``mutation_rate_per_layer`` を介して制御するため, ここでは API を単純に保つ.

Crossover 2 種 (関数として export):

- ``intra_layer_crossover(a, b, rng)`` — 各層を独立に 50/50 で choice.
  v0.F 要件 §3.3 「層内 crossover」相当. 親 A / 親 B のどちらの C_impl が
  選ばれるかは独立コインフリップ.
- ``cross_layer_crossover(a, b, rng)`` — 親 A の code 層 + 親 B の prompt 層 +
  meta 層は片親優位 (50/50). v0.F 要件 §3.3 「層間 crossover」相当.
  cross-substrate な遺伝物質交換を模倣する.

References:

- llive `docs/requirements_v0.F_genome_two_layer_and_novelty.md` §2-§3.3.
- llive `docs/requirements_v0.I_meta_evolution_and_cross_substrate.md` §3.3.
- Schmidhuber, J. (2003). Gödel Machine.
- Real, E. et al. (2020). AutoML-Zero ([arXiv:2003.03384](https://arxiv.org/abs/2003.03384)).
- Wang, R. et al. (2024). Promptbreeder ([arXiv:2309.16797](https://arxiv.org/abs/2309.16797)).

Status (2026-05-22 着地): skeleton. データ結合 + serialization +
kolmogorov proxy 加法 + neighborhood sampling + 2 種 crossover のみ.
実 EvolutionLoop / Population への注入は EV-14 以降.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from llive.perf.evolutionary.impl_chromosome import ImplChromosome
from llive.perf.evolutionary.meta_chromosome import MetaChromosome
from llive.perf.evolutionary.prompt_chromosome import PromptChromosome
from llive.perf.evolutionary.thought_factor_per_layer import (
    ThoughtFactorPerLayerChromosome,
    crossover_per_factor as _factor_crossover_per_factor,
)


@dataclass(frozen=True)
class Genome3D:
    """多階建てゲノム (C_impl + C_prompt + C_meta + C_factors) の frozen aggregate.

    v0.F 2 階建て (impl + prompt) と v0.I 3 階建て (+meta), さらに本セッション
    (2026-05-23) で 4 層目として加わった因子×層 2D matrix の合流点. class 名は
    歴史的経緯で ``Genome3D`` のまま (referenecs/import 不変を優先).

    EvolutionLoop / selector / fitness 評価は本クラスを受け取って 4 chromosome
    それぞれを参照する. skeleton 段階では既存 v0.B :class:`Genome`
    (scalar 19 dim) と並走し, Population は引き続き Genome ベース. Genome3D は
    段階的に注入される.

    Backward-compat: ``c_factors`` は default factory 付きなので, ``c_impl``
    / ``c_prompt`` / ``c_meta`` のみを指定する既存コードはそのまま動く.
    ``from_dict`` も ``c_factors`` キー欠落時は default を使う.
    """

    #: 実装層 (コード層). frozen dataclass.
    c_impl: ImplChromosome

    #: プロンプト層 (思想・スキル・ルール). frozen dataclass.
    c_prompt: PromptChromosome

    #: メタ層 (進化アルゴリズム自身). frozen dataclass.
    c_meta: MetaChromosome

    #: 因子層 (10 思考因子 × メモリ層 2D matrix). frozen dataclass.
    #: 2026-05-23 ユーザー要件「10 因子がゲノム化できているのが理想」由来.
    c_factors: ThoughtFactorPerLayerChromosome = field(
        default_factory=ThoughtFactorPerLayerChromosome.default
    )

    # ----- factories ------------------------------------------------------

    @classmethod
    def default(cls) -> Genome3D:
        """v0.B baseline 互換のデフォルト. 4 chromosome 全て default 値."""
        return cls(
            c_impl=ImplChromosome.default(),
            c_prompt=PromptChromosome.default(),
            c_meta=MetaChromosome.default(),
            c_factors=ThoughtFactorPerLayerChromosome.default(),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Genome3D:
        """nested dict → Genome3D 復元. ``to_dict()`` と round-trip 整合.

        Backward-compat: ``c_factors`` キーが無ければ default を使う.
        """
        kwargs: dict[str, Any] = {
            "c_impl": ImplChromosome.from_dict(data["c_impl"]),
            "c_prompt": PromptChromosome.from_dict(data["c_prompt"]),
            "c_meta": MetaChromosome.from_dict(data["c_meta"]),
        }
        if "c_factors" in data:
            kwargs["c_factors"] = ThoughtFactorPerLayerChromosome.from_dict(
                data["c_factors"]
            )
        return cls(**kwargs)

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """4 chromosome を nested dict 化. JSON 化可能."""
        return {
            "c_impl": self.c_impl.to_dict(),
            "c_prompt": self.c_prompt.to_dict(),
            "c_meta": self.c_meta.to_dict(),
            "c_factors": self.c_factors.to_dict(),
        }

    # ----- Kolmogorov complexity proxy ------------------------------------

    def kolmogorov_proxy(self) -> int:
        """gzip K(joint) の上界近似. 4 chromosome の K を加法和で集約.

        厳密には K(A,B,C,D) ≤ K(A) + K(B) + K(C) + K(D) + O(1)
        (Li & Vitanyi 2008 §2.8) だが, 計算可能近似 (gzip) では各 chromosome の
        json を独立に圧縮したものを加算する形を採る.
        """
        return (
            self.c_impl.kolmogorov_proxy()
            + self.c_prompt.kolmogorov_proxy()
            + self.c_meta.kolmogorov_proxy()
            + self.c_factors.kolmogorov_proxy()
        )

    # ----- neighborhood sampling ------------------------------------------

    def sample_neighborhood(
        self,
        rng: np.random.Generator,
        step_size: float = 0.1,
    ) -> Genome3D:
        """各層を独立に sample_neighborhood. step_size は 4 chromosome 共通.

        層別 step_size を使いたい場合は ``c_meta.mutation_rate_per_layer`` から
        派生させる EvolutionLoop 側で実装. ここでは API を単純に保つ.
        """
        return Genome3D(
            c_impl=self.c_impl.sample_neighborhood(rng, step_size),
            c_prompt=self.c_prompt.sample_neighborhood(rng, step_size),
            c_meta=self.c_meta.sample_neighborhood(rng, step_size),
            c_factors=self.c_factors.sample_neighborhood(rng, step_size),
        )


# ---------------------------------------------------------------------------
# Crossover 2 種
# ---------------------------------------------------------------------------


def intra_layer_crossover(
    parent_a: Genome3D,
    parent_b: Genome3D,
    rng: np.random.Generator,
) -> Genome3D:
    """各層を独立に 50/50 で choice (層内 crossover).

    v0.F 要件 §3.3 の「層内 crossover」. 親 A / 親 B のどちらの ``c_impl`` が
    選ばれるかは独立コインフリップで決まり, ``c_prompt`` / ``c_meta`` /
    ``c_factors`` も同様. 4 層独立 → 2^4 = 16 通りの組合せが等確率で生まれる.

    Args:
        parent_a: 親 A. frozen Genome3D.
        parent_b: 親 B. frozen Genome3D.
        rng: numpy RNG.

    Returns:
        子 Genome3D. 各層は親 A / 親 B のうちどちらか.
    """
    return Genome3D(
        c_impl=parent_a.c_impl if rng.random() < 0.5 else parent_b.c_impl,
        c_prompt=parent_a.c_prompt if rng.random() < 0.5 else parent_b.c_prompt,
        c_meta=parent_a.c_meta if rng.random() < 0.5 else parent_b.c_meta,
        c_factors=parent_a.c_factors
        if rng.random() < 0.5
        else parent_b.c_factors,
    )


def cross_layer_crossover(
    parent_a: Genome3D,
    parent_b: Genome3D,
    rng: np.random.Generator,
) -> Genome3D:
    """親 A から code 層, 親 B から prompt 層, meta / factors は混合 (層間 crossover).

    v0.F 要件 §3.3 の「層間 crossover」. cross-substrate な遺伝物質交換を模倣.

    - ``c_impl`` は **常に親 A** から (code substrate fixed)
    - ``c_prompt`` は **常に親 B** から (prompt substrate fixed)
    - ``c_meta`` は 50/50 で片親優位 (どちらのアルゴリズムを受け継ぐかは確率的)
    - ``c_factors`` は **因子ごと 50/50 混合** (`crossover_per_factor`):
      行 = 思考因子, ということは「ある因子の層別 profile は親 A から,
      別の因子の層別 profile は親 B から」を継承する. これは cross-substrate な
      因子分布交換になり, code/prompt 層の cross 遺伝と同じく「親 A の世界観 +
      親 B の世界観」を一段細かく混ぜる.

    Args:
        parent_a: コード層 donor + factor 混合の親 A. frozen Genome3D.
        parent_b: プロンプト層 donor + factor 混合の親 B. frozen Genome3D.
        rng: numpy RNG.

    Returns:
        子 Genome3D.
    """
    use_a_meta = rng.random() < 0.5
    return Genome3D(
        c_impl=parent_a.c_impl,
        c_prompt=parent_b.c_prompt,
        c_meta=parent_a.c_meta if use_a_meta else parent_b.c_meta,
        c_factors=_factor_crossover_per_factor(
            parent_a.c_factors, parent_b.c_factors, rng
        ),
    )


# ---------------------------------------------------------------------------
# flat numeric view (shared by Population diversity / NoveltyScorer)
# ---------------------------------------------------------------------------


def genome_flat_vector(genome: object) -> np.ndarray:
    """Flat float64 view of any genome, for diversity / novelty distance math.

    - flat :class:`~llive.perf.evolutionary.genome.Genome` → its ``as_array()``
      (the 19-dim vector).
    - :class:`Genome3D` → ``c_factors.as_flat()`` (the 10×layer factor matrix,
      flattened). impl/prompt/meta are categorical and not part of this
      continuous view — diversity over Genome3D is measured on the factor layer
      only (same choice as ``scripts/demo_genome3d_evolution.py``). Extending to
      include a categorical (Hamming) component is a later refinement.

    A population is homogeneous (all flat *or* all Genome3D) within one run, so
    the per-population vectors are always the same length.
    """
    as_array = getattr(genome, "as_array", None)
    if callable(as_array):
        return np.asarray(as_array(), dtype=np.float64)
    if isinstance(genome, Genome3D):
        return np.asarray(genome.c_factors.as_flat(), dtype=np.float64)
    raise TypeError(f"unsupported genome type for flat vector: {type(genome).__name__}")


__all__ = [
    "Genome3D",
    "cross_layer_crossover",
    "genome_flat_vector",
    "intra_layer_crossover",
]
