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

from dataclasses import dataclass

import numpy as np

from llive.benchmark.runtime_metadata import collect_runtime_metadata
from llive.perf.evolutionary.fitness import Fitness
from llive.perf.evolutionary.individual import FitnessReport
from llive.perf.evolutionary.llive_variant import THOUGHT_FACTOR_LABELS
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


__all__ = [
    "LLM_WEAKNESS_PRESSURES",
    "ProxyPressure",
    "make_pressure_fitness",
]
