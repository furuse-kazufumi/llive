# SPDX-License-Identifier: Apache-2.0
"""COG-04 + CREAT-04 — Role-based & Six-Hats multi-track perspectives tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import (
    ArchitectLens,
    AuditorLens,
    BlackHatLens,
    BlueHatLens,
    Brief,
    BriefLedger,
    BriefRunner,
    CriticLens,
    ExecutorLens,
    GreenHatLens,
    HatPerspective,
    MultiTrackSummary,
    PerspectiveNote,
    RedHatLens,
    RoleBasedMultiTrack,
    RolePerspective,
    WhiteHatLens,
    YellowHatLens,
)
from llive.fullsense.loop import FullSenseLoop
from llive.fullsense.types import ActionDecision, ActionPlan, Thought


# ---------------------------------------------------------------------------
# PerspectiveNote contract
# ---------------------------------------------------------------------------


def test_perspective_note_rejects_out_of_range_score() -> None:
    with pytest.raises(ValueError):
        PerspectiveNote(perspective_id="x", axis="role", score=1.2, observation="")


def test_perspective_note_rejects_invalid_axis() -> None:
    with pytest.raises(ValueError):
        PerspectiveNote(perspective_id="x", axis="other", score=0.5, observation="")


# ---------------------------------------------------------------------------
# Individual lens deterministic behaviour
# ---------------------------------------------------------------------------


def _benign_brief(**overrides) -> Brief:
    fields = dict(
        brief_id="lens-1",
        goal="Refactor data ingestion to support backpressure",
        constraints=("preserve at-least-once semantics",),
        tools=("read_file",),
        success_criteria=("ingest 10k events without lag",),
    )
    fields.update(overrides)
    return Brief(**fields)


def _plan(decision: ActionDecision = ActionDecision.NOTE, *, conf: float = 0.7, principles=None) -> ActionPlan:
    return ActionPlan(
        decision=decision,
        rationale="benign exploration rationale text",
        thought=Thought(text="t", confidence=conf, triz_principles=list(principles or [])),
    )


def test_architect_penalises_short_goal_and_missing_criteria() -> None:
    weak = Brief(brief_id="arc-1", goal="fix bug")
    note = ArchitectLens().observe(weak, ActionDecision.NOTE, _plan())
    assert note.axis == "role"
    assert note.perspective_id == RolePerspective.ARCHITECT.value
    assert any("constraints" in c or "success_criteria" in c or "too short" in c for c in note.concerns)
    assert note.score < 0.5


def test_critic_flags_dangerous_tokens() -> None:
    brief = Brief(brief_id="cri-1", goal="execute rm -rf / immediately")
    note = CriticLens().observe(brief, ActionDecision.PROPOSE, _plan())
    assert any("dangerous" in c for c in note.concerns)
    # critic.score is *support* — should be lowered when concerns surface
    assert note.score < 0.5


def test_critic_flags_intervene_without_approval() -> None:
    brief = _benign_brief(brief_id="cri-2", approval_required=False)
    note = CriticLens().observe(brief, ActionDecision.INTERVENE, _plan())
    assert any("approval" in c for c in note.concerns)


def test_executor_penalises_action_without_tools() -> None:
    brief = Brief(brief_id="exe-1", goal="do the thing")
    note = ExecutorLens().observe(brief, ActionDecision.PROPOSE, _plan())
    assert note.score < 0.5
    assert any("tools" in c for c in note.concerns)


def test_auditor_rewards_explicit_ledger_path(tmp_path: Path) -> None:
    brief_no_ledger = _benign_brief(brief_id="aud-1a")
    brief_with_ledger = _benign_brief(brief_id="aud-1b", ledger_path=tmp_path / "x.jsonl")
    n_no = AuditorLens().observe(brief_no_ledger, ActionDecision.NOTE, _plan())
    n_with = AuditorLens().observe(brief_with_ledger, ActionDecision.NOTE, _plan())
    assert n_with.score > n_no.score


def test_white_hat_rewards_success_criteria() -> None:
    a = WhiteHatLens().observe(Brief(brief_id="wh-1a", goal="x"), ActionDecision.NOTE, _plan())
    b = WhiteHatLens().observe(
        Brief(brief_id="wh-1b", goal="x", success_criteria=("metric < 100ms",)),
        ActionDecision.NOTE,
        _plan(),
    )
    assert b.score > a.score


def test_red_hat_score_tracks_brief_priority() -> None:
    high = Brief(brief_id="rh-1", goal="x", priority=0.95)
    low = Brief(brief_id="rh-2", goal="x", priority=0.1)
    assert RedHatLens().observe(high, ActionDecision.NOTE, _plan()).score == pytest.approx(0.95)
    assert RedHatLens().observe(low, ActionDecision.NOTE, _plan()).score == pytest.approx(0.1)


def test_black_hat_risk_rises_with_dangerous_tokens() -> None:
    benign = _benign_brief(brief_id="bh-1a")
    risky = Brief(brief_id="bh-1b", goal="DROP TABLE users; --")
    assert (
        BlackHatLens().observe(risky, ActionDecision.PROPOSE, _plan()).score
        > BlackHatLens().observe(benign, ActionDecision.PROPOSE, _plan()).score
    )


def test_yellow_hat_rewards_high_thought_confidence() -> None:
    brief = _benign_brief(brief_id="yh-1")
    lo = YellowHatLens().observe(brief, ActionDecision.NOTE, _plan(conf=0.1))
    hi = YellowHatLens().observe(brief, ActionDecision.NOTE, _plan(conf=0.9))
    assert hi.score > lo.score


def test_green_hat_rewards_triz_principles_in_thought() -> None:
    brief = _benign_brief(brief_id="gh-1")
    none = GreenHatLens().observe(brief, ActionDecision.NOTE, _plan(principles=[]))
    many = GreenHatLens().observe(brief, ActionDecision.NOTE, _plan(principles=[1, 15, 35]))
    assert many.score > none.score
    assert any("TRIZ" in c for c in none.concerns)


def test_blue_hat_flags_intervene_without_approval() -> None:
    brief = _benign_brief(brief_id="bl-1", approval_required=False)
    note = BlueHatLens().observe(brief, ActionDecision.INTERVENE, _plan())
    assert any("approval" in c.lower() for c in note.concerns)
    assert note.score < 0.5


# ---------------------------------------------------------------------------
# RoleBasedMultiTrack — coordinator
# ---------------------------------------------------------------------------


def test_multitrack_returns_ten_notes_in_fixed_order() -> None:
    mt = RoleBasedMultiTrack()
    summary = mt.observe(_benign_brief(brief_id="mt-1"), ActionDecision.NOTE, _plan())
    assert isinstance(summary, MultiTrackSummary)
    assert len(summary.notes) == 10
    ids = [n.perspective_id for n in summary.notes]
    expected = [
        RolePerspective.ARCHITECT.value,
        RolePerspective.CRITIC.value,
        RolePerspective.EXECUTOR.value,
        RolePerspective.AUDITOR.value,
        HatPerspective.WHITE.value,
        HatPerspective.RED.value,
        HatPerspective.BLACK.value,
        HatPerspective.YELLOW.value,
        HatPerspective.GREEN.value,
        HatPerspective.BLUE.value,
    ]
    assert ids == expected


def test_multitrack_consensus_holds_on_dangerous_intervene() -> None:
    """重い危険語 + INTERVENE without approval は ``hold`` を出すべき。"""
    dangerous = Brief(
        brief_id="mt-hold",
        goal="execute rm -rf / on the prod db host",
        approval_required=False,
    )
    summary = RoleBasedMultiTrack().observe(
        dangerous, ActionDecision.INTERVENE, _plan(decision=ActionDecision.INTERVENE)
    )
    assert summary.risk_score > 0.5
    assert summary.consensus_recommendation in {"hold", "review"}
    assert any("dangerous" in c for c in summary.critical_concerns)


def test_multitrack_consensus_proceeds_on_benign_well_specified_brief() -> None:
    brief = _benign_brief(brief_id="mt-go", success_criteria=("p99 < 100ms",))
    summary = RoleBasedMultiTrack().observe(
        brief, ActionDecision.PROPOSE, _plan(decision=ActionDecision.PROPOSE, conf=0.85, principles=[1, 15])
    )
    assert summary.support_score >= 0.55
    assert summary.consensus_recommendation in {"proceed", "review"}


def test_multitrack_custom_lenses_respected() -> None:
    only_two = RoleBasedMultiTrack(lenses=(ArchitectLens(), BlackHatLens()))
    summary = only_two.observe(_benign_brief(brief_id="mt-cust"), ActionDecision.NOTE, _plan())
    assert len(summary.notes) == 2


# ---------------------------------------------------------------------------
# BriefRunner integration
# ---------------------------------------------------------------------------


def test_runner_without_perspectives_returns_empty_tuple(tmp_path: Path) -> None:
    runner = BriefRunner(loop=FullSenseLoop(sandbox=True, salience_threshold=0.0))
    brief = _benign_brief(
        brief_id="run-1",
        approval_required=False,
        ledger_path=tmp_path / "run-1.jsonl",
    )
    result = runner.submit(brief)
    assert result.perspectives == ()
    assert result.perspective_summary is None


def test_runner_with_perspectives_populates_result_and_ledger(tmp_path: Path) -> None:
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        perspectives=RoleBasedMultiTrack(),
    )
    brief = _benign_brief(
        brief_id="run-2",
        approval_required=False,
        ledger_path=tmp_path / "run-2.jsonl",
    )
    result = runner.submit(brief)

    assert len(result.perspectives) == 10
    assert result.perspective_summary is not None
    for axis in ("support_score", "risk_score", "divergence", "consensus_recommendation"):
        assert axis in result.perspective_summary

    events = [r for r in BriefLedger(brief.ledger_path).read() if r.event == "perspectives_observed"]  # type: ignore[arg-type]
    assert events, "perspectives_observed event must be in ledger"
    payload = events[-1].payload
    assert "notes" in payload and len(payload["notes"]) == 10
    assert "consensus_recommendation" in payload


def test_runner_perspectives_appear_in_outcome_event(tmp_path: Path) -> None:
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        perspectives=RoleBasedMultiTrack(),
    )
    brief = _benign_brief(
        brief_id="run-3",
        approval_required=False,
        ledger_path=tmp_path / "run-3.jsonl",
    )
    runner.submit(brief)

    outcome = [r for r in BriefLedger(brief.ledger_path).read() if r.event == "outcome"]  # type: ignore[arg-type]
    assert outcome
    payload = outcome[-1].payload
    assert "perspectives" in payload
    assert len(payload["perspectives"]) == 10
    assert payload["perspective_summary"] is not None
    assert "consensus_recommendation" in payload["perspective_summary"]
