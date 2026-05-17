# SPDX-License-Identifier: Apache-2.0
"""VRB-04 — Premortem / Counterfactual Review.

採用前の Brief に「失敗シナリオ」を deterministic に生成する formal premortem 層。

`HatPerspective.BLACK` / `RolePerspective.CRITIC` が「視点からの観察」だったのに対し、
こちらは「失敗シナリオの **構造化列挙**」を担う。両者の責務:

* BlackHatLens = 1 文の risk observation
* PremortemGenerator = 失敗シナリオ表 (想定反論 / 妥当性 / 対応方針 / 追加検証)

deterministic な heuristic で初期実装。後段で LLM-driven generator に
Strategy 差し替え可能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger
    from llive.brief.types import Brief


_DANGEROUS_TOKENS: tuple[str, ...] = (
    "rm -rf", "sudo", "drop table", "delete from", "format c:",
    "shutdown", "kill -9", "chmod 777",
)


@dataclass(frozen=True)
class FailureScenario:
    """想定される 1 つの失敗シナリオ — 表 1 行に相当。"""

    title: str
    likelihood: str           # "low" / "medium" / "high"
    impact: str               # "low" / "medium" / "high"
    mitigation: str           # 対応方針
    additional_check: str     # 追加検証

    def to_payload(self) -> dict[str, object]:
        return {
            "title": self.title,
            "likelihood": self.likelihood,
            "impact": self.impact,
            "mitigation": self.mitigation,
            "additional_check": self.additional_check,
        }


@dataclass(frozen=True)
class PremortemReport:
    brief_id: str
    scenarios: tuple[FailureScenario, ...] = ()

    @property
    def has_high_impact(self) -> bool:
        return any(s.impact == "high" for s in self.scenarios)

    def to_payload(self) -> dict[str, object]:
        return {
            "brief_id": self.brief_id,
            "scenarios": [s.to_payload() for s in self.scenarios],
            "has_high_impact": self.has_high_impact,
        }


class PremortemGenerator:
    """Deterministic premortem generator with Strategy injection point.

    Future LLM lens implementation should override :meth:`scenarios_for`
    to consult the model + corpus instead of the heuristic rules below.
    """

    def __init__(self, *, ledger: "BriefLedger | None" = None) -> None:
        self._ledger = ledger

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        self._ledger = ledger

    def generate(self, brief: "Brief") -> PremortemReport:
        scenarios: list[FailureScenario] = list(self.scenarios_for(brief))
        report = PremortemReport(brief_id=brief.brief_id, scenarios=tuple(scenarios))
        if self._ledger is not None:
            self._ledger.append("premortem_generated", report.to_payload())
        return report

    # -- heuristic generators -----------------------------------------------

    def scenarios_for(self, brief: "Brief") -> list[FailureScenario]:
        out: list[FailureScenario] = []
        text = (brief.goal + "\n" + "\n".join(brief.constraints)).lower()

        # 1. dangerous-token scenarios — always high impact
        for tok in _DANGEROUS_TOKENS:
            if tok in text:
                out.append(FailureScenario(
                    title=f"危険トークン {tok!r} の意図せぬ実行",
                    likelihood="medium",
                    impact="high",
                    mitigation="Approval Bus + tool whitelist で gating",
                    additional_check="dry-run / sandbox 実行で副作用なし確認",
                ))

        # 2. action without tools — execution failure
        if not brief.tools and "execute" in text:
            out.append(FailureScenario(
                title="実行宣言があるが tools が空 — 実行手段なし",
                likelihood="high",
                impact="medium",
                mitigation="brief.tools に実行ハンドラを追加",
                additional_check="tool 起動 unit test",
            ))

        # 3. missing success_criteria — evaluation impossible
        if not brief.success_criteria:
            out.append(FailureScenario(
                title="success_criteria 未定義 — 合否判定不能",
                likelihood="high",
                impact="medium",
                mitigation="Brief 提出前に成功条件を追記",
                additional_check="VRB-05 metrics_registry と突合",
            ))

        # 4. INTERVENE without approval — governance break
        if not brief.approval_required:
            out.append(FailureScenario(
                title="approval_required=False — 監査ポイント欠落",
                likelihood="medium",
                impact="high",
                mitigation="approval_required=True に変更",
                additional_check="Approval Bus policy で auto-deny を確認",
            ))

        # 5. constraint contradiction heuristic — vague vs strict
        if "可能な限り" in text and any("must" in c.lower() or "必須" in c for c in brief.constraints):
            out.append(FailureScenario(
                title="曖昧制約と必須制約の同居 — 矛盾するスペック",
                likelihood="medium",
                impact="medium",
                mitigation="どちらかを採用し言い換える",
                additional_check="VRB-02 PromptLint を実行",
            ))

        return out


__all__ = [
    "FailureScenario",
    "PremortemGenerator",
    "PremortemReport",
]
