# SPDX-License-Identifier: Apache-2.0
"""lldarwin Stage2 (proxy 部分) — LLM 苦手軸の Pressure plugin カタログ.

設計正本: fullsense ``docs/vision/LLDARWIN_DESIGN.md`` §3。LLM が現実に弱く、かつ
測定可能な軸 (typo / polysemy / multistep / calibration / context) を **独立した
選択圧 (pressure)** として表現し、ε-lexicase で集約せず淘汰する (差別化軸 DIFF-1)。

各 :class:`ProxyPressure` は個体の思考因子 (10 dims) のうち、その LLM 弱点に関連する
因子群を case 群として返す。lldarwin の :class:`~llive.perf.evolutionary.lldarwin.MultiPressureSelector`
が breakdown からこれらを pressure として拾い、軸ごとに specialist を保存する。

.. warning:: HONEST DISCLOSURE (設計 §7 / §7.1)

    これは **proxy** である。個体は実 LLM でなく llive genome (Genome3D) なので、
    本 pressure は「genome がその弱点に関連する思考因子をどれだけ備えるか」という
    **振る舞い代理** を測るに過ぎない。**production の LLM 能力を測るものではない**
    (実 LLM/VLM 評価は Stage2 後半 = 個体→実 LLM 写像 + on-prem 推論が前提)。
    本 module の目的は **mechanism feasibility** — 「複数の独立した苦手軸に同時に
    選択圧をかけ、軸ごとの specialist を維持できるか」を proxy で検証すること。
    Goodhart リスク (proxy をハックする表面戦略) を受容済みの限界として明記する。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from llive.benchmark.runtime_metadata import collect_runtime_metadata
from llive.perf.evolutionary.fitness import Fitness
from llive.perf.evolutionary.individual import FitnessReport
from llive.perf.evolutionary.lldarwin import (
    DEFAULT_EXCLUDED_CRITERIA,
    _infer_numeric_criteria,
    _numeric_breakdown,
)
from llive.perf.evolutionary.llive_variant import THOUGHT_FACTOR_LABELS
from llive.perf.evolutionary.population import Population
from llive.perf.evolutionary.thought_factor_per_layer import NUM_THOUGHT_FACTORS

_LABEL_IDX: dict[str, int] = {label: i for i, label in enumerate(THOUGHT_FACTOR_LABELS)}


def _factor_vector(genome: object) -> np.ndarray:
    """個体の 10-dim 思考因子ベクトルを返す.

    * :class:`Genome3D` → ``c_factors`` を層平均した 10-vector。
    * flat ``Genome`` → ``as_array()`` の dims 0..9。
    """
    c_factors = getattr(genome, "c_factors", None)
    if c_factors is not None:
        matrix = np.asarray(c_factors.as_array(), dtype=np.float64)  # (10, n_layers)
        return matrix.mean(axis=1)
    as_array = getattr(genome, "as_array", None)
    if callable(as_array):
        return np.asarray(as_array(), dtype=np.float64)[:NUM_THOUGHT_FACTORS]
    raise TypeError(f"unsupported genome type for pressure proxy: {type(genome).__name__}")


def factor_vector(genome: object) -> np.ndarray:
    """個体 genome の思考因子ベクトル（公開 API; factor-subspace QD で使う）.

    :class:`Genome3D` → ``c_factors`` を層平均した 10-vector / flat ``Genome`` →
    ``as_array()`` の dims 0..9。
    :class:`~llive.perf.evolutionary.quality_diversity.FactorSubspaceNovelty` の
    ``factor_extractor`` に注入する（lldarwin_v2 経由）。循環 import を避けるため
    selector でなく合成側 (lldarwin_v2) がこの関数を渡す。
    """
    return _factor_vector(genome)


@dataclass(frozen=True)
class ProxyPressure:
    """1 つの LLM 苦手軸の proxy pressure (設計 §3 の ``Pressure`` インターフェース).

    Attributes
    ----------
    name:
        pressure 名 (breakdown キーの接頭辞)。
    factors:
        この弱点に関連する思考因子ラベル群 (:data:`THOUGHT_FACTOR_LABELS` のキー)。
        各因子が 1 つの case になる (ε-lexicase が軸ごとに specialist を保存)。
    minimal_criterion:
        :class:`~llive.perf.evolutionary.lldarwin.MinimalCriterionGate` 用の最低基準
        (None なら gate 無し)。
    is_proxy:
        常に True (本 module は proxy のみ。実評価は Stage2 後半)。
    """

    name: str
    factors: tuple[str, ...]
    minimal_criterion: float | None = None
    is_proxy: bool = True

    def __post_init__(self) -> None:
        unknown = [f for f in self.factors if f not in _LABEL_IDX]
        if unknown:
            raise ValueError(f"pressure {self.name!r} references unknown factors: {unknown}")

    def factor_indices(self) -> tuple[int, ...]:
        return tuple(_LABEL_IDX[f] for f in self.factors)

    def evaluate(self, genome: object) -> dict[str, float]:
        """関連思考因子の値を case として返す ``{case_key: score}``.

        case_key = ``"<name>::<factor>"``。値 = genome のその因子値 (層平均, [0,1])。
        弱点軸ごとに独立した case を与え、ある軸に強い specialist を lexicase が保存する。
        """
        vec = _factor_vector(genome)
        return {
            f"{self.name}::{factor}": float(np.clip(vec[idx], 0.0, 1.0))
            for factor, idx in zip(self.factors, self.factor_indices())
        }


#: LLM 苦手軸カタログ (設計 §3 の proxy 可能な 5 軸)。各軸 → LLM 弱点に関連する思考因子。
#: typo=ノイズ耐性(整合+現実接続+不確実性) / polysemy=多義語(多視点+整合+現実接続) /
#: multistep=多段推論(構造化+閉ループ+自己拡張) / calibration=信頼度(不確実性+来歴) /
#: context=無関係文脈耐性(整合+来歴+再構成)。
LLM_WEAKNESS_PRESSURES: tuple[ProxyPressure, ...] = (
    ProxyPressure(
        "typo_robustness",
        ("factor_consistency", "factor_reality_link", "factor_uncertainty"),
    ),
    ProxyPressure(
        "polysemy_wsd",
        ("factor_multiview", "factor_consistency", "factor_reality_link"),
    ),
    ProxyPressure(
        "multistep_robustness",
        ("factor_structurize", "factor_closed_loop", "factor_self_extend"),
    ),
    ProxyPressure(
        "calibration",
        ("factor_uncertainty", "factor_provenance"),
    ),
    ProxyPressure(
        "context_management",
        ("factor_consistency", "factor_provenance", "factor_recompose"),
    ),
)


def make_pressure_fitness(
    pressures: tuple[ProxyPressure, ...] = LLM_WEAKNESS_PRESSURES,
) -> Fitness:
    """LLM 苦手軸 proxy の多目的 :data:`Fitness` を作る.

    ``breakdown`` に各 pressure の case スコア (``<name>::<factor>``) を入れる。これが
    lldarwin の ε-lexicase が淘汰する pressure profile (集約しない多目的ベクトル)。
    ``score`` は全 case 平均 (単一目的 consumer 用。lexicase は使わない)。

    HONEST: proxy のみ。個体は実 LLM でなく genome なので mechanism feasibility 検証用。
    """
    if not pressures:
        raise ValueError("pressures must be non-empty")
    pressure_list = list(pressures)

    def fitness(genome: object) -> FitnessReport:  # noqa: ANN001
        breakdown: dict[str, float] = {}
        for pressure in pressure_list:
            breakdown.update(pressure.evaluate(genome))
        score = float(np.mean(list(breakdown.values()))) if breakdown else 0.0
        return FitnessReport(
            score=float(max(0.0, min(1.0, score))),
            breakdown=breakdown,
            runtime_metadata=dict(collect_runtime_metadata()),
            n_samples=1,
            notes=(
                "PROXY LLM-weakness pressures (NOT real LLM evaluation). Each case = "
                "genome's thought-factor value associated with an LLM weakness axis "
                f"({', '.join(p.name for p in pressure_list)}). Mechanism feasibility "
                "only; production LLM capability requires Stage2 real eval."
            ),
        )

    return fitness


# ---------------------------------------------------------------------------
# Phase 1-③ — 適応難易度 (条件カリキュラム) = パーセンタイル動的 minimal-criterion
# ---------------------------------------------------------------------------


@dataclass
class AdaptivePercentileGate:
    """パーセンタイル動的 minimal-criterion (適応難易度 / 条件カリキュラム).

    設計正本: fullsense ``docs/research/lldarwin_v2_poc_marathon_2026_05_26.md``
    §「飽和回避レシピ」① + 自己 PoC #1/#2。

    各 pressure 軸の最低基準 (floor) を毎世代 **集団のその軸スコア分布の指定
    パーセンタイル** に設定する。固定スカラー quiz が飽和して選択圧を失う 12h 病理
    (best=1.0 飽和 → 遺伝的浮動 → monoculture) に対し、集団が改善すると floor も
    追従して上がるため「ものさし」が飽和しない。

    * **PoC #1**: 固定難易度は能力 0.627 で停滞 / 適応難易度 (集団 60 分位) は 0.952。
    * **PoC #2**: 適応難易度 (勾配維持) と novelty (多様性維持) は **相補で両方必須**
      (適応難易度×novelty で能力 0.881・多様性 0.316 を両立)。

    :class:`~llive.perf.evolutionary.lldarwin.MinimalCriterionGate` と同じ
    ``passes(breakdown) -> bool`` インターフェースを持つので
    :class:`~llive.perf.evolutionary.lldarwin.MultiPressureSelector` が gate として
    そのまま扱える。加えて ``update(population)`` を実装し、selector が世代ごとに 1 回
    呼んで floor を再計算する (duck typing; ``MinimalCriterionGate`` は ``update`` を
    持たないので影響を受けない = 後方互換)。全員 fail の世代は selector が gate を
    無視するので **全滅は構造的に回避** される (要件 SEL-4)。

    Attributes
    ----------
    percentile:
        floor に使う集団分位 [0, 100]。marathon レシピは「集団 30-60 % 点」。既定 40。
        大きいほど厳しい (上位ほど生存)。
    axes:
        floor を課す breakdown 軸名。空なら集団 breakdown から数値キーを動的抽出
        (``exclude`` のキーは除外)。
    higher_is_better:
        各軸とも大きいほど良いか。既定 True。
    ratchet:
        True なら floor は単調非減少 (higher_is_better では上昇のみ)。集団が一時的に
        退化しても基準が緩まない = 「飽和しない」(レシピ①)。False なら毎世代分位で
        上書き (集団追従だが退化時に緩む)。既定 True。
    exclude:
        ``axes`` 自動抽出時に除外するキー。既定 :data:`DEFAULT_EXCLUDED_CRITERIA`
        (``factor_score`` = argmax / ``nearest_persona_idx`` = カテゴリ index)。
    """

    percentile: float = 40.0
    axes: tuple[str, ...] = ()
    higher_is_better: bool = True
    ratchet: bool = True
    exclude: frozenset[str] = DEFAULT_EXCLUDED_CRITERIA
    _thresholds: dict[str, float] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _sig: tuple[int, tuple[str, ...]] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not (0.0 <= self.percentile <= 100.0):
            raise ValueError(
                f"percentile must be in [0, 100], got {self.percentile}"
            )

    @property
    def thresholds(self) -> dict[str, float]:
        """現在の floor (観測 / 監査可能性用)。update 前は空 = 全通過。"""
        return dict(self._thresholds)

    def update(self, population: Population) -> None:
        """集団からこの世代の floor を再計算する (世代ごとに 1 回だけ).

        selector が ``__call__`` のたびに呼んでも、population の (generation, ids)
        署名で 1 世代 1 回だけ計算する。``ratchet`` のとき floor は前回値と比較して
        単調側にのみ更新する。
        """
        individuals = list(population.individuals)
        ids = tuple(ind.individual_id for ind in individuals)
        sig = (int(getattr(population, "generation", 0)), ids)
        if sig == self._sig:
            return
        self._sig = sig

        axes = self.axes or _infer_numeric_criteria(individuals, self.exclude)
        for axis in axes:
            vals = [
                bd[axis]
                for ind in individuals
                if axis in (bd := _numeric_breakdown(ind))
            ]
            if not vals:
                continue
            pct = float(np.percentile(np.asarray(vals, dtype=float), self.percentile))
            old = self._thresholds.get(axis)
            if old is None or not self.ratchet:
                self._thresholds[axis] = pct
            elif self.higher_is_better:
                self._thresholds[axis] = max(old, pct)  # 改善で上昇のみ
            else:
                self._thresholds[axis] = min(old, pct)

    def passes(self, breakdown: dict[str, float]) -> bool:
        """``MinimalCriterionGate.passes`` 互換。floor 未確定 (update 前) は全通過."""
        for axis, threshold in self._thresholds.items():
            if axis not in breakdown:
                continue
            value = breakdown[axis]
            if self.higher_is_better and value < threshold:
                return False
            if not self.higher_is_better and value > threshold:
                return False
        return True


__all__ = [
    "LLM_WEAKNESS_PRESSURES",
    "AdaptivePercentileGate",
    "ProxyPressure",
    "factor_vector",
    "make_pressure_fitness",
]
