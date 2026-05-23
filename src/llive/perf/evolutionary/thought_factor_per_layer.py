# SPDX-License-Identifier: Apache-2.0
"""ThoughtFactorPerLayerChromosome — 10 思考因子 × メモリ層 の 2D matrix genome.

ユーザー要件 (2026-05-23): 「10 因子がゲノム化できているのが理想」.

# 現状 (本 module 着地前)

llive v0.C `LIVE_VARIANT_GENOME_BOUNDS` には既に 10 思考因子が
**scalar 1 dim/因子 (合計 10 dim)** で含まれている (`llive_variant.py:78`).
これは「全体の傾向」だけ表現する simple encoding.

# 本 module が加える 1 段

10 因子 × メモリ層 の **2D matrix (10 × N_layers)** に拡張する.
層によって異なる因子強度が進化可能になり, 以下のような分布が探索できる:

* 「**不確実性**」因子: working layer で強 / episodic で弱
  (= 短期推論で exploration, 長期記憶で integrate)
* 「**来歴**」因子: episodic layer で強 / working で弱
  (= 過去の情報源を長期に保持する)
* 「**現実接続**」因子: short_term layer で強
  (= 直近の実観測を anchor として使う)

これは生物学的に妥当な「**因子の局在化**」を遺伝表現に取り入れるもので,
[[project_llive_cog_fx_factors]] の 10 因子設計と
[[project_llive_v0F_genome_two_layer]] の階層ゲノム方針を接続する.

# 既存実装との位置づけ

* :class:`Genome` (v0.B scalar 19 dim) — flat な強度値. 既存 EvolutionLoop が使う.
* :class:`Genome3D` (v0.F/v0.I 3 階建て: impl + prompt + meta) — 階層化された
  chromosome aggregate. **本 module はその 4 つ目 (因子 × 層) を追加候補として
  独立 chromosome で着地** させる. Genome3D 統合は別段階.
* :class:`Persona.factor_affinity` (10 dim, persona.py:78) — 偉人 persona が
  保持する 10 因子親和度. **本 module の matrix と同じ THOUGHT_FACTORS 順序**
  なので, ``ThoughtFactorPerLayerChromosome × Persona`` で「persona 親和度を
  どの層に **書き込む**か」が表現できる (SSM × 10 因子 Bridge の前駆).

# 設計判断

* **frozen=True** + tuple-of-tuple で hashable. Genome3D との合流互換.
* 値域は **[0, 1]** に正規化. ``LIVE_VARIANT_GENOME_BOUNDS`` の thought_factor
  既存値域と一致.
* **層名 (`layer_names`)** は default に 4 メモリ層を取るが任意拡張可能.
  「短期/中期/長期/エピソード」など [[project_llive_v06_legal]] の architecture と整合.
* Crossover 2 種を提供: ``per_factor`` (因子行ごと) と ``per_layer`` (層列ごと).
  Genome3D の ``intra_layer_crossover`` / ``cross_layer_crossover`` と命名整合.
* ``kolmogorov_proxy`` は gzip 圧縮後 bytes 数. Genome3D K と **加法和** が
  取れるよう同一インターフェース.

# 後段計画

1. Genome3D に 4 番目の chromosome (c_factors) を追加するか, PromptChromosome
   内に統合するかをユーザー判断で確定.
2. fitness 評価で「層別因子が出力品質に与える効果」を NSGA2 多目的軸で測る.
3. SSM × 10 因子 Bridge (QIITA #24-06) の前駆: SSM hidden state ``h_t`` から
   matrix を読み出す bridge を実装.

References:
* THOUGHT_FACTORS (10): :mod:`llive.perf.evolutionary.persona`
* Cohoon et al. (1987) Island GA.
* Stanley & Miikkulainen (2002) NEAT (heterogeneous topology evolution).
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from llive.perf.evolutionary.persona import THOUGHT_FACTORS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUM_THOUGHT_FACTORS: int = len(THOUGHT_FACTORS)  # 10
DEFAULT_MEMORY_LAYER_NAMES: tuple[str, ...] = (
    "working",
    "short_term",
    "long_term",
    "episodic",
)
NUM_MEMORY_LAYERS: int = len(DEFAULT_MEMORY_LAYER_NAMES)  # 4

# 各 (factor, layer) cell の値域
FACTOR_WEIGHT_LO: float = 0.0
FACTOR_WEIGHT_HI: float = 1.0


# ---------------------------------------------------------------------------
# Chromosome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThoughtFactorPerLayerChromosome:
    """10 思考因子 × メモリ層の matrix genome.

    Attributes
    ----------
    factor_weights : tuple[tuple[float, ...], ...]
        shape (NUM_THOUGHT_FACTORS, len(layer_names)). 各値は [0, 1].
        ``factor_weights[i][j]`` = THOUGHT_FACTORS[i] の layer_names[j] への強度.
    layer_names : tuple[str, ...]
        メモリ層名. default は :data:`DEFAULT_MEMORY_LAYER_NAMES`.
    """

    factor_weights: tuple[tuple[float, ...], ...]
    layer_names: tuple[str, ...] = field(default=DEFAULT_MEMORY_LAYER_NAMES)

    def __post_init__(self) -> None:
        if len(self.factor_weights) != NUM_THOUGHT_FACTORS:
            raise ValueError(
                f"factor_weights must have {NUM_THOUGHT_FACTORS} rows "
                f"(one per thought factor), got {len(self.factor_weights)}"
            )
        n_layers = len(self.layer_names)
        if n_layers < 1:
            raise ValueError("layer_names must be non-empty")
        for i, row in enumerate(self.factor_weights):
            if len(row) != n_layers:
                raise ValueError(
                    f"row {i} ({THOUGHT_FACTORS[i]}) has {len(row)} cols "
                    f"but layer_names has {n_layers}"
                )
            for j, val in enumerate(row):
                fval = float(val)
                if not (FACTOR_WEIGHT_LO <= fval <= FACTOR_WEIGHT_HI):
                    raise ValueError(
                        f"factor_weights[{i}][{j}] = {fval} "
                        f"out of [{FACTOR_WEIGHT_LO}, {FACTOR_WEIGHT_HI}]"
                    )

    # ----- factories ------------------------------------------------------

    @classmethod
    def default(
        cls,
        layer_names: tuple[str, ...] = DEFAULT_MEMORY_LAYER_NAMES,
    ) -> ThoughtFactorPerLayerChromosome:
        """全 cell uniform 0.5 (中立) で初期化."""
        return cls(
            factor_weights=tuple(
                tuple(0.5 for _ in range(len(layer_names)))
                for _ in range(NUM_THOUGHT_FACTORS)
            ),
            layer_names=layer_names,
        )

    @classmethod
    def random(
        cls,
        rng: np.random.Generator,
        layer_names: tuple[str, ...] = DEFAULT_MEMORY_LAYER_NAMES,
    ) -> ThoughtFactorPerLayerChromosome:
        """uniform random で各 cell ∈ [0, 1] を生成."""
        arr = rng.uniform(
            FACTOR_WEIGHT_LO,
            FACTOR_WEIGHT_HI,
            size=(NUM_THOUGHT_FACTORS, len(layer_names)),
        )
        return cls(
            factor_weights=tuple(tuple(row.tolist()) for row in arr),
            layer_names=layer_names,
        )

    @classmethod
    def from_array(
        cls,
        arr: np.ndarray,
        layer_names: tuple[str, ...] = DEFAULT_MEMORY_LAYER_NAMES,
    ) -> ThoughtFactorPerLayerChromosome:
        """numpy ndarray から構築. 値は [0, 1] に clip される."""
        expected_shape = (NUM_THOUGHT_FACTORS, len(layer_names))
        if arr.shape != expected_shape:
            raise ValueError(
                f"arr shape {arr.shape} != {expected_shape}"
            )
        clipped = np.clip(arr, FACTOR_WEIGHT_LO, FACTOR_WEIGHT_HI)
        return cls(
            factor_weights=tuple(tuple(row.tolist()) for row in clipped),
            layer_names=layer_names,
        )

    @classmethod
    def from_persona_affinity(
        cls,
        persona_affinity: tuple[float, ...],
        *,
        broadcast_strategy: str = "uniform",
        layer_names: tuple[str, ...] = DEFAULT_MEMORY_LAYER_NAMES,
    ) -> ThoughtFactorPerLayerChromosome:
        """Persona.factor_affinity (10 dim) を 2D matrix に broadcast.

        ``broadcast_strategy``:
        * ``"uniform"`` — 同じ affinity 値を全層に複製 (default).
        * ``"working_heavy"`` — working 層に affinity, 他層は 0.5.
        * ``"episodic_heavy"`` — episodic 層に affinity, 他層は 0.5.
        """
        if len(persona_affinity) != NUM_THOUGHT_FACTORS:
            raise ValueError(
                f"persona_affinity must have {NUM_THOUGHT_FACTORS} values"
            )
        n_layers = len(layer_names)
        if broadcast_strategy == "uniform":
            arr = np.tile(np.asarray(persona_affinity)[:, None], (1, n_layers))
        elif broadcast_strategy == "working_heavy":
            arr = np.full((NUM_THOUGHT_FACTORS, n_layers), 0.5)
            arr[:, 0] = persona_affinity
        elif broadcast_strategy == "episodic_heavy":
            arr = np.full((NUM_THOUGHT_FACTORS, n_layers), 0.5)
            arr[:, -1] = persona_affinity
        else:
            raise ValueError(f"unknown broadcast_strategy: {broadcast_strategy!r}")
        return cls.from_array(arr, layer_names=layer_names)

    # ----- views ----------------------------------------------------------

    def as_array(self) -> np.ndarray:
        """numpy ndarray shape (NUM_THOUGHT_FACTORS, len(layer_names))."""
        return np.asarray(self.factor_weights, dtype=np.float64)

    def as_flat(self) -> np.ndarray:
        """flatten された 1D ndarray (10 * n_layers,) 形."""
        return self.as_array().flatten()

    def get_factor_layer(self, factor: str, layer: str) -> float:
        """``factor`` × ``layer`` の cell 値."""
        try:
            fi = THOUGHT_FACTORS.index(factor)
        except ValueError as exc:
            raise KeyError(f"unknown thought factor: {factor!r}") from exc
        try:
            li = self.layer_names.index(layer)
        except ValueError as exc:
            raise KeyError(f"unknown memory layer: {layer!r}") from exc
        return float(self.factor_weights[fi][li])

    def factor_profile(self, factor: str) -> tuple[float, ...]:
        """1 因子の層別 profile (len(layer_names) 長)."""
        try:
            fi = THOUGHT_FACTORS.index(factor)
        except ValueError as exc:
            raise KeyError(f"unknown thought factor: {factor!r}") from exc
        return self.factor_weights[fi]

    def layer_profile(self, layer: str) -> tuple[float, ...]:
        """1 層の因子別 profile (10 長)."""
        try:
            li = self.layer_names.index(layer)
        except ValueError as exc:
            raise KeyError(f"unknown memory layer: {layer!r}") from exc
        return tuple(row[li] for row in self.factor_weights)

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_weights": [list(row) for row in self.factor_weights],
            "layer_names": list(self.layer_names),
            "factor_names": list(THOUGHT_FACTORS),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThoughtFactorPerLayerChromosome:
        weights = data["factor_weights"]
        layer_names = tuple(
            data.get("layer_names", DEFAULT_MEMORY_LAYER_NAMES)
        )
        return cls(
            factor_weights=tuple(tuple(float(v) for v in row) for row in weights),
            layer_names=layer_names,
        )

    # ----- evolution operators -------------------------------------------

    def sample_neighborhood(
        self,
        rng: np.random.Generator,
        step_size: float = 0.1,
    ) -> ThoughtFactorPerLayerChromosome:
        """Gaussian noise を加えて [0, 1] にクリップ. mutation operator として使う."""
        arr = self.as_array()
        noise = rng.normal(0.0, step_size, size=arr.shape)
        return self.from_array(arr + noise, layer_names=self.layer_names)

    # ----- complexity ------------------------------------------------------

    def kolmogorov_proxy(self) -> int:
        """gzip 圧縮後 bytes 数. :class:`Genome3D` K と加法和を取るため
        独立 chromosome として閉じた K を返す."""
        payload = json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")
        return len(gzip.compress(payload))


# ---------------------------------------------------------------------------
# Crossover (free functions, Genome3D の crossover と命名整合)
# ---------------------------------------------------------------------------


def crossover_per_factor(
    parent_a: ThoughtFactorPerLayerChromosome,
    parent_b: ThoughtFactorPerLayerChromosome,
    rng: np.random.Generator,
) -> ThoughtFactorPerLayerChromosome:
    """因子ごとに 50/50 で親 A/B から行を選ぶ.

    結果: 「**ある因子は親 A の層別分布**, 別の因子は親 B の層別分布」を継承.
    """
    a = parent_a.as_array()
    b = parent_b.as_array()
    if a.shape != b.shape:
        raise ValueError(
            f"parent shape mismatch: {a.shape} vs {b.shape}"
        )
    if parent_a.layer_names != parent_b.layer_names:
        raise ValueError("parents must share layer_names")
    mask = rng.random(NUM_THOUGHT_FACTORS) < 0.5
    new = np.where(mask[:, None], a, b)
    return ThoughtFactorPerLayerChromosome.from_array(
        new, layer_names=parent_a.layer_names
    )


def crossover_per_layer(
    parent_a: ThoughtFactorPerLayerChromosome,
    parent_b: ThoughtFactorPerLayerChromosome,
    rng: np.random.Generator,
) -> ThoughtFactorPerLayerChromosome:
    """層ごとに 50/50 で親 A/B から列を選ぶ.

    結果: 「**working layer は親 A から, episodic layer は親 B から**」のような
    層別遺伝物質交換. cross-layer な再構成を促す.
    """
    a = parent_a.as_array()
    b = parent_b.as_array()
    if a.shape != b.shape:
        raise ValueError(
            f"parent shape mismatch: {a.shape} vs {b.shape}"
        )
    if parent_a.layer_names != parent_b.layer_names:
        raise ValueError("parents must share layer_names")
    n_layers = a.shape[1]
    mask = rng.random(n_layers) < 0.5
    new = np.where(mask[None, :], a, b)
    return ThoughtFactorPerLayerChromosome.from_array(
        new, layer_names=parent_a.layer_names
    )


__all__ = [
    "DEFAULT_MEMORY_LAYER_NAMES",
    "FACTOR_WEIGHT_HI",
    "FACTOR_WEIGHT_LO",
    "NUM_MEMORY_LAYERS",
    "NUM_THOUGHT_FACTORS",
    "ThoughtFactorPerLayerChromosome",
    "crossover_per_factor",
    "crossover_per_layer",
]
