# SPDX-License-Identifier: Apache-2.0
"""VRB-06 — Dual Spec Writer.

同一 Brief を **5 つの audience-specific 表現** に変換する deterministic renderer。

| Mode | 用途 | 形式 |
|---|---|---|
| ``HUMAN_BRIEF`` | 人間 (研究者/PM/管理者) | Markdown 短報 |
| ``MODEL_CONTRACT`` | LLM 入力 | 制約付き instruction block |
| ``EVAL_CONTRACT`` | 評価器 | metric / 閾値 / 停止条件の YAML |
| ``EXECUTION_MANIFEST`` | 実行系 / CI | tool whitelist + ledger path |
| ``RESEARCH_NOTE`` | 研究ノート / 公開 | 文体を抑えた説明書 |

設計:

* Strategy 注入なし — render は決定論的、入力 Brief から純粋関数的に出力
* :class:`EvalSpec` を渡すと EVAL_CONTRACT が中身を持つ (未指定なら success_criteria のみ)
* テキスト形式に閉じる → CI でも diff 比較しやすい
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llive.annotations import AnnotationBundle
    from llive.brief.eval_spec import EvalSpec
    from llive.brief.types import Brief


class RenderMode(StrEnum):
    HUMAN_BRIEF = "human_brief"
    MODEL_CONTRACT = "model_contract"
    EVAL_CONTRACT = "eval_contract"
    EXECUTION_MANIFEST = "execution_manifest"
    RESEARCH_NOTE = "research_note"


# ---------------------------------------------------------------------------
# Per-mode renderers
# ---------------------------------------------------------------------------


def _render_human_brief(brief: "Brief") -> str:
    lines = [f"# Brief: {brief.brief_id}", "", f"**Goal**: {brief.goal}", ""]
    if brief.constraints:
        lines.append("## Constraints")
        for c in brief.constraints:
            lines.append(f"- {c}")
        lines.append("")
    if brief.success_criteria:
        lines.append("## Success criteria")
        for s in brief.success_criteria:
            lines.append(f"- {s}")
        lines.append("")
    lines.append(f"_priority={brief.priority}, approval_required={brief.approval_required}_")
    return "\n".join(lines) + "\n"


def _render_model_contract(brief: "Brief") -> str:
    parts = ["<<<MODEL CONTRACT>>>", f"GOAL: {brief.goal}"]
    if brief.constraints:
        parts.append("CONSTRAINTS:")
        for c in brief.constraints:
            parts.append(f"  - MUST: {c}")
    if brief.success_criteria:
        parts.append("SUCCESS CRITERIA:")
        for s in brief.success_criteria:
            parts.append(f"  - {s}")
    if brief.tools:
        parts.append("TOOLS ALLOWED:")
        for t in brief.tools:
            parts.append(f"  - {t}")
    parts.append("OUTPUT FORMAT: structured + cited; do not invent values.")
    parts.append("<<<END CONTRACT>>>")
    return "\n".join(parts) + "\n"


def _render_eval_contract(brief: "Brief", spec: "EvalSpec | None") -> str:
    lines = [f"# Eval contract for {brief.brief_id}", ""]
    if spec is None:
        lines.append("## Success criteria (free text)")
        for s in brief.success_criteria:
            lines.append(f"- {s}")
        return "\n".join(lines) + "\n"
    lines.append("## Metrics")
    for m in spec.metrics:
        direction = "lower" if m.lower_is_better else "higher"
        thr = m.threshold if m.threshold is not None else "(unset)"
        lines.append(f"- {m.name} ({m.unit}) threshold={thr} {direction}_is_better")
    lines.append("")
    lines.append("## Stop conditions")
    for c in spec.stop_conditions:
        lines.append(f"- {c.condition_id}: {c.metric_name} {c.operator} {c.value}")
    return "\n".join(lines) + "\n"


def _render_execution_manifest(brief: "Brief") -> str:
    lines = [
        f"manifest_version: 1",
        f"brief_id: {brief.brief_id}",
        f"approval_required: {str(brief.approval_required).lower()}",
        f"priority: {brief.priority}",
    ]
    if brief.tools:
        lines.append("tools_whitelist:")
        for t in brief.tools:
            lines.append(f"  - {t}")
    if brief.ledger_path is not None:
        lines.append(f"ledger_path: {brief.ledger_path.as_posix()}")
    return "\n".join(lines) + "\n"


def _render_research_note(brief: "Brief") -> str:
    """Audience: 公開向け説明 — 過剰断言を避け事実中心。"""
    paragraphs: list[str] = []
    paragraphs.append(
        f"Brief `{brief.brief_id}` aimed to: {brief.goal}".rstrip(".") + "."
    )
    if brief.constraints:
        paragraphs.append(
            "The plan was bounded by: "
            + "; ".join(brief.constraints) + "."
        )
    if brief.success_criteria:
        paragraphs.append(
            "Success was defined by: "
            + "; ".join(brief.success_criteria) + "."
        )
    return "\n\n".join(paragraphs) + "\n"


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderedBrief:
    brief_id: str
    mode: RenderMode
    body: str


class DualSpecWriter:
    """Renders a Brief into one or more :class:`RenderMode` outputs."""

    def render(
        self,
        brief: "Brief",
        mode: RenderMode,
        *,
        eval_spec: "EvalSpec | None" = None,
    ) -> RenderedBrief:
        if mode is RenderMode.HUMAN_BRIEF:
            body = _render_human_brief(brief)
        elif mode is RenderMode.MODEL_CONTRACT:
            body = _render_model_contract(brief)
        elif mode is RenderMode.EVAL_CONTRACT:
            body = _render_eval_contract(brief, eval_spec)
        elif mode is RenderMode.EXECUTION_MANIFEST:
            body = _render_execution_manifest(brief)
        elif mode is RenderMode.RESEARCH_NOTE:
            body = _render_research_note(brief)
        else:  # pragma: no cover - StrEnum closed
            raise ValueError(f"unsupported mode: {mode!r}")
        return RenderedBrief(brief_id=brief.brief_id, mode=mode, body=body)

    def render_all(
        self,
        brief: "Brief",
        *,
        eval_spec: "EvalSpec | None" = None,
    ) -> dict[RenderMode, RenderedBrief]:
        return {m: self.render(brief, m, eval_spec=eval_spec) for m in RenderMode}


__all__ = [
    "DualSpecWriter",
    "RenderMode",
    "RenderedBrief",
]
