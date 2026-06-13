# SPDX-License-Identifier: Apache-2.0
"""lldarwin v2 — 確定方策 S1「選択核」の合成プリセット (Phase 1).

設計正本: fullsense ``docs/research/lldarwin_v2_poc_marathon_2026_05_26.md`` §「✅ 決定した
方策」S1 と ``docs/vision/OPEN_ENDED_EVOLUTION_REQUIREMENTS.md`` §1.1-1.3 / QD-3。

overnight PoC マラソン (自己PoC 6本 + Agent A/B/C + Perplexity が独立収束) で確定した
**選択核 S1** を、**新規アルゴリズムを発明せず**既存部品を合成・配線する薄いプリセット。

確定 S1 = ε-lexicase + novelty (z-score 標準化) + minimal-criterion gate
         + MAP-Elites QD archive 連携 + 中立貯蔵庫 (LineageReservoir) フック

このモジュールが直接合成するのは **選択器そのもの** (= ``MultiPressureSelector``) の
確定既定構成だけ:

* **ε-lexicase** — :class:`~llive.perf.evolutionary.mating.LexicaseSelection` (既存) を
  ``MultiPressureSelector`` 経由で再利用。集約せず軸ごとに specialist を保存 (SEL-3)。
* **novelty (z-score 標準化)** — ``MultiPressureSelector.use_novelty=True``。k-NN 過去
  archive 距離を集団内 z-score 化して ``breakdown['novelty']`` に書き lexicase case 化
  (STD-1 / SEL-1)。Agent A sweep で「標準化が QD 被覆を桁で拡大」を実証した核 (STD-1)。
* **minimal-criterion gate** — :class:`~llive.perf.evolutionary.lldarwin.MinimalCriterionGate`
  (既存) を構成フラグから組み立てて注入 (SEL-4)。全員 fail なら無視で全滅回避。

**QD archive 連携 (MAP-Elites)** と **中立貯蔵庫 (LineageReservoir)** は選択器の内側でなく
**ランナー / EvolutionLoop の hook レベル**で配線される (それぞれ ``MAPElitesGrid`` と
``on_population_bred`` hook)。本モジュールは選択器を合成しつつ、ランナーが解釈する
**構成フラグ** (:class:`LLDarwinV2Config`) でそれらの opt-in 既定値を 1 箇所に集約する
(= 「確定既定構成を 1 つの合成エントリにまとめる」要件)。

.. note:: HONEST DISCLOSURE (配線状況, [[feedback_implementation_status_record]])

    * **配線済 (本 Phase 1)**: ε-lexicase + novelty(z-score) + minimal-criterion を
      ``MultiPressureSelector`` の確定既定として 1 関数で構築。ランナーの
      ``--selection lldarwin-v2`` で QD archive (既存) + reservoir (既存) も既定 on に。
    * **配線済 (Phase 1-③)**: **適応難易度 (条件カリキュラム)** =
      :class:`~llive.perf.evolutionary.pressures.AdaptivePercentileGate` を gate に既定
      注入 (``adaptive_difficulty=True``)。集団分位 (30-60% 点) で minimal-criterion を
      毎世代自動上昇させ固定ものさしの飽和を回避 (PoC#1/#2: 適応難易度は勾配維持・
      novelty は多様性維持で **相補・両方必須**)。``MultiPressureSelector`` が gate の
      ``update`` を世代ごとに呼ぶ。
    * **構成フラグのみ (未配線 = ランナー/loop 側責務)**: ``map_elites_archive`` /
      ``lineage_reservoir`` フラグは「この構成で何を on にすべきか」を表明するだけで、
      実際の MAP-Elites submit と reservoir re-inject の配線は本モジュールの外
      (``run_persona_evolution`` の ``lineage_reservoir`` 引数 / 既存 QD 経路) に委ねる。
    * **配線済 (Phase 1-①)**: **factor-subspace QD (QD-3, PoC#6)** =
      :class:`~llive.perf.evolutionary.quality_diversity.FactorSubspaceNovelty` を全体
      novelty にブレンドし意味次元 (思考因子) の多様性を個別保護 (``factor_subspace_qd=True``,
      weight 既定 0.5)。``factor_extractor`` は循環 import 回避のため build 時に
      ``pressures.factor_vector`` を selector へ注入する。

    既存のデフォルト挙動 (``--selection default`` = Tournament) は一切変更しない。本構成は
    完全に **opt-in**。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from llive.perf.evolutionary.lldarwin import (
    MinimalCriterionGate,
    MultiPressureSelector,
)
from llive.perf.evolutionary.pressures import AdaptivePercentileGate, factor_vector

#: 確定既定構成の minimal-criterion 既定軸: なし (= criteria 自動抽出 + 全軸動的)。
#: gate を有効化するときの既定しきい値 (proxy pressure 軸の値域 [0,1] を想定)。
DEFAULT_MINIMAL_CRITERION: float = 0.0


@dataclass
class LLDarwinV2Config:
    """lldarwin v2 確定既定構成 (S1 選択核) の 1 箇所集約コンフィグ.

    overnight マラソンで確定した S1 を **既定値で表現**する。全フィールドは PoC で
    裏付けられた値を既定にしているが、**この構成を使うこと自体が opt-in** (既定の
    Tournament 選択は本コンフィグを通らない)。

    選択器に直接効くフィールド (本モジュールが合成):

    epsilon:
        ε-lexicase の許容範囲 (同点扱い)。PoC / Stage1 既定 0.01。
    use_novelty:
        novelty pressure (k-NN 過去 archive 距離の z-score) を lexicase case に加えるか。
        確定 S1 の核 (STD-1)。既定 True。
    novelty_k:
        novelty の k-NN 近傍数。既定 5 (Stage1 既定)。
    minimal_criterion:
        ``minimal_criterion_axes`` の各軸に課す最低基準しきい値。
        gate を組み立てるときのみ使用。既定 :data:`DEFAULT_MINIMAL_CRITERION`。
    minimal_criterion_axes:
        gate を課す breakdown 軸名の tuple。空なら gate 無効 (= ``gate=None``)。
        既定は空 (= 自動抽出 + lexicase のみ。gate は明示 opt-in で過剰拘束を避ける)。
    higher_is_better:
        各軸とも大きいほど良いか。既定 True。
    adaptive_difficulty:
        適応難易度 (条件カリキュラム) を gate に使うか。True なら
        :class:`~llive.perf.evolutionary.pressures.AdaptivePercentileGate` を組み立て、
        ``minimal_criterion_axes`` (空なら集団から動的抽出) に集団分位 floor を毎世代
        課す。確定 S1 の核 (適応難易度×novelty は相補で両方必須)。既定 True。
        ``adaptive_difficulty=True`` のとき ``minimal_criterion`` / 固定
        ``MinimalCriterionGate`` は使わない (gate は adaptive に置き換わる)。
    difficulty_percentile:
        適応難易度の floor に使う集団分位 [0, 100]。marathon レシピ「集団 30-60 % 点」。
        既定 40。
    difficulty_ratchet:
        floor を単調非減少にするか (飽和回避)。既定 True。
    factor_subspace_qd:
        factor-subspace QD (QD-3, PoC#6) = factor 部分空間 novelty を全体 novelty に
        ブレンドし意味次元の多様性を個別保護するか。既定 True (S1 完全構成)。build 時に
        ``factor_extractor`` = ``pressures.factor_vector`` を selector へ注入する。
    factor_subspace_weight:
        factor-subspace novelty のブレンド比 [0, 1]。PoC#6 既定 0.5。

    ランナー / loop 側が解釈する構成フラグ (本モジュールは選択器に注入しない):

    lineage_reservoir:
        中立貯蔵庫 (LineageReservoir) を ``on_population_bred`` に配線すべきか。
        確定 S1 で「系統多様性は中立貯蔵庫で別途確保」(res256 で uniq_lineages 1→32)。
        既定 True。**配線はランナー責務** (``run_persona_evolution(lineage_reservoir=...)``)。
    reinject_interval:
        貯蔵庫の再投入世代間隔 (1=毎世代)。既定 1。ランナーへ受け渡す値。
    map_elites_archive:
        MAP-Elites QD archive を成果アーカイブとして連携すべきか (QD-1/QD-2)。
        既定 True。**submit 配線は既存 QD 経路責務** (本モジュールは表明のみ)。
    """

    # ---- selector に直接効く (本モジュールが合成) ----
    epsilon: float = 0.01
    use_novelty: bool = True
    novelty_k: int = 5
    minimal_criterion: float = DEFAULT_MINIMAL_CRITERION
    minimal_criterion_axes: tuple[str, ...] = ()
    higher_is_better: bool = True
    adaptive_difficulty: bool = True
    difficulty_percentile: float = 40.0
    difficulty_ratchet: bool = True
    factor_subspace_qd: bool = True
    factor_subspace_weight: float = 0.5

    # ---- ランナー / loop hook が解釈する構成フラグ (selector には注入しない) ----
    lineage_reservoir: bool = True
    reinject_interval: int = 1
    map_elites_archive: bool = True

    # ---- 任意上書き ----
    criteria: tuple[str, ...] = field(default_factory=tuple)
    """lexicase の pressure 軸を明示指定。空なら集団 breakdown から自動抽出 (既定)。"""

    def __post_init__(self) -> None:
        if self.epsilon < 0:
            raise ValueError(f"epsilon must be >= 0, got {self.epsilon}")
        if self.novelty_k < 1:
            raise ValueError(f"novelty_k must be >= 1, got {self.novelty_k}")
        if self.reinject_interval < 1:
            raise ValueError(
                f"reinject_interval must be >= 1, got {self.reinject_interval}"
            )
        if not (0.0 <= self.difficulty_percentile <= 100.0):
            raise ValueError(
                f"difficulty_percentile must be in [0, 100], got {self.difficulty_percentile}"
            )
        if not (0.0 <= self.factor_subspace_weight <= 1.0):
            raise ValueError(
                f"factor_subspace_weight must be in [0, 1], got {self.factor_subspace_weight}"
            )

    # -- gate 合成 ---------------------------------------------------------

    def build_gate(self) -> MinimalCriterionGate | AdaptivePercentileGate | None:
        """確定 S1 の gate を組み立てる.

        * ``adaptive_difficulty=True`` (既定): 適応難易度
          :class:`~llive.perf.evolutionary.pressures.AdaptivePercentileGate` を返す。
          ``minimal_criterion_axes`` が空なら集団 breakdown から動的抽出した全軸へ
          集団分位 floor を課す (条件カリキュラム)。
        * ``adaptive_difficulty=False`` かつ ``minimal_criterion_axes`` 指定:
          固定 :class:`~llive.perf.evolutionary.lldarwin.MinimalCriterionGate`。
        * どちらでもない (固定 gate で軸未指定): ``None`` (gate 無効)。
        """
        if self.adaptive_difficulty:
            return AdaptivePercentileGate(
                percentile=self.difficulty_percentile,
                axes=self.minimal_criterion_axes,
                higher_is_better=self.higher_is_better,
                ratchet=self.difficulty_ratchet,
            )
        if not self.minimal_criterion_axes:
            return None
        return MinimalCriterionGate(
            criteria={axis: self.minimal_criterion for axis in self.minimal_criterion_axes},
            higher_is_better=self.higher_is_better,
        )


def build_lldarwin_v2_selector(
    config: LLDarwinV2Config | None = None,
) -> MultiPressureSelector:
    """lldarwin v2 確定既定構成の **選択器** を 1 つ合成して返す (S1 選択核).

    = ε-lexicase + novelty(z-score 標準化, 既定 on) + minimal-criterion gate
    (``minimal_criterion_axes`` 指定時)。新規アルゴリズムは作らず、既存
    :class:`~llive.perf.evolutionary.lldarwin.MultiPressureSelector` /
    :class:`~llive.perf.evolutionary.mating.LexicaseSelection` /
    :class:`~llive.perf.evolutionary.lldarwin.MinimalCriterionGate` を合成・配線する。

    ``EvolutionLoop.selection`` または ``run_persona_evolution(selection=...)`` に
    そのまま注入できる callable shape (``(Population, rng) -> Individual``)。

    Parameters
    ----------
    config:
        :class:`LLDarwinV2Config`。None なら確定既定 (novelty on / gate なし /
        epsilon 0.01)。

    Returns
    -------
    MultiPressureSelector
        確定既定構成で初期化済の選択器。
    """
    cfg = config or LLDarwinV2Config()
    # factor-subspace QD (QD-3): factor_extractor を循環 import 回避で build 時に注入。
    factor_extractor = factor_vector if cfg.factor_subspace_qd else None
    weight = cfg.factor_subspace_weight if cfg.factor_subspace_qd else 0.0
    return MultiPressureSelector(
        criteria=cfg.criteria,
        epsilon=cfg.epsilon,
        gate=cfg.build_gate(),
        higher_is_better=cfg.higher_is_better,
        use_novelty=cfg.use_novelty,
        novelty_k=cfg.novelty_k,
        factor_subspace_weight=weight,
        factor_extractor=factor_extractor,
    )


__all__ = [
    "DEFAULT_MINIMAL_CRITERION",
    "LLDarwinV2Config",
    "build_lldarwin_v2_selector",
]
