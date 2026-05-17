# SPDX-License-Identifier: Apache-2.0
"""CREAT-03 — 構造化変換 (KJ + MindMap + TRIZ + Six Hats → 要件 spec).

人間の思考フロー「拡散 → 構造化 → 収束」の **収束** を担う。

入力:
* KJBoard (CREAT-01)
* MindMapTree (CREAT-02)
* TRIZ citations (BriefGrounder の出力、optional)
* RoleBasedMultiTrack 結果 (perspectives, optional)

出力:
* :class:`RequirementDraft` — 構造化された要件 spec の draft

deterministic な構造化アルゴリズム:

1. KJBoard のクラスタを「テーマ群」として extract
2. MindMap depth=1 子を「要件カテゴリ」として extract
3. Six Hats の black/critic を「リスク注記」として attach
4. TRIZ citations を「適用原理」として attach
5. 全部を 1 つの RequirementDraft に詰める

`bind_ledger()` → `requirement_draft_generated` event。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger
    from llive.brief.roles import MultiTrackSummary
    from llive.brief.types import Brief
    from llive.creat.kj import KJBoard
    from llive.creat.mindmap import MindMapTree


@dataclass(frozen=True)
class RequirementCategory:
    name: str
    items: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {"name": self.name, "items": list(self.items)}


@dataclass(frozen=True)
class RequirementDraft:
    brief_id: str
    themes: tuple[str, ...]
    categories: tuple[RequirementCategory, ...]
    risk_notes: tuple[str, ...]
    triz_principles: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "brief_id": self.brief_id,
            "themes": list(self.themes),
            "categories": [c.to_payload() for c in self.categories],
            "risk_notes": list(self.risk_notes),
            "triz_principles": list(self.triz_principles),
        }

    def to_markdown(self) -> str:
        """人間が読める要件 draft Markdown を返す."""
        lines = [f"# Requirement draft (brief={self.brief_id})", ""]
        if self.themes:
            lines.append("## Themes")
            for t in self.themes:
                lines.append(f"- {t}")
            lines.append("")
        for cat in self.categories:
            lines.append(f"## {cat.name}")
            for item in cat.items:
                lines.append(f"- {item}")
            lines.append("")
        if self.risk_notes:
            lines.append("## Risk notes")
            for r in self.risk_notes:
                lines.append(f"- {r}")
            lines.append("")
        if self.triz_principles:
            lines.append("## Applicable TRIZ principles")
            for p in self.triz_principles:
                lines.append(f"- {p}")
            lines.append("")
        return "\n".join(lines) + "\n"


class StructureSynthesizer:
    """4 入力 → RequirementDraft の deterministic converger."""

    def __init__(self, *, ledger: "BriefLedger | None" = None) -> None:
        self._ledger = ledger

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        self._ledger = ledger

    def synthesize(
        self,
        brief: "Brief",
        *,
        kj_board: "KJBoard | None" = None,
        mindmap: "MindMapTree | None" = None,
        perspectives: "MultiTrackSummary | None" = None,
        triz_principle_names: tuple[str, ...] = (),
    ) -> RequirementDraft:
        themes: list[str] = []
        if kj_board is not None:
            themes.extend(c.label for c in kj_board.clusters[:5])

        categories: list[RequirementCategory] = []
        # Brief 自体の constraints / success_criteria は確実な要件
        if brief.constraints:
            categories.append(RequirementCategory(
                name="Constraints (from Brief)",
                items=tuple(brief.constraints),
            ))
        if brief.success_criteria:
            categories.append(RequirementCategory(
                name="Success criteria (from Brief)",
                items=tuple(brief.success_criteria),
            ))
        if mindmap is not None:
            depth1 = mindmap.children_of(mindmap.root.node_id)
            if depth1:
                categories.append(RequirementCategory(
                    name="MindMap top branches",
                    items=tuple(n.label for n in depth1),
                ))

        risk_notes: list[str] = []
        if perspectives is not None:
            risk_notes.extend(perspectives.critical_concerns[:5])

        report = RequirementDraft(
            brief_id=brief.brief_id,
            themes=tuple(themes),
            categories=tuple(categories),
            risk_notes=tuple(risk_notes),
            triz_principles=tuple(triz_principle_names),
        )
        if self._ledger is not None:
            self._ledger.append("requirement_draft_generated", report.to_payload())
        return report


__all__ = [
    "RequirementCategory",
    "RequirementDraft",
    "StructureSynthesizer",
]
