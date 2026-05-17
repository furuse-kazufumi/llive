# SPDX-License-Identifier: Apache-2.0
"""OKA-FX — Oka Kiyoshi Framework for the math vertical (v0.7-vertical+OKA).

岡潔の数学観 (情緒 / 行き詰まり / 文章化 / 国語力) を実装仕様に変換した
モジュール群。MATH-* が「計算の正確さ」を担うのに対し、OKA-* は
「数学者の思考プロセスの質」を担う。

Minimal v0.7-vertical+OKA prototype (2026-05-17):

* OKA-01/02 :class:`CoreEssence` / :class:`CoreEssenceExtractor` — 核心メモ抽出
* OKA-03 :class:`StrategyOrchestrator` — 戦略切替
* OKA-04 :class:`ReflectiveNotebook` — 中間/失敗/気づきを JSON 永続
* OKA-06 :class:`ExplanationAligner` — 解答 + naturalness rationale
* OKA-07 :class:`InsightScorer` — CoreEssence と ground-truth の deterministic 比較

すべて BriefLedger と連動可能 (``bind_ledger()`` パターン)。
"""

from __future__ import annotations

from llive.oka.essence import (
    CoreEssence,
    CoreEssenceExtractor,
    EssenceLens,
)
from llive.oka.explanation import (
    ExplanationAligner,
    ExplanationDraft,
)
from llive.oka.insight_score import (
    GroundTruthEssence,
    InsightScore,
    InsightScorer,
)
from llive.oka.notebook import (
    ReflectiveNote,
    ReflectiveNotebook,
)
from llive.oka.orchestrator import (
    StrategyFamily,
    StrategyOrchestrator,
    StrategySwitchEvent,
)

__all__ = [
    "CoreEssence",
    "CoreEssenceExtractor",
    "EssenceLens",
    "ExplanationAligner",
    "ExplanationDraft",
    "GroundTruthEssence",
    "InsightScore",
    "InsightScorer",
    "ReflectiveNote",
    "ReflectiveNotebook",
    "StrategyFamily",
    "StrategyOrchestrator",
    "StrategySwitchEvent",
]
