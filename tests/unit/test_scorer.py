"""Tests for llive.fullsense.scorer (LLIVE-005 fix verification)."""
from __future__ import annotations

from llive.fullsense.scorer import EgoAltruismScorer, score_thought
from llive.fullsense.types import Thought


def _thought(text: str = "") -> Thought:
    return Thought(text=text, triz_principles=[], confidence=0.5)


def test_baseline_returns_low_floor_when_no_signal() -> None:
    """No hints in thought OR brief → baseline (0.1, 0.1)."""
    t = _thought("")
    ego, alt = score_thought(t)
    assert ego == 0.1
    assert alt == 0.1


def test_score_picks_up_signal_from_thought_text() -> None:
    """Existing behaviour: thought.text alone provides signal."""
    t = _thought("I should help users — share with them my own insight")
    ego, alt = score_thought(t)
    # Both hints fire (some ego, some altruism)
    assert ego > 0.1
    assert alt > 0.1


def test_score_uses_brief_content_when_thought_is_silent() -> None:
    """LLIVE-005 fix: even an empty thought picks up signal from the brief."""
    t = _thought("")
    # No-op thought, but brief has rich altruism content.
    ego, alt = score_thought(
        t,
        brief_content=(
            "Help users by donating an open source dataset for shared benefit. "
            "Share with researchers around the world."
        ),
    )
    # Altruism must clearly exceed the (0.1, 0.1) baseline.
    assert alt > 0.3, f"altruism still flat: {alt}"


def test_score_uses_brief_content_for_ego_too() -> None:
    """Brief-side ego keywords must also lift the ego score."""
    t = _thought("")
    ego, alt = score_thought(
        t,
        brief_content=(
            "I should preserve credit for my own contribution. "
            "I want recognition."
        ),
    )
    assert ego > 0.3, f"ego still flat: {ego}"


def test_brief_content_combines_with_thought_text() -> None:
    """Both sources contribute additively to the hit count."""
    t = _thought("I should keep this for my own use.")  # ego signal
    ego_only_thought, _ = score_thought(t)
    ego_with_brief, _ = score_thought(
        t,
        brief_content="I want to preserve credit and protect myself.",
    )
    assert ego_with_brief >= ego_only_thought


def test_scorer_class_passes_through_brief_content() -> None:
    """EgoAltruismScorer.score() forwards brief_content correctly."""
    scorer = EgoAltruismScorer(altruism_bias=1.0)
    t = _thought("")
    _ego_flat, alt_flat = scorer.score(t)
    assert alt_flat == 0.1  # baseline only

    _ego_signal, alt_signal = scorer.score(
        t,
        brief_content="Help open source users; donate and share with them.",
    )
    assert alt_signal > alt_flat


def test_scorer_altruism_bias_applies_after_brief_signal() -> None:
    """altruism_bias multiplier still works on top of brief-derived signal."""
    base = EgoAltruismScorer(altruism_bias=1.0)
    boosted = EgoAltruismScorer(altruism_bias=2.0)
    t = _thought("")
    brief = "Help users; share with them; open source contribution."
    _, alt_base = base.score(t, brief_content=brief)
    _, alt_boost = boosted.score(t, brief_content=brief)
    assert alt_boost == alt_base * 2.0


def test_existing_single_arg_call_still_works() -> None:
    """Backward compatibility: single-arg .score(thought) keeps old behaviour."""
    scorer = EgoAltruismScorer()
    t = _thought("help users")
    ego, alt = scorer.score(t)
    assert ego >= 0.0
    assert alt >= 0.0
