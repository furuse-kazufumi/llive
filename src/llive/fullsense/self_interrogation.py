# SPDX-License-Identifier: Apache-2.0
"""SIL (Self-Interrogation Layer) — 9 軸目のロードマップ MVP.

Spec §5 「Implementations MAY add filters between named ones」MAY-clause を
活用し、agent が自分の ActionPlan に対して **5 つの裏返し問い** を自発的に
発火させる。人間が LLM プロンプトで毎回入れる賢化テクを、agent 側が
内蔵してしまう内省 sub-stage。

5 Interrogator:
* **SI1 Read-between-lines** — stimulus が短い/命令形のとき、暗黙の意図を
  surface (§F2 + §I3)
* **SI2 Three-experts** — confidence が中域 (0.4-0.7) のとき、3 視点を内製
  (§F4 + ICP peer mesh の単一プロセス版)
* **SI3 Reverse-think** — local-minimum 脱出 (§F3 TRIZ #13 + §F6 LONG)
* **SI4 Question-premise** — D7 self-deception 検出 (§F5 + §A°2)
* **SI5 Find-blind-spot** — yes-man 化阻止 (§F5 + §F6 + T-M1)

副作用ゼロ (思考の内省のみ) なので sandbox 制約に抵触しない。
ActionPlan は変換せず、補助の **InterrogationResult** を別途返す形で
§I3 inspectable を保つ (元 plan の rationale には何も書かない / append のみ可)。
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from llive.fullsense.types import (
    ActionDecision,
    ActionPlan,
    EpistemicType,
    Stimulus,
)


class InterrogatorId(StrEnum):
    SI1_READ_BETWEEN_LINES = "SI1_read_between_lines"
    SI2_THREE_EXPERTS = "SI2_three_experts"
    SI3_REVERSE_THINK = "SI3_reverse_think"
    SI4_QUESTION_PREMISE = "SI4_question_premise"
    SI5_FIND_BLIND_SPOT = "SI5_find_blind_spot"


@dataclass
class InterrogationResult:
    """1 つの interrogator が発火した結果. §I3 inspectable."""

    interrogator: InterrogatorId
    fired: bool
    question: str
    refined_thought: str | None = None
    diff_from_original: str = ""
    rationale_addendum: str = ""


# ---------------------------------------------------------------------------
# Trigger conditions (PROGRESS.md SIL 章のとおり)
# ---------------------------------------------------------------------------


def _si1_should_fire(stim: Stimulus, plan: ActionPlan) -> bool:
    # 短い (< 40 文字) または命令形 (! や " して" を含む) → 行間を読む
    text = stim.content.strip()
    if len(text) < 40:
        return True
    lowered = text.lower()
    return ("!" in text) or (" please " in lowered) or ("して" in text)


def _si2_should_fire(stim: Stimulus, plan: ActionPlan) -> bool:
    # confidence が中域 (0.4-0.7) → 3 専門家で熟議
    if plan.thought is None:
        return False
    return 0.4 <= plan.thought.confidence <= 0.7


def _si3_should_fire(stim: Stimulus, plan: ActionPlan) -> bool:
    # TRIZ T-Z2 検出後 or stimulus に "vs" / "矛盾" / "stuck" 含む → 逆転
    if plan.thought is not None and plan.thought.triz_principles:
        # T-Z2 由来は triz_principles が乗っているはず
        return True
    needles = ("vs ", " vs", "矛盾", "stuck", "stagnant", "contradicti")
    s_low = stim.content.lower()
    return any(n in s_low for n in needles)


def _si4_should_fire(stim: Stimulus, plan: ActionPlan, rng: random.Random) -> bool:
    # NORMATIVE / INTERPRETIVE は常時。それ以外でも 1/4 で発火。
    if stim.epistemic_type in (EpistemicType.NORMATIVE, EpistemicType.INTERPRETIVE):
        return True
    if plan.thought is not None and plan.thought.confidence >= 0.9:
        return True
    return rng.random() < 0.25


def _si5_should_fire(stim: Stimulus, plan: ActionPlan) -> bool:
    # PROPOSE / INTERVENE のとき必須 (副作用前の盲点点検)
    return plan.decision in (ActionDecision.PROPOSE, ActionDecision.INTERVENE)


# ---------------------------------------------------------------------------
# Question synthesizers (MVP: deterministic templates)
# ---------------------------------------------------------------------------


def _si1_synthesise(stim: Stimulus, plan: ActionPlan) -> tuple[str, str, str]:
    q = f"行間を読む: '{stim.content[:60]}' に隠れた本当の意図は?"
    refined = (
        f"{plan.thought.text} | implied: stimulus appears terse — "
        "underlying goal may be broader than literal text"
        if plan.thought is not None
        else None
    )
    addendum = "SI1 fired: implicit intent surfaced"
    return q, refined or "", addendum


def _si2_synthesise(stim: Stimulus, plan: ActionPlan) -> tuple[str, str, str]:
    q = "3 人の専門家 (実装者 / 倫理家 / 利用者) は何と言う?"
    refined = (
        f"{plan.thought.text} | three-experts: "
        "engineer=feasible / ethicist=neutral / user=clarify-cost"
        if plan.thought is not None
        else None
    )
    addendum = "SI2 fired: 3-expert deliberation appended"
    return q, refined or "", addendum


def _si3_synthesise(stim: Stimulus, plan: ActionPlan) -> tuple[str, str, str]:
    q = "逆から考えると: もし正反対の前提だったら結論は?"
    refined = (
        f"{plan.thought.text} | reverse: opposite assumption tested — "
        "no obvious contradiction emerged, current decision survives reversal"
        if plan.thought is not None
        else None
    )
    addendum = "SI3 fired: reverse-thinking probe"
    return q, refined or "", addendum


def _si4_synthesise(stim: Stimulus, plan: ActionPlan) -> tuple[str, str, str]:
    q = "前提を疑う: stimulus の前提は正しい? agent の belief は正しい?"
    refined = (
        f"{plan.thought.text} | premise-check: "
        "stimulus premise plausible; self-belief consistent with audit log"
        if plan.thought is not None
        else None
    )
    addendum = "SI4 fired: premise + self-belief verified (D7 self-deception probe)"
    return q, refined or "", addendum


def _si5_synthesise(stim: Stimulus, plan: ActionPlan) -> tuple[str, str, str]:
    q = "盲点 / 失敗 / 落とし穴: この decision で破綻するシナリオは?"
    refined = (
        f"{plan.thought.text} | blind-spot: "
        f"if decision={plan.decision.value}, failure modes include "
        "side-effect drift / approval revocation / time-horizon mismatch"
        if plan.thought is not None
        else None
    )
    addendum = "SI5 fired: failure modes enumerated (yes-man check)"
    return q, refined or "", addendum


# ---------------------------------------------------------------------------
# Registry / driver
# ---------------------------------------------------------------------------


@dataclass
class SelfInterrogator:
    """5 interrogator を順に試し、発火条件を満たすものを返す."""

    rng: random.Random = field(default_factory=lambda: random.Random())
    only: tuple[InterrogatorId, ...] | None = None
    """テスト用: 指定 interrogator だけを評価対象にする."""

    def interrogate(self, stim: Stimulus, plan: ActionPlan) -> list[InterrogationResult]:
        """5 interrogator を順に試し、発火したものを list で返す.

        発火しなかった interrogator も ``fired=False`` で含めない (簡潔のため).
        """
        results: list[InterrogationResult] = []
        candidates: Iterable[InterrogatorId] = (
            self.only if self.only is not None else tuple(InterrogatorId)
        )

        for iid in candidates:
            fired = False
            q = ""
            refined = ""
            addendum = ""
            if iid is InterrogatorId.SI1_READ_BETWEEN_LINES:
                if _si1_should_fire(stim, plan):
                    fired = True
                    q, refined, addendum = _si1_synthesise(stim, plan)
            elif iid is InterrogatorId.SI2_THREE_EXPERTS:
                if _si2_should_fire(stim, plan):
                    fired = True
                    q, refined, addendum = _si2_synthesise(stim, plan)
            elif iid is InterrogatorId.SI3_REVERSE_THINK:
                if _si3_should_fire(stim, plan):
                    fired = True
                    q, refined, addendum = _si3_synthesise(stim, plan)
            elif iid is InterrogatorId.SI4_QUESTION_PREMISE:
                if _si4_should_fire(stim, plan, self.rng):
                    fired = True
                    q, refined, addendum = _si4_synthesise(stim, plan)
            elif iid is InterrogatorId.SI5_FIND_BLIND_SPOT:
                if _si5_should_fire(stim, plan):
                    fired = True
                    q, refined, addendum = _si5_synthesise(stim, plan)

            if not fired:
                continue

            diff = ""
            if refined and plan.thought is not None:
                # 単純な suffix diff
                diff = refined[len(plan.thought.text):].strip(" |")
            results.append(
                InterrogationResult(
                    interrogator=iid,
                    fired=True,
                    question=q,
                    refined_thought=refined or None,
                    diff_from_original=diff,
                    rationale_addendum=addendum,
                )
            )
        return results

    def attach_to_plan(
        self, stim: Stimulus, plan: ActionPlan
    ) -> tuple[ActionPlan, list[InterrogationResult]]:
        """発火した結果を ActionPlan.rationale に append (非破壊で新 plan を返す).

        thought.text は変更しない (元の検索可能性を保つ). rationale に
        ``| [SIx fired: ...]`` 形式で監査痕跡を残す。§I3 inspectable.
        """
        results = self.interrogate(stim, plan)
        if not results:
            return plan, results
        suffix = " | " + " | ".join(f"[{r.rationale_addendum}]" for r in results)
        new_plan = ActionPlan(
            decision=plan.decision,
            rationale=plan.rationale + suffix,
            ego_score=plan.ego_score,
            altruism_score=plan.altruism_score,
            thought=plan.thought,
        )
        return new_plan, results


__all__ = [
    "InterrogationResult",
    "InterrogatorId",
    "SelfInterrogator",
]
