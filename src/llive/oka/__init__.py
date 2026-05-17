# SPDX-License-Identifier: Apache-2.0
"""OKA-FX — Oka Kiyoshi Framework for the math vertical (v0.7-vertical+OKA).

岡潔の数学観 (情緒 / 行き詰まり / 文章化 / 国語力) を実装仕様に変換した
4 モジュール群。MATH-* が「計算の正確さ」を担うのに対し、OKA-* は
「数学者の思考プロセスの質」を担う。両者は補強関係 — MathVerifier が
「黒板の正しさ」、OKA が「黒板に到達するまでの探索の質」。

Minimal v0.7-vertical+OKA prototype (2026-05-17):

* :class:`CoreEssence` / :class:`CoreEssenceExtractor` — 問題から「核心メモ」を
  抽出 (OKA-01 / OKA-02)
* :class:`ReflectiveNote` / :class:`ReflectiveNotebook` — 中間/失敗/気づきを
  JSON で永続 (OKA-04)
* :class:`StrategyFamily` / :class:`StrategyOrchestrator` — 戦略切替 (OKA-03)

すべて BriefLedger と連動可能 (``bind_ledger()`` パターン)。
MathVerifier / RoleBasedMultiTrack と同じ Strategy 注入 + 後付け ledger 設計。
"""

from __future__ import annotations

from llive.oka.essence import (
    CoreEssence,
    CoreEssenceExtractor,
    EssenceLens,
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
    "ReflectiveNote",
    "ReflectiveNotebook",
    "StrategyFamily",
    "StrategyOrchestrator",
    "StrategySwitchEvent",
]
