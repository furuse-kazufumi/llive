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

from llive.perf.evolutionary.persona import PERSONA_ONTOLOGY, THOUGHT_FACTORS

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


def _canonical_persona_ids() -> tuple[str, ...]:
    """persona-index の **正準順**. 小 PoC ``poc_persona_indexed_genome`` と同一の
    ``sorted(PERSONA_ONTOLOGY.keys())``. index → persona id の写像を固定するため
    モジュール読み込み毎に同じ並びを返す."""
    return tuple(sorted(PERSONA_ONTOLOGY.keys()))


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
    persona_index : tuple[int, ...] | None
        **additive・default None** (2026-05-28 追加). 各思考因子に「担当ペルソナ」を
        1 名割り当てる **persona-indexed (モザイク)** メタデータ. len ==
        NUM_THOUGHT_FACTORS, 各値は :func:`_canonical_persona_ids` (=
        ``sorted(PERSONA_ONTOLOGY.keys())``) 上の index ∈ [0, P).

        小 PoC ``scripts/poc_persona_indexed_genome.py`` で「各因子の最適が別専門家に
        ある専門家委員会型 (モザイク) target」に対して効果ありと gate 済の方式を
        **後方互換に** 個体構造へ持ち込んだもの. ``None`` のとき現行挙動を完全維持し,
        連続 flat genome ベクトル (:meth:`as_array` / :meth:`as_flat`) には **一切
        含めない** (genome_version.assert_no_fourth_dim の 40-dim 不変条件を守る).
        decode は :meth:`persona_indexed_affinity` から別経路で取り出す.
    """

    factor_weights: tuple[tuple[float, ...], ...]
    layer_names: tuple[str, ...] = field(default=DEFAULT_MEMORY_LAYER_NAMES)
    persona_index: tuple[int, ...] | None = field(default=None)

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
        # persona_index は additive: None なら何もしない (現行挙動を完全維持).
        # 設定時のみ fail-closed 検証 (len + 各 index の値域).
        if self.persona_index is not None:
            n_personas = len(PERSONA_ONTOLOGY)
            raw = tuple(self.persona_index)
            if len(raw) != NUM_THOUGHT_FACTORS:
                raise ValueError(
                    f"persona_index must have {NUM_THOUGHT_FACTORS} entries "
                    f"(one per thought factor), got {len(raw)}"
                )
            coerced: list[int] = []
            for f, idx in enumerate(raw):
                # bool は int サブクラスだが persona index としては拒否 (fail-closed).
                if isinstance(idx, bool):
                    raise ValueError(
                        f"persona_index[{f}] must be an int, got bool {idx!r}"
                    )
                if not isinstance(idx, (int, np.integer)):
                    raise ValueError(
                        f"persona_index[{f}] must be an int, got {idx!r}"
                    )
                iv = int(idx)
                if not (0 <= iv < n_personas):
                    raise ValueError(
                        f"persona_index[{f}] = {iv} out of "
                        f"[0, {n_personas}) (n_personas={n_personas})"
                    )
                coerced.append(iv)
            # list / ndarray-int で渡されても frozen tuple-of-int に正規化 (hashable 維持).
            # 既に同一の plain int tuple なら setattr を省く (= 等価比較は plain tuple 同士).
            coerced_tuple = tuple(coerced)
            if not (
                isinstance(self.persona_index, tuple)
                and self.persona_index == coerced_tuple
            ):
                object.__setattr__(self, "persona_index", coerced_tuple)

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

    # ----- persona-indexed (mosaic) decode --------------------------------

    def persona_indexed_affinity(self) -> tuple[float, ...] | None:
        """persona-indexed (モザイク) decode.

        ``persona_index`` が設定されているとき, 各思考因子 f に対し
        「担当ペルソナ ``ids[persona_index[f]]`` の factor f への親和度」を返す
        (len == NUM_THOUGHT_FACTORS の phenotype). ``ids = sorted(
        PERSONA_ONTOLOGY.keys())`` (= :func:`_canonical_persona_ids`).

        小 PoC ``poc_persona_indexed_genome`` の ``decode_indexed`` と同一写像::

            affinity[f] = PERSONA_ONTOLOGY[ids[persona_index[f]]].factor_affinity[f]

        ``persona_index`` が None のとき None を返す (現行挙動を変えない signal).
        """
        if self.persona_index is None:
            return None
        ids = _canonical_persona_ids()
        return tuple(
            float(PERSONA_ONTOLOGY[ids[self.persona_index[f]]].factor_affinity[f])
            for f in range(NUM_THOUGHT_FACTORS)
        )

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "factor_weights": [list(row) for row in self.factor_weights],
            "layer_names": list(self.layer_names),
            "factor_names": list(THOUGHT_FACTORS),
        }
        # additive: persona_index は設定時のみ書き出す (None は省略しても to_dict 経由で
        # from_dict 復元時に default None になり round-trip 整合).
        if self.persona_index is not None:
            d["persona_index"] = list(self.persona_index)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThoughtFactorPerLayerChromosome:
        weights = data["factor_weights"]
        layer_names = tuple(
            data.get("layer_names", DEFAULT_MEMORY_LAYER_NAMES)
        )
        # backward-compat: 旧 snapshot に persona_index キーが無ければ None.
        raw_pi = data.get("persona_index")
        persona_index = (
            None if raw_pi is None else tuple(int(v) for v in raw_pi)
        )
        return cls(
            factor_weights=tuple(tuple(float(v) for v in row) for row in weights),
            layer_names=layer_names,
            persona_index=persona_index,
        )

    # ----- evolution operators -------------------------------------------

    def sample_neighborhood(
        self,
        rng: np.random.Generator,
        step_size: float = 0.1,
    ) -> ThoughtFactorPerLayerChromosome:
        """Gaussian noise を加えて [0, 1] にクリップ. mutation operator として使う.

        ``persona_index`` が None の個体は **現行挙動を完全維持** (連続 weights のみ摂動,
        persona_index は None のまま). 設定済の個体は ``mutate_persona_index`` で
        1 因子の担当ペルソナも別 persona に変える (小 PoC ``i_mut`` と同型) ので,
        モザイク indexed の進化が連続層と独立に進む.
        """
        arr = self.as_array()
        noise = rng.normal(0.0, step_size, size=arr.shape)
        child = self.from_array(arr + noise, layer_names=self.layer_names)
        if self.persona_index is None:
            return child  # additive: None 個体は persona_index を一切持たない.
        new_index = mutate_persona_index(self.persona_index, rng)
        return child.with_persona_index(new_index)

    # ----- persona-index helpers ------------------------------------------

    def with_persona_index(
        self, persona_index: tuple[int, ...] | None
    ) -> ThoughtFactorPerLayerChromosome:
        """連続 weights / layer_names を保ったまま ``persona_index`` だけ差し替えた
        新個体を返す (frozen なので copy). additive 採用用の便利メソッド."""
        return ThoughtFactorPerLayerChromosome(
            factor_weights=self.factor_weights,
            layer_names=self.layer_names,
            persona_index=persona_index,
        )

    # ----- complexity ------------------------------------------------------

    def kolmogorov_proxy(self) -> int:
        """gzip 圧縮後 bytes 数. :class:`Genome3D` K と加法和を取るため
        独立 chromosome として閉じた K を返す."""
        payload = json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")
        return len(gzip.compress(payload))


# ---------------------------------------------------------------------------
# persona-index operators (free functions)
# ---------------------------------------------------------------------------


def random_persona_index(rng: np.random.Generator) -> tuple[int, ...]:
    """各思考因子にランダムな担当ペルソナ index を割り当てた persona_index を返す.

    小 PoC ``i_init`` 相当. index 値域 = [0, len(PERSONA_ONTOLOGY)).
    """
    n_personas = len(PERSONA_ONTOLOGY)
    return tuple(int(i) for i in rng.integers(n_personas, size=NUM_THOUGHT_FACTORS))


def argmax_persona_index(target: np.ndarray | None = None) -> tuple[int, ...]:
    """各因子で affinity 最大のペルソナを割り当てた persona_index を返す.

    ``target`` 指定時は |affinity - target| 最小のペルソナを各因子で選ぶ (モザイク
    target への最良 indexed 充填). None のとき各因子で affinity 最大のペルソナ
    (= per-factor 専門家委員会の argmax envelope).
    """
    ids = _canonical_persona_ids()
    A = np.array(
        [list(PERSONA_ONTOLOGY[pid].factor_affinity) for pid in ids], dtype=float
    )
    if target is None:
        idx = A.argmax(axis=0)
    else:
        t = np.asarray(target, dtype=float)
        idx = np.abs(A - t[None, :]).argmin(axis=0)
    return tuple(int(i) for i in idx)


def mutate_persona_index(
    persona_index: tuple[int, ...],
    rng: np.random.Generator,
) -> tuple[int, ...]:
    """persona_index の 1 因子の担当ペルソナを別ペルソナへ変更する (小 PoC ``i_mut``).

    決定論 (rng 固定で再現). 長さ・値域は呼び出し元 (``__post_init__``) で fail-closed
    検証される.
    """
    n_personas = len(PERSONA_ONTOLOGY)
    new = list(persona_index)
    f = int(rng.integers(NUM_THOUGHT_FACTORS))
    new[f] = int(rng.integers(n_personas))
    return tuple(new)


def _crossover_persona_index(
    pi_a: tuple[int, ...] | None,
    pi_b: tuple[int, ...] | None,
    rng: np.random.Generator,
) -> tuple[int, ...] | None:
    """親の persona_index を因子ごと 50/50 で継承.

    - 両親とも None → None (**no-op = additive 不変条件**: persona_index 非使用の
      個体集団は従来通り何も増えない).
    - 両親とも設定 → 因子ごと独立 50/50 で A/B を選ぶ.
    - 片方だけ設定 → 設定側をそのまま継承 (None からは合成しない).
    """
    if pi_a is None and pi_b is None:
        return None
    if pi_a is None:
        return pi_b
    if pi_b is None:
        return pi_a
    return tuple(
        int(pi_a[f]) if rng.random() < 0.5 else int(pi_b[f])
        for f in range(NUM_THOUGHT_FACTORS)
    )


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
    ``persona_index`` も同様に因子ごと 50/50 継承 (両親 None なら None のまま = no-op).
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
    persona_index = _crossover_persona_index(
        parent_a.persona_index, parent_b.persona_index, rng
    )
    return ThoughtFactorPerLayerChromosome.from_array(
        new, layer_names=parent_a.layer_names
    ).with_persona_index(persona_index)


def crossover_per_layer(
    parent_a: ThoughtFactorPerLayerChromosome,
    parent_b: ThoughtFactorPerLayerChromosome,
    rng: np.random.Generator,
) -> ThoughtFactorPerLayerChromosome:
    """層ごとに 50/50 で親 A/B から列を選ぶ.

    結果: 「**working layer は親 A から, episodic layer は親 B から**」のような
    層別遺伝物質交換. cross-layer な再構成を促す.
    ``persona_index`` は層概念を持たない離散メタデータなので因子ごと 50/50 継承
    (両親 None なら None のまま = no-op).
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
    persona_index = _crossover_persona_index(
        parent_a.persona_index, parent_b.persona_index, rng
    )
    return ThoughtFactorPerLayerChromosome.from_array(
        new, layer_names=parent_a.layer_names
    ).with_persona_index(persona_index)


__all__ = [
    "DEFAULT_MEMORY_LAYER_NAMES",
    "FACTOR_WEIGHT_HI",
    "FACTOR_WEIGHT_LO",
    "NUM_MEMORY_LAYERS",
    "NUM_THOUGHT_FACTORS",
    "ThoughtFactorPerLayerChromosome",
    "argmax_persona_index",
    "crossover_per_factor",
    "crossover_per_layer",
    "mutate_persona_index",
    "random_persona_index",
]
