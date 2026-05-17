# SPDX-License-Identifier: Apache-2.0
"""OKA-FX — Framework inspired by the writings of Prof. Oka Kiyoshi
(v0.7-vertical+OKA).

岡潔先生 (1901-1978) が遺された数学観 ―― 「数学は情緒である」「発見の前に
一度行き詰まる」「文章を書くことなしには思索を進められない」「国語が
数学を育む」―― という思想に学ばせていただき、その 4 観点を **設計の
切り口** として実装に取り込んだモジュール群。

**重要**: 本モジュール群は、岡潔先生のお考えそのものを実装したと主張する
ものではありません。先生が遺された豊かな思索のうち、エンジニアリング言語
として参照させていただける 4 観点に着目し、それを **触発源** として
モジュール設計に活かしたものです。命名にはその敬意を込めています。

MATH-* が「計算の正確さ」(deterministic verification) を担うのに対し、
OKA-* は「数学者の思考プロセスの質」(reflective process quality) を担う
補強層として位置付けています。

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
