# SPDX-License-Identifier: Apache-2.0
"""FullSense Loop — Sandbox-only MVP の smoke / unit tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from llive.fullsense import (
    ActionDecision,
    EgoAltruismScorer,
    FullSenseLoop,
    IdleTrigger,
    SandboxOutputBus,
    Stimulus,
)
from llive.fullsense.loop import _detect_triz_principles
from llive.fullsense.scorer import score_thought
from llive.fullsense.triggers import QueuedStimulusSource, drain
from llive.fullsense.types import Thought

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


def test_stimulus_default_id_is_unique() -> None:
    s1 = Stimulus(content="x")
    s2 = Stimulus(content="x")
    assert s1.stim_id != s2.stim_id


def test_action_decision_values() -> None:
    assert ActionDecision.SILENT.value == "silent"
    assert ActionDecision.NOTE.value == "note"
    assert ActionDecision.PROPOSE.value == "propose"
    assert ActionDecision.INTERVENE.value == "intervene"


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


def test_score_thought_neutral_returns_baseline() -> None:
    ego, alt = score_thought(Thought(text="some neutral observation"))
    assert 0.0 <= ego <= 1.0
    assert 0.0 <= alt <= 1.0
    assert abs(ego - alt) < 0.1


def test_score_thought_altruism_dominates_with_help_keywords() -> None:
    ego, alt = score_thought(Thought(text="users could benefit if we share with them"))
    assert alt > ego


def test_score_thought_ego_dominates_with_self_keywords() -> None:
    ego, alt = score_thought(Thought(text="I want to preserve my own credit"))
    assert ego > alt


def test_ego_altruism_scorer_bias() -> None:
    plain = EgoAltruismScorer(altruism_bias=1.0)
    boosted = EgoAltruismScorer(altruism_bias=2.0)
    t = Thought(text="help users share resources")
    _, alt_plain = plain.score(t)
    _, alt_boost = boosted.score(t)
    assert alt_boost > alt_plain


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------


def test_idle_trigger_does_not_fire_when_recent() -> None:
    trig = IdleTrigger(threshold_seconds=30.0)
    trig.mark_active()
    assert trig.poll() is None


def test_idle_trigger_fires_when_quiet() -> None:
    trig = IdleTrigger(threshold_seconds=0.05)
    time.sleep(0.06)
    s = trig.poll()
    assert s is not None
    assert s.source == "idle"


def test_idle_trigger_debounces() -> None:
    trig = IdleTrigger(threshold_seconds=0.05)
    time.sleep(0.06)
    first = trig.poll()
    assert first is not None
    second = trig.poll()
    # Same window — should debounce
    assert second is None


def test_queued_stimulus_source_drain() -> None:
    src = QueuedStimulusSource()
    src.add(Stimulus(content="a"))
    src.add(Stimulus(content="b"))
    items = list(drain(src))
    assert [s.content for s in items] == ["a", "b"]
    # Source now empty
    assert src.poll() is None


# ---------------------------------------------------------------------------
# TRIZ detector
# ---------------------------------------------------------------------------


def test_triz_detector_picks_up_tradeoff() -> None:
    assert 1 in _detect_triz_principles("we have a trade-off here")


def test_triz_detector_picks_up_periodic_idle() -> None:
    hits = _detect_triz_principles("idle periodic check")
    assert 19 in hits


def test_triz_detector_empty_text() -> None:
    assert _detect_triz_principles("") == []


# ---------------------------------------------------------------------------
# Sandbox bus
# ---------------------------------------------------------------------------


def test_sandbox_bus_records_in_memory() -> None:
    loop = FullSenseLoop()
    loop.process(Stimulus(content="hello world", surprise=0.9))
    assert len(loop.output_bus) == 1


def test_sandbox_bus_writes_jsonl_to_file(tmp_path: Path) -> None:
    log = tmp_path / "fs.jsonl"
    bus = SandboxOutputBus(log_path=log)
    loop = FullSenseLoop(output_bus=bus)
    loop.process(Stimulus(content="needs many tokens to pass salience gate", surprise=0.8))
    loop.process(Stimulus(content="another one", surprise=0.9))
    assert log.exists()
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    assert "decision" in lines[0]["plan"]


# ---------------------------------------------------------------------------
# Loop end-to-end
# ---------------------------------------------------------------------------


def test_loop_rejects_non_sandbox() -> None:
    with pytest.raises(ValueError, match="sandbox=True"):
        FullSenseLoop(sandbox=False)


def test_loop_low_surprise_yields_silent() -> None:
    loop = FullSenseLoop(salience_threshold=0.9)
    res = loop.process(Stimulus(content="trivial", surprise=0.1))
    assert res.plan.decision == ActionDecision.SILENT
    assert res.stages["salience"]["pass"] is False


def test_loop_high_surprise_traverses_all_stages() -> None:
    loop = FullSenseLoop(
        salience_threshold=0.3,
        curiosity_threshold=0.5,
    )
    res = loop.process(Stimulus(
        content="novel idea: trade-off between size and speed; periodic check",
        surprise=0.95,
    ))
    # All stages should be present
    for key in ("salience", "curiosity", "thought", "ego_score", "altruism_score"):
        assert key in res.stages
    # TRIZ principles should be detected
    assert res.plan.thought is not None
    assert 1 in res.plan.thought.triz_principles  # trade-off
    assert 19 in res.plan.thought.triz_principles  # periodic


def test_loop_known_corpus_reduces_curiosity() -> None:
    loop_unknown = FullSenseLoop(salience_threshold=0.0, curiosity_threshold=0.5)
    loop_known = FullSenseLoop(
        salience_threshold=0.0,
        curiosity_threshold=0.5,
        known_corpus={"buffer", "overflow", "stack"},
    )
    s = Stimulus(content="buffer overflow on the stack", surprise=0.9)
    r_unknown = loop_unknown.process(s)
    r_known = loop_known.process(s)
    cur_unknown = r_unknown.stages["curiosity"]["score"]
    cur_known = r_known.stages["curiosity"]["score"]
    assert cur_unknown > cur_known


def test_loop_altruism_dominant_yields_propose() -> None:
    loop = FullSenseLoop(salience_threshold=0.0)
    # Inject a stimulus whose generated thought will contain altruism hints
    res = loop.process(Stimulus(
        content="we should help users share with them via open source release",
        surprise=0.9,
    ))
    # Altruism should outweigh ego; depending on curiosity, decision could be PROPOSE or NOTE
    assert res.plan.decision in (ActionDecision.PROPOSE, ActionDecision.NOTE)


def test_loop_decision_never_intervene_in_sandbox_unless_explicit() -> None:
    # The MVP heuristic never emits INTERVENE on its own.
    loop = FullSenseLoop(salience_threshold=0.0)
    for content in ["random idea", "trade-off scenario", "user benefit thoughts"]:
        res = loop.process(Stimulus(content=content, surprise=0.9))
        assert res.plan.decision != ActionDecision.INTERVENE


def test_loop_full_pipeline_via_queued_source() -> None:
    src = QueuedStimulusSource()
    src.add(Stimulus(content="trivial", surprise=0.05))
    src.add(Stimulus(content="users could be helped by sharing this insight broadly", surprise=0.9))
    loop = FullSenseLoop(salience_threshold=0.4)
    results = [loop.process(s) for s in drain(src)]
    assert len(results) == 2
    assert results[0].plan.decision == ActionDecision.SILENT
    # Second one should at minimum NOT be silent
    assert results[1].plan.decision != ActionDecision.SILENT
