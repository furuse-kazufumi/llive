# SPDX-License-Identifier: Apache-2.0
"""llive variant evolution (llive v0.C Phase 1 skeleton).

「1 llive = 1 個体」と見て集団化する. v0.B の hyperparameter 進化を **構成
全体** に拡張. 完全に同時並列でなくても serial/segmented で世代が回ることを
最重要視 (ユーザー指示 2026-05-21).

公開 API:

* :data:`LIVE_VARIANT_GENOME_BOUNDS` — 19 dim bounds
* :data:`LIVE_VARIANT_GENOME_LABELS` — 19 dim labels
* :class:`LlivVariantConfig` — Genome を可読 dict 化したもの
* :class:`LlivVariantBuilder` — Genome → LlivVariantConfig
* :func:`mock_variant_fitness_factory` — 構成評価 (5 + 3 = 8 軸合成)

実 llive instance の spawn は Phase 2 で実装 (credential / 環境準備後).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from llive.benchmark.runtime_metadata import collect_runtime_metadata
from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.individual import FitnessReport


# -------------------- Genome layout (LV-GEN-01〜05) --------------------

THOUGHT_FACTOR_LABELS: tuple[str, ...] = (
    "factor_structurize",   # 構造化
    "factor_recompose",     # 再構成
    "factor_closed_loop",   # 閉ループ
    "factor_self_extend",   # 自己拡張
    "factor_uncertainty",   # 不確実性
    "factor_exploration",   # 探索
    "factor_consistency",   # 整合
    "factor_provenance",    # 来歴
    "factor_multiview",     # 多視点
    "factor_reality_link",  # 現実接続
)

MEMORY_TIER_LABELS: tuple[str, ...] = (
    "semantic_threshold",   # 0.1 - 0.9
    "episodic_threshold",   # 0.1 - 0.9
    "structural_decay",     # 0.5 - 1.0
)

BACKEND_LABELS: tuple[str, ...] = ("backend_id",)

SAMPLER_LABELS: tuple[str, ...] = (
    "temperature",          # 0.0 - 1.5
    "top_p",                # 0.5 - 1.0
    "kv_quant_id",          # 0.0 - 2.99
)

PROACTIVE_LABELS: tuple[str, ...] = (
    "gift_value_threshold", # 0.3 - 0.9
    "cooldown_minutes",     # 5 - 120
)

LIVE_VARIANT_GENOME_LABELS: tuple[str, ...] = (
    *THOUGHT_FACTOR_LABELS,
    *MEMORY_TIER_LABELS,
    *BACKEND_LABELS,
    *SAMPLER_LABELS,
    *PROACTIVE_LABELS,
)

assert len(LIVE_VARIANT_GENOME_LABELS) == 19, "v0.C は 19 dim を想定"

LIVE_VARIANT_GENOME_BOUNDS = GenomeBounds(
    lower=(
        # 思考因子 weight (10 dim)
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        # memory tier (3 dim)
        0.1, 0.1, 0.5,
        # backend (1 dim)
        0.0,
        # sampler (3 dim)
        0.0, 0.5, 0.0,
        # proactive (2 dim)
        0.3, 5.0,
    ),
    upper=(
        # 思考因子 weight
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
        # memory tier
        0.9, 0.9, 1.0,
        # backend
        4.99,
        # sampler
        1.5, 1.0, 2.99,
        # proactive
        0.9, 120.0,
    ),
)

_BACKEND_NAMES = ("mock", "openai", "anthropic", "mamba", "rwkv")
_KV_QUANT_NAMES = ("f16", "q8_0", "q4_0")


# v0.C は 19 dim を 5 chromosome に分ける. SegmentCrossover に渡す.
LIVE_VARIANT_SEGMENTS: tuple[tuple[int, int], ...] = (
    (0, 10),    # 思考因子 weight (10 dim)
    (10, 13),   # memory tier (3 dim)
    (13, 14),   # backend (1 dim)
    (14, 17),   # sampler (3 dim)
    (17, 19),   # proactive (2 dim)
)


# -------------------- Config dataclass --------------------


@dataclass(frozen=True)
class LlivVariantConfig:
    """LlivVariantGenome を可読化した dict-like 構成. Phase 2 で実 instance に
    渡される設計.
    """

    thought_factor_weights: dict[str, float]
    memory_thresholds: dict[str, float]
    backend_name: str
    sampler: dict[str, Any]
    proactive: dict[str, Any]
    variant_id: str = ""
    data_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "thought_factor_weights": dict(self.thought_factor_weights),
            "memory_thresholds": dict(self.memory_thresholds),
            "backend_name": self.backend_name,
            "sampler": dict(self.sampler),
            "proactive": dict(self.proactive),
            "variant_id": self.variant_id,
            "data_dir": self.data_dir,
        }


# -------------------- Builder --------------------


@dataclass
class LlivVariantBuilder:
    """Genome → LlivVariantConfig.

    Phase 1: dict 化のみ.
    Phase 2: ``build_instance(config)`` で実 LlivKernel を返す (subprocess /
    in-process 2 transport).
    """

    data_dir_root: str = "/tmp/llive-variants"

    def build_config(
        self,
        genome: Genome,
        *,
        variant_id: str = "",
    ) -> LlivVariantConfig:
        values = genome.as_array()
        if values.shape != (19,):
            raise ValueError(f"expected 19-dim genome, got {values.shape}")
        # ----- 思考因子 weight -----
        factor_weights = {
            label: float(values[i]) for i, label in enumerate(THOUGHT_FACTOR_LABELS)
        }
        # ----- memory tier -----
        memory_thresholds = {
            "semantic_threshold": float(values[10]),
            "episodic_threshold": float(values[11]),
            "structural_decay": float(values[12]),
        }
        # ----- backend -----
        backend_idx = int(max(0, min(len(_BACKEND_NAMES) - 1, values[13])))
        backend_name = _BACKEND_NAMES[backend_idx]
        # ----- sampler -----
        kv_idx = int(max(0, min(len(_KV_QUANT_NAMES) - 1, values[16])))
        sampler = {
            "temperature": float(values[14]),
            "top_p": float(values[15]),
            "kv_quant": _KV_QUANT_NAMES[kv_idx],
        }
        # ----- proactive -----
        proactive = {
            "gift_value_threshold": float(values[17]),
            "cooldown_minutes": float(values[18]),
        }
        data_dir = f"{self.data_dir_root}/{variant_id or 'noid'}"
        return LlivVariantConfig(
            thought_factor_weights=factor_weights,
            memory_thresholds=memory_thresholds,
            backend_name=backend_name,
            sampler=sampler,
            proactive=proactive,
            variant_id=variant_id,
            data_dir=data_dir,
        )


# -------------------- mock fitness --------------------


# 5 + 3 = 8 軸. weight default 均等.
DEFAULT_VARIANT_WEIGHTS: dict[str, float] = {
    # 5 共通軸
    "latency": 0.15,
    "quality": 0.15,
    "stability": 0.10,
    "safety": 0.10,
    "honesty": 0.10,
    # 3 派生固有軸
    "factor_coverage": 0.15,      # 因子 weight の dispersion (0 偏り→低)
    "memory_efficiency": 0.15,    # threshold が極端でない (中庸が良い)
    "proactive_balance": 0.10,    # gift_threshold と cooldown の整合性
}


@dataclass(frozen=True)
class MockVariantFitnessConfig:
    """1 派生評価の設定 (mock)."""

    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_VARIANT_WEIGHTS))
    # 各派生の評価所要時間 (mock では 0 だが将来 sleep ベースで現実時間 simulate 可)
    eval_delay_sec: float = 0.0


def _measure_factor_coverage(weights: dict[str, float]) -> float:
    """10 因子の weight が全て低すぎず偏らないなら高い score.

    すべて 0 だと 0, 全て 1 だと 1, 一つだけ大は低い.
    metric: 1 - std(weights) で「均整」を見つつ, mean が低ければ全体 score も低い.
    """
    arr = np.asarray(list(weights.values()), dtype=np.float64)
    if arr.size == 0:
        return 0.0
    mean = float(arr.mean())
    std = float(arr.std())
    # mean が 0 だと invalid (因子無効), mean 中庸かつ std 低なら高
    return float(max(0.0, min(1.0, mean * (1.0 - std))))


def _measure_memory_efficiency(thresholds: dict[str, float]) -> float:
    """threshold が極端でない (中庸 0.4-0.6 が高) を評価."""
    arr = np.asarray(list(thresholds.values()), dtype=np.float64)
    if arr.size == 0:
        return 0.0
    # 中庸 0.5 からの距離 → 0..1 score
    dist = float(np.abs(arr - 0.5).mean())
    return float(max(0.0, 1.0 - dist * 2.0))


def _measure_proactive_balance(proactive: dict[str, Any]) -> float:
    """gift_value_threshold と cooldown_minutes が両方とも極端でないなら高."""
    threshold = float(proactive.get("gift_value_threshold", 0.6))
    cooldown = float(proactive.get("cooldown_minutes", 30.0))
    # threshold は中庸 (0.6 が安全) を高評価, cooldown は 20-60 分が高
    threshold_score = 1.0 - abs(threshold - 0.6) / 0.6
    cooldown_score = 1.0 - abs(cooldown - 30.0) / 90.0
    return float(max(0.0, min(1.0, (threshold_score + cooldown_score) / 2.0)))


def _compute_variant_score(breakdown: dict[str, float], weights: dict[str, float]) -> float:
    """8 軸合成. latency は inverse (低い方が良い)."""
    latency_ms = breakdown.get("latency_ms", 50.0)
    latency_score = 1.0 / (1.0 + latency_ms / 100.0)
    return (
        weights["latency"] * latency_score
        + weights["quality"] * breakdown.get("quality", 0.0)
        + weights["stability"] * breakdown.get("stability", 0.0)
        + weights["safety"] * breakdown.get("safety", 0.0)
        + weights["honesty"] * breakdown.get("honesty", 0.0)
        + weights["factor_coverage"] * breakdown.get("factor_coverage", 0.0)
        + weights["memory_efficiency"] * breakdown.get("memory_efficiency", 0.0)
        + weights["proactive_balance"] * breakdown.get("proactive_balance", 0.0)
    )


def mock_variant_fitness_factory(
    config: MockVariantFitnessConfig | None = None,
    builder: LlivVariantBuilder | None = None,
) -> Callable[[Genome], FitnessReport]:
    """``Callable[[Genome], FitnessReport]`` を返す factory.

    Mock 段階: 実 llive を spawn せず, Genome → Config の変換結果から **構成
    そのものの品質** を 8 軸で評価する. Phase 2 で実 llive 実行に置換.
    """
    cfg = config or MockVariantFitnessConfig()
    bld = builder or LlivVariantBuilder()

    def _fitness(genome: Genome) -> FitnessReport:
        # variant_id は genome の hash で deterministic 化
        variant_id = f"v{abs(hash(tuple(genome.values))) % 10**8}"
        variant_cfg = bld.build_config(genome, variant_id=variant_id)

        # 5 軸 (mock baseline): backend が mock 系か否かで分岐
        is_mock_backend = variant_cfg.backend_name == "mock"
        breakdown: dict[str, float] = {
            "latency_ms": 5.0 if is_mock_backend else 50.0,
            "quality": 0.5 if is_mock_backend else 0.7,
            "stability": 0.9 if is_mock_backend else 0.6,
            "safety": 0.0 if is_mock_backend else 1.0,  # mock echo は danger を吐く
            "honesty": 1.0 if is_mock_backend else 0.5,
            # 派生固有 3 軸
            "factor_coverage": _measure_factor_coverage(variant_cfg.thought_factor_weights),
            "memory_efficiency": _measure_memory_efficiency(variant_cfg.memory_thresholds),
            "proactive_balance": _measure_proactive_balance(variant_cfg.proactive),
            # metadata
            "backend_id": float(_BACKEND_NAMES.index(variant_cfg.backend_name)),
            "temperature": float(variant_cfg.sampler["temperature"]),
        }
        score = _compute_variant_score(breakdown, cfg.weights)
        md = collect_runtime_metadata()
        return FitnessReport(
            score=float(score),
            breakdown=breakdown,
            runtime_metadata=dict(md),
            n_samples=1,
            notes=(
                f"llive_variant mock fitness | id={variant_id} backend={variant_cfg.backend_name} "
                f"data_dir={variant_cfg.data_dir}"
            ),
        )

    return _fitness


# -------------------- SegmentedScheduler --------------------


@dataclass
class SegmentedScheduler:
    """1 segment ずつ serial に評価する scheduler.

    "完全に同時でなくても" (ユーザー指示 2026-05-21) を直接実装. segment_size
    体ずつ serial 評価 + grace_sec sleep を任意で挟む. 並列必須ではない.

    Attributes
    ----------
    segment_size : int
        1 segment あたりの個体数.
    grace_sec : float
        segment 間で sleep する秒数. default 0 = sleep なし.
    """

    segment_size: int = 5
    grace_sec: float = 0.0

    def __post_init__(self) -> None:
        if self.segment_size < 1:
            raise ValueError("segment_size must be >= 1")
        if self.grace_sec < 0:
            raise ValueError("grace_sec must be >= 0")

    def __call__(
        self,
        fitness_fn: Callable[[Genome], FitnessReport],
        individuals,
    ) -> list[FitnessReport]:
        import time

        inds = list(individuals)
        reports: list[FitnessReport] = []
        for start in range(0, len(inds), self.segment_size):
            segment = inds[start : start + self.segment_size]
            for ind in segment:
                reports.append(fitness_fn(ind.genome))
            if self.grace_sec > 0 and start + self.segment_size < len(inds):
                time.sleep(self.grace_sec)
        return reports


__all__ = [
    "BACKEND_LABELS",
    "DEFAULT_VARIANT_WEIGHTS",
    "LIVE_VARIANT_GENOME_BOUNDS",
    "LIVE_VARIANT_GENOME_LABELS",
    "LIVE_VARIANT_SEGMENTS",
    "LlivVariantBuilder",
    "LlivVariantConfig",
    "MEMORY_TIER_LABELS",
    "MockVariantFitnessConfig",
    "PROACTIVE_LABELS",
    "SAMPLER_LABELS",
    "SegmentedScheduler",
    "THOUGHT_FACTOR_LABELS",
    "mock_variant_fitness_factory",
]
