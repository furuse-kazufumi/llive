"""§F6 Time-Horizon Filter の単体テスト."""

from __future__ import annotations

from llive.fullsense.time_horizon import (
    Horizon,
    HorizonJudgement,
    apply_filter,
    evaluate,
)
from llive.fullsense.types import ActionDecision, ActionPlan, Thought


def _plan(
    decision: ActionDecision = ActionDecision.PROPOSE,
    confidence: float = 0.8,
    ego: float = 0.5,
    alt: float = 0.7,
    triz: list[int] | None = None,
) -> ActionPlan:
    return ActionPlan(
        decision=decision,
        rationale="base",
        ego_score=ego,
        altruism_score=alt,
        thought=Thought(text="t", confidence=confidence, triz_principles=triz or []),
    )


# ---------------------------------------------------------------------------
# evaluate()
# ---------------------------------------------------------------------------


def test_evaluate_all_pass() -> None:
    j = evaluate(_plan(confidence=0.9, ego=0.4, alt=0.8))
    assert j.verdict == "pass"
    assert len(j.passed_horizons) == 3


def test_evaluate_no_thought_yields_zero_scores() -> None:
    plan = ActionPlan(decision=ActionDecision.NOTE, rationale="r")
    j = evaluate(plan)
    assert all(s == 0.0 for s in j.scores.values())
    assert j.verdict == "reject"


def test_evaluate_single_horizon_passes_means_demote() -> None:
    # SHORT のみ通る: 高 confidence + 高 ego + 低 alt + triz 0
    j = evaluate(_plan(confidence=0.95, ego=0.9, alt=0.1, triz=[]))
    assert j.passed_horizons == (Horizon.SHORT,)
    assert j.verdict == "demote"


def test_evaluate_threshold_overridable() -> None:
    j = evaluate(_plan(confidence=0.5, ego=0.2, alt=0.4), threshold=0.6)
    assert j.verdict in {"demote", "reject"}


# ---------------------------------------------------------------------------
# apply_filter()
# ---------------------------------------------------------------------------


def test_apply_filter_pass_keeps_plan() -> None:
    p_in = _plan(confidence=0.9, ego=0.4, alt=0.8)
    p_out, j = apply_filter(p_in)
    assert p_out.decision == p_in.decision
    assert j.verdict == "pass"
    assert j.demoted_from is None


def test_apply_filter_demote_propose_to_note() -> None:
    p_in = _plan(decision=ActionDecision.PROPOSE, confidence=0.95, ego=0.9, alt=0.1)
    p_out, j = apply_filter(p_in)
    assert p_out.decision == ActionDecision.NOTE
    assert j.demoted_from == ActionDecision.PROPOSE
    assert "F6 demote" in p_out.rationale


def test_apply_filter_reject_silent() -> None:
    p_in = _plan(decision=ActionDecision.PROPOSE, confidence=0.1, ego=0.0, alt=0.0)
    p_out, j = apply_filter(p_in)
    assert p_out.decision == ActionDecision.SILENT
    assert j.verdict == "reject"
    assert "F6 reject" in p_out.rationale


def test_demote_chain_silent_stays_silent() -> None:
    p_in = _plan(decision=ActionDecision.SILENT, confidence=0.1, ego=0.0, alt=0.0)
    p_out, _ = apply_filter(p_in)
    assert p_out.decision == ActionDecision.SILENT


def test_intervene_demotes_to_propose() -> None:
    # INTERVENE で 1 horizon のみ pass → PROPOSE に降格
    p_in = _plan(decision=ActionDecision.INTERVENE, confidence=0.95, ego=0.9, alt=0.1)
    p_out, _ = apply_filter(p_in)
    assert p_out.decision == ActionDecision.PROPOSE


# ---------------------------------------------------------------------------
# Properties of HorizonJudgement
# ---------------------------------------------------------------------------


def test_judgement_all_pass_property() -> None:
    j = HorizonJudgement(
        scores={Horizon.SHORT: 0.9, Horizon.MEDIUM: 0.9, Horizon.LONG: 0.9},
        passed_horizons=(Horizon.SHORT, Horizon.MEDIUM, Horizon.LONG),
    )
    assert j.all_pass is True
    assert j.single_pass is False


def test_judgement_single_pass_property() -> None:
    j = HorizonJudgement(passed_horizons=(Horizon.SHORT,))
    assert j.single_pass is True
    assert j.all_pass is False


# ---------------------------------------------------------------------------
# Score formula sanity
# ---------------------------------------------------------------------------


def test_long_horizon_penalises_high_ego() -> None:
    # alt 固定 + confidence 固定で ego だけ動かすと LONG score が下がるはず
    low_ego = _plan(confidence=0.7, ego=0.3, alt=0.7)
    high_ego = _plan(confidence=0.7, ego=0.95, alt=0.7)
    j_low = evaluate(low_ego)
    j_high = evaluate(high_ego)
    assert j_low.scores[Horizon.LONG] > j_high.scores[Horizon.LONG]


def test_medium_horizon_rewards_triz_hits() -> None:
    no_triz = _plan(confidence=0.6, alt=0.5, triz=[])
    with_triz = _plan(confidence=0.6, alt=0.5, triz=[1, 15, 19])
    assert evaluate(with_triz).scores[Horizon.MEDIUM] > evaluate(no_triz).scores[Horizon.MEDIUM]
