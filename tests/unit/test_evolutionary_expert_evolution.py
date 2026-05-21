# SPDX-License-Identifier: Apache-2.0
"""ExpertCompositionEvolution + SurvivalRateTracking (v0.E CE-16/17) tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    CompositionStat,
    ExpertCompositionGenome,
    ExpertCompositionMutation,
    SurvivalRateTracker,
)


# ---------------------------------------------------------------------------
# 1. ExpertCompositionGenome validation
# ---------------------------------------------------------------------------


def test_genome_basic() -> None:
    g = ExpertCompositionGenome(
        persona_ids=("oka-kiyoshi", "feynman"),
    )
    assert g.protocol == "weighted_average"
    assert g.moderator_index == 0


def test_genome_rejects_empty() -> None:
    with pytest.raises(ValueError, match="persona_ids"):
        ExpertCompositionGenome(persona_ids=())


def test_genome_rejects_duplicate() -> None:
    with pytest.raises(ValueError, match="unique"):
        ExpertCompositionGenome(
            persona_ids=("oka-kiyoshi", "oka-kiyoshi"),
        )


def test_genome_rejects_unknown_persona() -> None:
    with pytest.raises(ValueError, match="unknown persona_id"):
        ExpertCompositionGenome(persona_ids=("bogus",))


def test_genome_rejects_unknown_protocol() -> None:
    with pytest.raises(ValueError, match="unknown protocol"):
        ExpertCompositionGenome(
            persona_ids=("oka-kiyoshi",),
            protocol="debate",  # type: ignore[arg-type]
        )


def test_genome_rejects_invalid_moderator() -> None:
    with pytest.raises(ValueError, match="moderator_index"):
        ExpertCompositionGenome(
            persona_ids=("oka-kiyoshi",),
            moderator_index=5,
        )


def test_signature_deterministic() -> None:
    g1 = ExpertCompositionGenome(persona_ids=("oka-kiyoshi", "feynman"))
    g2 = ExpertCompositionGenome(persona_ids=("feynman", "oka-kiyoshi"))
    # order 違いでも同じ signature
    assert g1.signature() == g2.signature()


def test_signature_includes_protocol() -> None:
    g1 = ExpertCompositionGenome(
        persona_ids=("oka-kiyoshi",), protocol="weighted_average"
    )
    g2 = ExpertCompositionGenome(persona_ids=("oka-kiyoshi",), protocol="veto")
    assert g1.signature() != g2.signature()


def test_to_panel() -> None:
    g = ExpertCompositionGenome(persona_ids=("oka-kiyoshi", "feynman"))
    panel = g.to_panel()
    assert panel.size == 2


# ---------------------------------------------------------------------------
# 2. ExpertCompositionMutation
# ---------------------------------------------------------------------------


def test_mutation_returns_valid_genome() -> None:
    g = ExpertCompositionGenome(persona_ids=("oka-kiyoshi", "feynman"))
    mut = ExpertCompositionMutation()
    rng = np.random.default_rng(0)
    for _ in range(20):
        g = mut(g, rng)
        # 妥当な genome のまま
        assert len(set(g.persona_ids)) == len(g.persona_ids)
        assert g.protocol in ("weighted_average", "round_robin", "moderator_vote", "veto")
        assert 0 <= g.moderator_index < len(g.persona_ids)


def test_mutation_respects_min_max() -> None:
    g = ExpertCompositionGenome(persona_ids=("oka-kiyoshi", "feynman"))
    mut = ExpertCompositionMutation(
        p_swap=0.0,
        p_add=1.0,
        p_remove=1.0,
        p_change_protocol=0.0,
        p_shift_moderator=0.0,
        min_personas=1,
        max_personas=3,
    )
    rng = np.random.default_rng(0)
    for _ in range(50):
        g = mut(g, rng)
        assert 1 <= len(g.persona_ids) <= 3


def test_mutation_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="probabilities"):
        ExpertCompositionMutation(p_swap=1.5)
    with pytest.raises(ValueError, match="min_personas"):
        ExpertCompositionMutation(min_personas=0)
    with pytest.raises(ValueError, match="max_personas"):
        ExpertCompositionMutation(min_personas=5, max_personas=2)


def test_mutation_protocol_changes() -> None:
    """p_change_protocol=1.0 で多くの呼び出しで protocol が変化する."""
    g = ExpertCompositionGenome(persona_ids=("oka-kiyoshi",))
    mut = ExpertCompositionMutation(
        p_swap=0.0, p_add=0.0, p_remove=0.0,
        p_change_protocol=1.0, p_shift_moderator=0.0,
    )
    rng = np.random.default_rng(0)
    protocols_seen = set()
    for _ in range(20):
        g = mut(g, rng)
        protocols_seen.add(g.protocol)
    assert len(protocols_seen) >= 2


# ---------------------------------------------------------------------------
# 3. SurvivalRateTracker
# ---------------------------------------------------------------------------


def test_tracker_first_observation() -> None:
    t = SurvivalRateTracker()
    t.observe(0, ["sig_a"])
    assert "sig_a" in t.stats
    assert t.stats["sig_a"].first_seen_generation == 0
    assert t.stats["sig_a"].survived_generations == 1
    assert t.stats["sig_a"].current_streak == 1


def test_tracker_consecutive_appearances() -> None:
    t = SurvivalRateTracker()
    t.observe(0, ["sig_a"])
    t.observe(1, ["sig_a"])
    t.observe(2, ["sig_a"])
    assert t.stats["sig_a"].current_streak == 3
    assert t.stats["sig_a"].survived_generations == 3


def test_tracker_broken_streak() -> None:
    t = SurvivalRateTracker()
    t.observe(0, ["sig_a"])
    t.observe(1, ["sig_a"])
    t.observe(2, ["sig_b"])  # sig_a 不在
    t.observe(3, ["sig_a"])
    assert t.stats["sig_a"].survived_generations == 2  # max streak 維持
    assert t.stats["sig_a"].current_streak == 1


def test_tracker_score_aggregation() -> None:
    t = SurvivalRateTracker()
    t.observe(0, ["sig_a"], scores=[0.5])
    t.observe(1, ["sig_a"], scores=[0.7])
    assert t.stats["sig_a"].score_samples == 2
    assert t.stats["sig_a"].mean_score() == pytest.approx(0.6, abs=1e-6)


def test_tracker_score_length_mismatch() -> None:
    t = SurvivalRateTracker()
    with pytest.raises(ValueError, match="scores length"):
        t.observe(0, ["sig_a", "sig_b"], scores=[0.5])


def test_tracker_top_signatures_by_streak() -> None:
    t = SurvivalRateTracker()
    t.observe(0, ["a", "b"])
    t.observe(1, ["a"])
    t.observe(2, ["a"])
    t.observe(3, ["b"])
    top = t.top_signatures(k=2, by="survived_generations")
    assert top[0].signature == "a"
    assert top[0].survived_generations == 3


def test_tracker_top_signatures_by_mean_score() -> None:
    t = SurvivalRateTracker()
    t.observe(0, ["a"], scores=[0.9])
    t.observe(1, ["b"], scores=[0.1])
    top = t.top_signatures(k=2, by="mean_score")
    assert top[0].signature == "a"


def test_tracker_top_unknown_key_raises() -> None:
    t = SurvivalRateTracker()
    t.observe(0, ["a"])
    with pytest.raises(ValueError, match="unknown sort key"):
        t.top_signatures(by="bogus")


def test_tracker_to_dict_serializable() -> None:
    t = SurvivalRateTracker()
    t.observe(0, ["a"], scores=[0.5])
    t.observe(1, ["a"], scores=[0.7])
    d = t.to_dict()
    assert "a" in d
    assert d["a"]["mean_score"] == pytest.approx(0.6)
    assert d["a"]["appearances"] == 2
