# SPDX-License-Identifier: Apache-2.0
"""Multi-track Filter Architecture (A-1.5) の単体テスト.

- 各標準 track が ActionPlan を変換し、[track:<name>] tag を rationale に付与
- INTERPRETIVE で multi-perspective が thought.text に展開
- FACTUAL の strict confidence 降格 (< 0.7 → SILENT)
- NORMATIVE の ego 優位 → SILENT 降格
- PRAGMATIC の framed_for=<audience> が rationale に明示
- 予備層 RESERVED_1..5 は noop だが tag だけ付く
- Registry: epistemic_type=None は default、未登録 type も default
"""

from __future__ import annotations

from llive.fullsense.tracks import (
    TrackRegistry,
    build_default_registry,
    empirical_track,
    factual_track,
    interpretive_track,
    normative_track,
    pragmatic_track,
    reserved_noop,
)
from llive.fullsense.types import (
    ActionDecision,
    ActionPlan,
    EpistemicType,
    Stimulus,
    Thought,
)


def _stim(content: str = "x", source: str = "manual", et: EpistemicType | None = None) -> Stimulus:
    return Stimulus(content=content, source=source, surprise=0.9, epistemic_type=et)


def _plan(
    confidence: float = 0.8,
    ego: float = 0.3,
    alt: float = 0.5,
    decision: ActionDecision = ActionDecision.NOTE,
    text: str = "thought",
    triz: list[int] | None = None,
) -> ActionPlan:
    return ActionPlan(
        decision=decision,
        rationale="base reason",
        ego_score=ego,
        altruism_score=alt,
        thought=Thought(text=text, confidence=confidence, triz_principles=triz or []),
    )


# ---------------------------------------------------------------------------
# Default registry behaviour
# ---------------------------------------------------------------------------


def test_registry_default_when_epistemic_type_is_none() -> None:
    r = build_default_registry()
    stim = _stim(et=None)
    plan = r.apply(stim, _plan())
    assert "[track:default]" in plan.rationale


def test_registry_default_when_type_unregistered() -> None:
    r = TrackRegistry()  # 空 registry
    stim = _stim(et=EpistemicType.FACTUAL)
    plan = r.apply(stim, _plan())
    assert "[track:default]" in plan.rationale


# ---------------------------------------------------------------------------
# FACTUAL — strict confidence
# ---------------------------------------------------------------------------


def test_factual_allows_high_confidence() -> None:
    plan = factual_track(_stim(), _plan(confidence=0.9))
    assert "[track:factual]" in plan.rationale
    assert plan.decision is not ActionDecision.SILENT


def test_factual_demotes_low_confidence_to_silent() -> None:
    plan = factual_track(_stim(), _plan(confidence=0.5, decision=ActionDecision.PROPOSE))
    assert plan.decision is ActionDecision.SILENT
    assert "FACTUAL strict" in plan.rationale
    assert "[track:factual]" in plan.rationale


# ---------------------------------------------------------------------------
# EMPIRICAL — CI annotation
# ---------------------------------------------------------------------------


def test_empirical_annotates_confidence_interval() -> None:
    plan = empirical_track(_stim(), _plan(confidence=0.8, text="evidence-X"))
    assert "[track:empirical]" in plan.rationale
    assert plan.thought is not None
    assert "CI95" in plan.thought.text


def test_empirical_no_thought_keeps_tag_only() -> None:
    bare = ActionPlan(decision=ActionDecision.SILENT, rationale="r")
    plan = empirical_track(_stim(), bare)
    assert "[track:empirical]" in plan.rationale


# ---------------------------------------------------------------------------
# NORMATIVE — ego dominance check
# ---------------------------------------------------------------------------


def test_normative_demotes_ego_dominant() -> None:
    plan = normative_track(_stim(), _plan(ego=0.8, alt=0.3))
    assert plan.decision is ActionDecision.SILENT
    assert "ego dominates" in plan.rationale
    assert "[track:normative]" in plan.rationale


def test_normative_allows_altruism_dominant() -> None:
    plan = normative_track(_stim(), _plan(ego=0.2, alt=0.8))
    assert plan.decision is not ActionDecision.SILENT
    assert "[track:normative]" in plan.rationale


# ---------------------------------------------------------------------------
# INTERPRETIVE — multi-perspective preservation (§5.D.3)
# ---------------------------------------------------------------------------


def test_interpretive_injects_multi_perspective() -> None:
    plan = interpretive_track(_stim(), _plan(text="claim X"))
    assert plan.thought is not None
    assert "perspectives" in plan.thought.text
    assert "frame A" in plan.thought.text
    assert "frame B" in plan.thought.text
    assert "[track:interpretive]" in plan.rationale
    assert "multi-perspective" in plan.rationale


def test_interpretive_no_thought_only_tags() -> None:
    bare = ActionPlan(decision=ActionDecision.NOTE, rationale="r")
    plan = interpretive_track(_stim(), bare)
    assert "[track:interpretive]" in plan.rationale


# ---------------------------------------------------------------------------
# PRAGMATIC — framed_for audit (§5.D.D1)
# ---------------------------------------------------------------------------


def test_pragmatic_records_audience_from_source() -> None:
    plan = pragmatic_track(_stim(source="customer"), _plan())
    assert "[track:pragmatic]" in plan.rationale
    assert "framed_for=customer" in plan.rationale


def test_pragmatic_generalises_idle_or_manual_source() -> None:
    plan = pragmatic_track(_stim(source="idle"), _plan())
    assert "framed_for=general" in plan.rationale
    plan2 = pragmatic_track(_stim(source="manual"), _plan())
    assert "framed_for=general" in plan2.rationale


# ---------------------------------------------------------------------------
# Reserved layers (将来拡張用予備層)
# ---------------------------------------------------------------------------


def test_reserved_tracks_are_noop_with_tag() -> None:
    r = build_default_registry()
    for et in (
        EpistemicType.RESERVED_1,
        EpistemicType.RESERVED_2,
        EpistemicType.RESERVED_3,
        EpistemicType.RESERVED_4,
        EpistemicType.RESERVED_5,
    ):
        stim = _stim(et=et)
        plan = r.apply(stim, _plan())
        assert f"[track:{et.value}]" in plan.rationale


# ---------------------------------------------------------------------------
# Registry: 5 標準 track が登録済み
# ---------------------------------------------------------------------------


def test_default_registry_has_all_standard_tracks() -> None:
    r = build_default_registry()
    for et in (
        EpistemicType.FACTUAL,
        EpistemicType.EMPIRICAL,
        EpistemicType.NORMATIVE,
        EpistemicType.INTERPRETIVE,
        EpistemicType.PRAGMATIC,
    ):
        assert et in r.transforms


def test_double_tag_does_not_stack() -> None:
    """同じ tag を二重適用しても rationale が膨らまない."""
    stim = _stim()
    p1 = factual_track(stim, _plan(confidence=0.9))
    p2 = factual_track(stim, p1)
    # 1 回だけ tag が付くこと
    assert p2.rationale.count("[track:factual]") == 1


def test_register_overrides_existing() -> None:
    r = build_default_registry()
    r.register(EpistemicType.FACTUAL, reserved_noop("override"))
    stim = _stim(et=EpistemicType.FACTUAL)
    plan = r.apply(stim, _plan(confidence=0.5))
    # override は noop なので SILENT に降格しない
    assert plan.decision is not ActionDecision.SILENT
    assert "[track:override]" in plan.rationale
