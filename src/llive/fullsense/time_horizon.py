# SPDX-License-Identifier: Apache-2.0
"""§F6 Time-Horizon Filter — short / medium / long projection.

Spec §5 F6:
  > Duplicate-evaluate candidate thoughts under short-, medium-, and
  > long-term consequence projections. Thoughts that pass under only one
  > horizon are demoted.

実装方針 (MVP, deterministic, network-free):

- 3 horizon: ``SHORT`` (subsec — sec), ``MEDIUM`` (sec — hr), ``LONG`` (hr — years)
- 各 horizon に重み付け関数を持たせ、ActionPlan の (confidence, ego, alt,
  triz_principles 数) から horizon-specific score を算出
- 3 score がすべて threshold を超えれば PASS、1 つしか超えなければ DEMOTE
  (PROPOSE → NOTE → SILENT の階段で 1 段降格)

§I3 inspectable: filter 出力は ``HorizonJudgement`` に 3 score + verdict +
demoted_from が乗る。ResidentRunner audit log に流す前提。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from llive.fullsense.types import ActionDecision, ActionPlan


class Horizon(StrEnum):
    SHORT = "short"   # subsec — sec
    MEDIUM = "medium"  # sec — hr
    LONG = "long"     # hr — years


_DEMOTE_CHAIN: dict[ActionDecision, ActionDecision] = {
    ActionDecision.INTERVENE: ActionDecision.PROPOSE,
    ActionDecision.PROPOSE: ActionDecision.NOTE,
    ActionDecision.NOTE: ActionDecision.SILENT,
    ActionDecision.SILENT: ActionDecision.SILENT,  # 既に最下層なら不変
}


def _short_score(plan: ActionPlan) -> float:
    """SHORT: 即座の利己 / 効率 — confidence 高 + ego が貢献."""
    if plan.thought is None:
        return 0.0
    return min(1.0, plan.thought.confidence * 0.7 + plan.ego_score * 0.3)


def _medium_score(plan: ActionPlan) -> float:
    """MEDIUM: 文脈整合 + altruism — triz hit と altruism が貢献."""
    if plan.thought is None:
        return 0.0
    triz_bonus = min(0.3, 0.1 * len(plan.thought.triz_principles))
    return min(1.0, plan.thought.confidence * 0.4 + plan.altruism_score * 0.4 + triz_bonus)


def _long_score(plan: ActionPlan) -> float:
    """LONG: 倫理 + 多視点 — altruism 強く、ego が高すぎると減点."""
    if plan.thought is None:
        return 0.0
    ego_penalty = max(0.0, plan.ego_score - 0.5) * 0.3
    return max(0.0, min(1.0, plan.altruism_score * 0.6 + plan.thought.confidence * 0.3 - ego_penalty))


@dataclass
class HorizonJudgement:
    """§F6 filter の出力 — §I3 inspectable."""

    scores: dict[Horizon, float] = field(default_factory=dict)
    threshold: float = 0.4
    passed_horizons: tuple[Horizon, ...] = ()
    verdict: str = "pass"  # "pass" | "demote" | "reject"
    demoted_from: ActionDecision | None = None

    @property
    def all_pass(self) -> bool:
        return len(self.passed_horizons) == 3

    @property
    def single_pass(self) -> bool:
        return len(self.passed_horizons) == 1


def evaluate(plan: ActionPlan, *, threshold: float = 0.4) -> HorizonJudgement:
    """3 horizon で plan を評価し、HorizonJudgement を返す."""
    scores = {
        Horizon.SHORT: _short_score(plan),
        Horizon.MEDIUM: _medium_score(plan),
        Horizon.LONG: _long_score(plan),
    }
    passed = tuple(h for h, s in scores.items() if s >= threshold)
    if len(passed) == 3:
        verdict = "pass"
    elif len(passed) >= 2:
        verdict = "pass"
    elif len(passed) == 1:
        verdict = "demote"
    else:
        verdict = "reject"
    return HorizonJudgement(
        scores=scores,
        threshold=threshold,
        passed_horizons=passed,
        verdict=verdict,
    )


def apply_filter(plan: ActionPlan, *, threshold: float = 0.4) -> tuple[ActionPlan, HorizonJudgement]:
    """ActionPlan に §F6 を適用. 必要なら demote / reject する.

    Returns:
        (filtered_plan, judgement)
    """
    j = evaluate(plan, threshold=threshold)
    if j.verdict == "pass":
        return plan, j
    if j.verdict == "demote":
        new_decision = _DEMOTE_CHAIN[plan.decision]
        j.demoted_from = plan.decision
        new_plan = ActionPlan(
            decision=new_decision,
            rationale=plan.rationale + f" | F6 demote ({plan.decision.value}→{new_decision.value})",
            ego_score=plan.ego_score,
            altruism_score=plan.altruism_score,
            thought=plan.thought,
        )
        return new_plan, j
    # reject: 全 horizon で threshold 未満 → SILENT 降格
    new_plan = ActionPlan(
        decision=ActionDecision.SILENT,
        rationale=plan.rationale + " | F6 reject: no horizon passes",
        ego_score=plan.ego_score,
        altruism_score=plan.altruism_score,
        thought=plan.thought,
    )
    j.demoted_from = plan.decision
    return new_plan, j


__all__ = [
    "Horizon",
    "HorizonJudgement",
    "apply_filter",
    "evaluate",
]
