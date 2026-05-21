# SPDX-License-Identifier: Apache-2.0
"""PersonaSurvivalAnalysis (v0.E CE-22) — unit tests."""

from __future__ import annotations

import pytest

from llive.perf.evolutionary import PersonaComposition, PersonaSurvivalAnalysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(*ids: str) -> PersonaComposition:
    n = len(ids)
    return PersonaComposition(
        persona_ids=tuple(ids), weights=tuple(1.0 / n for _ in ids)
    )


# ---------------------------------------------------------------------------
# 1. signature
# ---------------------------------------------------------------------------


class TestSignature:
    def test_single_persona_signature(self) -> None:
        sig = PersonaSurvivalAnalysis.composition_signature(_comp("newton"))
        assert sig == "newton"

    def test_hybrid_signature_sorted(self) -> None:
        sig_ab = PersonaSurvivalAnalysis.composition_signature(
            _comp("newton", "feynman")
        )
        sig_ba = PersonaSurvivalAnalysis.composition_signature(
            _comp("feynman", "newton")
        )
        # 並び順に依存しない
        assert sig_ab == sig_ba == "feynman|newton"

    def test_three_persona_signature(self) -> None:
        sig = PersonaSurvivalAnalysis.composition_signature(
            _comp("newton", "feynman", "kant")
        )
        assert sig == "feynman|kant|newton"


# ---------------------------------------------------------------------------
# 2. observe_generation
# ---------------------------------------------------------------------------


class TestObserve:
    def test_empty_observe(self) -> None:
        a = PersonaSurvivalAnalysis()
        a.observe_generation(0, [])
        assert a.tracker.stats == {}

    def test_single_gen_observe(self) -> None:
        a = PersonaSurvivalAnalysis()
        a.observe_generation(
            0, [_comp("newton"), _comp("feynman"), _comp("newton")]
        )
        # newton 2 回, feynman 1 回
        assert "newton" in a.tracker.stats
        assert "feynman" in a.tracker.stats
        assert a.tracker.stats["newton"].appearances == 2
        assert a.tracker.stats["feynman"].appearances == 1

    def test_streak_grows(self) -> None:
        a = PersonaSurvivalAnalysis()
        for gen in range(3):
            a.observe_generation(gen, [_comp("newton")])
        assert a.tracker.stats["newton"].current_streak == 3
        assert a.tracker.stats["newton"].survived_generations == 3

    def test_streak_breaks(self) -> None:
        a = PersonaSurvivalAnalysis()
        a.observe_generation(0, [_comp("newton")])
        a.observe_generation(1, [_comp("feynman")])  # newton 消失
        assert a.tracker.stats["newton"].current_streak == 0
        assert a.tracker.stats["newton"].survived_generations == 1

    def test_scores_aggregate(self) -> None:
        a = PersonaSurvivalAnalysis()
        a.observe_generation(0, [_comp("newton")], scores=[0.5])
        a.observe_generation(1, [_comp("newton")], scores=[0.7])
        stat = a.tracker.stats["newton"]
        assert stat.mean_score() == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# 3. top_signatures
# ---------------------------------------------------------------------------


class TestTopSignatures:
    def test_top_by_appearances(self) -> None:
        a = PersonaSurvivalAnalysis()
        # newton 3 回, feynman 1 回
        a.observe_generation(
            0, [_comp("newton"), _comp("newton"), _comp("newton"), _comp("feynman")]
        )
        top = a.top_signatures(k=2, by="appearances")
        assert top[0].signature == "newton"
        assert top[0].appearances == 3
        assert top[1].signature == "feynman"

    def test_invalid_sort_key_raises(self) -> None:
        a = PersonaSurvivalAnalysis()
        a.observe_generation(0, [_comp("newton")])
        with pytest.raises(ValueError):
            a.top_signatures(by="bogus")


# ---------------------------------------------------------------------------
# 4. hybrid_distribution / appearance / ratio
# ---------------------------------------------------------------------------


class TestDistributionMetrics:
    def test_hybrid_distribution(self) -> None:
        a = PersonaSurvivalAnalysis()
        a.observe_generation(
            0,
            [
                _comp("newton"),
                _comp("feynman"),
                _comp("newton", "feynman"),
                _comp("kant", "newton", "feynman"),
            ],
        )
        dist = a.hybrid_distribution()
        # ユニーク signature: newton, feynman, feynman|newton, feynman|kant|newton
        assert dist == {1: 2, 2: 1, 3: 1}

    def test_persona_appearance_count(self) -> None:
        a = PersonaSurvivalAnalysis()
        a.observe_generation(
            0,
            [
                _comp("newton"),
                _comp("newton"),
                _comp("newton", "feynman"),
            ],
        )
        # newton signature 2 回 → "newton" +2, hybrid signature 1 回 → "newton" +1, "feynman" +1
        # newton 合計 3, feynman 合計 1
        counts = a.persona_appearance_count()
        assert counts == {"newton": 3, "feynman": 1}

    def test_hybrid_ratio_empty(self) -> None:
        a = PersonaSurvivalAnalysis()
        assert a.hybrid_ratio() == 0.0

    def test_hybrid_ratio_mixed(self) -> None:
        a = PersonaSurvivalAnalysis()
        a.observe_generation(
            0,
            [
                _comp("newton"),
                _comp("feynman"),
                _comp("newton", "feynman"),
                _comp("kant", "feynman"),
            ],
        )
        # 4 ユニーク signature: 2 hybrid / 2 single → 0.5
        assert a.hybrid_ratio() == pytest.approx(0.5)

    def test_survival_by_size(self) -> None:
        a = PersonaSurvivalAnalysis()
        # single persona 1 個を 3 世代維持, hybrid 1 個を 2 世代維持
        for gen in range(3):
            a.observe_generation(gen, [_comp("newton")])
        for gen in range(2):
            a.observe_generation(gen + 10, [_comp("kant", "feynman")])
        by_size = a.survival_by_size()
        assert by_size[1] == pytest.approx(3.0)
        assert by_size[2] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# 5. serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_keys(self) -> None:
        a = PersonaSurvivalAnalysis()
        a.observe_generation(
            0, [_comp("newton"), _comp("newton", "feynman")], scores=[0.5, 0.8]
        )
        d = a.to_dict()
        assert "tracker" in d
        assert "hybrid_distribution" in d
        assert "persona_appearance_count" in d
        assert "hybrid_ratio" in d
        assert "survival_by_size" in d
        assert d["hybrid_distribution"] == {1: 1, 2: 1}
