# SPDX-License-Identifier: Apache-2.0
"""FullSense — 自発トリガから始まる自律思考ループ (Sandbox-only MVP).

ユーザ Furuse の名から取った概念名。現状の AI が「user の質問」を待たないと
動かないのに対し、FullSense は **外乱 / 内乱 / 退屈タイマー**を spontaneous
trigger として受け取り、TRIZ や生物学的記憶モデルの「思考の網」を通過させて
**自発的な action plan** を生成する。

本リリースは **Sandbox-only MVP** (memory: user 選択「Sandbox だけで完全自律
実験」)。Output Bus は log のみで、外向け副作用は一切なし。

FullSense Loop の 6 ステージ::

    [外乱 / 内乱 / 退屈タイマー]
        ↓
    ① Salience Gate          ─ BayesianSurpriseGate を流用
        ↓
    ② Curiosity Drive        ─ SemanticMemory との距離測定
        ↓
    ③ Inner Monologue        ─ episodic 振り返り + TRIZ 思考の網
        ↓
    ④ Ego/Altruism Scorer    ─ 利己/利他のバランス重み付け
        ↓
    ⑤ Action Plan            ─ 黙る / メモする / 提案する (sandbox は log のみ)
        ↓
    ⑥ Output Bus             ─ Sandbox: log only / 本番: TUI/MCP/llove bridge

詳細仕様は :mod:`llive.fullsense.loop` を参照。命名根拠は
``docs/fullsense_naming_research.md`` に記載。
"""

from llive.fullsense.loop import FullSenseLoop, FullSenseResult
from llive.fullsense.sandbox import SandboxOutputBus
from llive.fullsense.scorer import EgoAltruismScorer
from llive.fullsense.triggers import IdleTrigger, StimulusSource
from llive.fullsense.types import ActionDecision, ActionPlan, Stimulus, Thought

__all__ = [
    "ActionDecision",
    "ActionPlan",
    "EgoAltruismScorer",
    "FullSenseLoop",
    "FullSenseResult",
    "IdleTrigger",
    "SandboxOutputBus",
    "Stimulus",
    "StimulusSource",
    "Thought",
]
