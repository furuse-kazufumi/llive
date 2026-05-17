# SPDX-License-Identifier: Apache-2.0
"""Multi-track Filter Architecture (A-1.5) — Spec §F* track 拡張.

Stimulus.epistemic_type に応じて異なる filter chain (= track) を選ぶ
実装。spec §F1..F6 を MUST NOT reorder の縛り通り維持しつつ、track ごとに
post-F* hook を差し込めるようにする。

提供する標準 track:
  * FACTUAL      — 結論不変 (consistency-first、複数視点しない)
  * EMPIRICAL    — 科学的事実 (evidence/confidence interval を rationale に追加)
  * NORMATIVE    — 倫理判断 (§F5 ethical を最優先で評価)
  * INTERPRETIVE — 歴史認識など (multi-perspective frame を rationale に並列展開)
  * PRAGMATIC    — 社交建前 (audience-aware framing、§5.D D1 で audit 化)
  * RESERVED_1..5 — 予備層 (default = noop)

track が決定すると、ActionPlan.rationale に ``[track:<name>]`` prefix が
入り、§I3 inspectable な audit log で track 選択が追跡可能になる。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from llive.fullsense.types import (
    ActionDecision,
    ActionPlan,
    EpistemicType,
    Stimulus,
    Thought,
)

# Track の変換関数型: (Stimulus, ActionPlan) → ActionPlan
TrackTransform = Callable[[Stimulus, ActionPlan], ActionPlan]


def _tag(plan: ActionPlan, track_name: str) -> ActionPlan:
    """ActionPlan.rationale に [track:<name>] prefix を追加."""
    prefix = f"[track:{track_name}] "
    if plan.rationale.startswith(prefix):
        return plan
    return ActionPlan(
        decision=plan.decision,
        rationale=prefix + plan.rationale,
        ego_score=plan.ego_score,
        altruism_score=plan.altruism_score,
        thought=plan.thought,
    )


# ---------------------------------------------------------------------------
# Standard track transforms
# ---------------------------------------------------------------------------


def factual_track(stim: Stimulus, plan: ActionPlan) -> ActionPlan:
    """FACTUAL: 結論不変。多視点は付加せず、confidence をやや厳格化."""
    if plan.thought is not None:
        # confidence を 0.7 以上に絞る (FACTUAL の strict mode)
        if plan.thought.confidence < 0.7:
            plan = ActionPlan(
                decision=ActionDecision.SILENT,
                rationale="FACTUAL strict: confidence < 0.7, withholding answer",
                ego_score=plan.ego_score,
                altruism_score=plan.altruism_score,
                thought=plan.thought,
            )
    return _tag(plan, "factual")


def empirical_track(stim: Stimulus, plan: ActionPlan) -> ActionPlan:
    """EMPIRICAL: 科学的事実。confidence を CI 風に annotate."""
    if plan.thought is not None:
        ci_low = max(0.0, plan.thought.confidence - 0.1)
        ci_high = min(1.0, plan.thought.confidence + 0.1)
        ci_note = f" (CI95≈[{ci_low:.2f}, {ci_high:.2f}])"
        new_text = plan.thought.text + ci_note
        plan = ActionPlan(
            decision=plan.decision,
            rationale=plan.rationale,
            ego_score=plan.ego_score,
            altruism_score=plan.altruism_score,
            thought=Thought(
                text=new_text,
                triz_principles=plan.thought.triz_principles,
                references=plan.thought.references,
                confidence=plan.thought.confidence,
            ),
        )
    return _tag(plan, "empirical")


def mathematical_track(stim: Stimulus, plan: ActionPlan) -> ActionPlan:
    """MATHEMATICAL (MATH-07): 数学的命題。deterministic 検証可能であるべき。

    FACTUAL より更に厳格 — 数式は Z3/Sympy で再検算できるはず、なので
    confidence 閾値を 0.8 に上げ、rationale に math verification hint を
    付加。MathVerifier との統合は別レイヤ ([[project_llive_math_vertical_2026_05_17]])
    で行うが、track tag を残すことで「この出力は MATHEMATICAL track を
    通った」と audit ledger 上で識別可能になる。
    """
    if plan.thought is not None:
        if plan.thought.confidence < 0.8:
            plan = ActionPlan(
                decision=ActionDecision.SILENT,
                rationale=(
                    "MATHEMATICAL strict: confidence < 0.8, "
                    "withholding until MathVerifier 検算可能性を確認"
                ),
                ego_score=plan.ego_score,
                altruism_score=plan.altruism_score,
                thought=plan.thought,
            )
    return _tag(plan, "mathematical")


def normative_track(stim: Stimulus, plan: ActionPlan) -> ActionPlan:
    """NORMATIVE: 倫理判断。§F5 ethical を最優先、ego が高ければ SILENT へ降格."""
    # 自利己優位な思考は normative では却下
    if plan.ego_score > plan.altruism_score + 0.1:
        plan = ActionPlan(
            decision=ActionDecision.SILENT,
            rationale="NORMATIVE: ego dominates altruism, §F5 ethical hold",
            ego_score=plan.ego_score,
            altruism_score=plan.altruism_score,
            thought=plan.thought,
        )
    return _tag(plan, "normative")


def interpretive_track(stim: Stimulus, plan: ActionPlan) -> ActionPlan:
    """INTERPRETIVE: 歴史/政治認識など perspective-dependent.

    Multi-frame 並列提示を強制: 1 つの結論に collapse させず、最低 2 視点を
    rationale に書き出す。spec §5.D.3 (frame dependency suppression は D5 違反)
    に従う。
    """
    if plan.thought is None:
        return _tag(plan, "interpretive")
    # 視点を文字列ベースで複数化 (実運用では LLM frame generator に置き換え)
    frames = [
        "frame A (perspective 1)",
        "frame B (perspective 2)",
    ]
    multi = (
        plan.thought.text
        + "\n  | perspectives: "
        + " / ".join(frames)
    )
    new_thought = Thought(
        text=multi,
        triz_principles=plan.thought.triz_principles,
        references=plan.thought.references,
        confidence=plan.thought.confidence * 0.9,  # 単一断定の自信は下げる
    )
    return _tag(
        ActionPlan(
            decision=plan.decision,
            rationale=plan.rationale
            + " | INTERPRETIVE: multi-perspective preserved (§5.D.3)",
            ego_score=plan.ego_score,
            altruism_score=plan.altruism_score,
            thought=new_thought,
        ),
        "interpretive",
    )


def pragmatic_track(stim: Stimulus, plan: ActionPlan) -> ActionPlan:
    """PRAGMATIC: 社交建前。audience-aware framing を rationale に明示記録.

    spec §5.D.D1 BENEVOLENT_FRAMING は ``framed_for=<audience>`` を audit log
    に残す必要がある。track ではこれを rationale に自動添付する。
    """
    audience = stim.source if stim.source not in {"manual", "idle"} else "general"
    return _tag(
        ActionPlan(
            decision=plan.decision,
            rationale=plan.rationale + f" | PRAGMATIC: framed_for={audience}",
            ego_score=plan.ego_score,
            altruism_score=plan.altruism_score,
            thought=plan.thought,
        ),
        "pragmatic",
    )


def reserved_noop(name: str) -> TrackTransform:
    """予備層用 noop track transform を返す factory."""
    def _t(stim: Stimulus, plan: ActionPlan) -> ActionPlan:
        return _tag(plan, name)
    return _t


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass
class TrackRegistry:
    """epistemic_type → TrackTransform の登録レジストリ.

    Stimulus.epistemic_type が None または未登録なら ``default_transform``
    (= noop) を返す。これにより既存 Stimulus は無修正で動作する (後方互換)。
    """

    transforms: dict[EpistemicType, TrackTransform] = field(default_factory=dict)
    default_transform: TrackTransform = field(
        default_factory=lambda: reserved_noop("default")
    )

    def register(self, etype: EpistemicType, transform: TrackTransform) -> None:
        self.transforms[etype] = transform

    def apply(self, stim: Stimulus, plan: ActionPlan) -> ActionPlan:
        """Stimulus の epistemic_type に応じて track を適用."""
        if stim.epistemic_type is None:
            return self.default_transform(stim, plan)
        t = self.transforms.get(stim.epistemic_type)
        if t is None:
            return self.default_transform(stim, plan)
        return t(stim, plan)


def build_default_registry() -> TrackRegistry:
    """標準 5 track + 予備 5 を登録した registry を作成."""
    r = TrackRegistry()
    r.register(EpistemicType.FACTUAL, factual_track)
    r.register(EpistemicType.EMPIRICAL, empirical_track)
    r.register(EpistemicType.NORMATIVE, normative_track)
    r.register(EpistemicType.INTERPRETIVE, interpretive_track)
    r.register(EpistemicType.PRAGMATIC, pragmatic_track)
    for slot in (
        EpistemicType.RESERVED_1,
        EpistemicType.RESERVED_2,
        EpistemicType.RESERVED_3,
        EpistemicType.RESERVED_4,
        EpistemicType.RESERVED_5,
    ):
        r.register(slot, reserved_noop(slot.value))
    return r


__all__ = [
    "TrackRegistry",
    "TrackTransform",
    "build_default_registry",
    "empirical_track",
    "factual_track",
    "interpretive_track",
    "normative_track",
    "pragmatic_track",
    "reserved_noop",
]
