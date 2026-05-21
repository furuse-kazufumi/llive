# SPDX-License-Identifier: Apache-2.0
"""Historical Persona Ontology + PersonaCompositionMutation (v0.E CE-19/21) tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    PERSONA_ONTOLOGY,
    Persona,
    PersonaComposition,
    PersonaCompositionMutation,
    THOUGHT_FACTORS,
    get_persona,
    list_persona_ids,
    persona_dissimilarity,
    random_persona_composition,
)


# ---------------------------------------------------------------------------
# 1. Persona / ontology
# ---------------------------------------------------------------------------


def test_ontology_has_10_personas() -> None:
    assert len(PERSONA_ONTOLOGY) == 10


def test_thought_factors_length_10() -> None:
    assert len(THOUGHT_FACTORS) == 10


def test_persona_oka_kiyoshi_exists() -> None:
    p = get_persona("oka-kiyoshi")
    assert p.name == "岡潔"
    assert "情緒" in p.thought_patterns
    assert len(p.factor_affinity) == 10


def test_get_persona_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_persona("non-existent")


def test_persona_factor_affinity_in_unit_range() -> None:
    for p in PERSONA_ONTOLOGY.values():
        for v in p.factor_affinity:
            assert 0.0 <= v <= 1.0


def test_persona_to_dict_roundtrip() -> None:
    p = get_persona("grothendieck")
    d = p.to_dict()
    p2 = Persona.from_dict(d)
    assert p2 == p


def test_persona_rejects_wrong_affinity_length() -> None:
    with pytest.raises(ValueError, match="factor_affinity"):
        Persona(
            persona_id="test",
            name="Test",
            era="Test",
            fields=(),
            thought_patterns=(),
            factor_affinity=(0.5, 0.5, 0.5),  # too short
        )


def test_persona_rejects_out_of_range_affinity() -> None:
    with pytest.raises(ValueError, match="factor_affinity values"):
        Persona(
            persona_id="test",
            name="Test",
            era="Test",
            fields=(),
            thought_patterns=(),
            factor_affinity=(1.5,) + (0.5,) * 9,
        )


def test_list_persona_ids_sorted() -> None:
    ids = list_persona_ids()
    assert list(ids) == sorted(ids)


# ---------------------------------------------------------------------------
# 2. PersonaComposition
# ---------------------------------------------------------------------------


def test_composition_basic() -> None:
    c = PersonaComposition(
        persona_ids=("oka-kiyoshi", "feynman"),
        weights=(0.5, 0.5),
    )
    assert c.import_policy == "mix"
    assert sum(c.weights) == pytest.approx(1.0)


def test_composition_rejects_empty() -> None:
    with pytest.raises(ValueError, match="persona_ids"):
        PersonaComposition(persona_ids=(), weights=())


def test_composition_rejects_duplicate() -> None:
    with pytest.raises(ValueError, match="unique"):
        PersonaComposition(
            persona_ids=("oka-kiyoshi", "oka-kiyoshi"),
            weights=(0.5, 0.5),
        )


def test_composition_rejects_unknown_persona() -> None:
    with pytest.raises(ValueError, match="unknown persona_id"):
        PersonaComposition(
            persona_ids=("bogus-id",),
            weights=(1.0,),
        )


def test_composition_normalize_weights() -> None:
    c = PersonaComposition(
        persona_ids=("oka-kiyoshi", "feynman"),
        weights=(2.0, 3.0),
    ).normalize_weights()
    assert sum(c.weights) == pytest.approx(1.0)
    assert c.weights[0] == pytest.approx(0.4)


def test_composition_effective_affinity_mix() -> None:
    c = PersonaComposition(
        persona_ids=("oka-kiyoshi", "feynman"),
        weights=(1.0, 1.0),
    ).normalize_weights()
    aff = c.effective_factor_affinity()
    oka = np.asarray(get_persona("oka-kiyoshi").factor_affinity)
    fey = np.asarray(get_persona("feynman").factor_affinity)
    expected = 0.5 * oka + 0.5 * fey
    assert np.allclose(aff, expected)


def test_composition_exclusive_uses_first_only() -> None:
    c = PersonaComposition(
        persona_ids=("oka-kiyoshi", "feynman"),
        weights=(0.5, 0.5),
        import_policy="exclusive",
    )
    aff = c.effective_factor_affinity()
    oka = np.asarray(get_persona("oka-kiyoshi").factor_affinity)
    assert np.allclose(aff, oka)


def test_composition_moderator_doubles_first_weight() -> None:
    c = PersonaComposition(
        persona_ids=("oka-kiyoshi", "feynman"),
        weights=(0.5, 0.5),
        import_policy="moderator",
    )
    aff = c.effective_factor_affinity()
    oka = np.asarray(get_persona("oka-kiyoshi").factor_affinity)
    fey = np.asarray(get_persona("feynman").factor_affinity)
    expected = (1.0 / 1.5) * oka + (0.5 / 1.5) * fey
    assert np.allclose(aff, expected, atol=1e-6)


def test_composition_to_dict_roundtrip() -> None:
    c = PersonaComposition(
        persona_ids=("kant", "socrates"),
        weights=(0.6, 0.4),
        import_policy="moderator",
    )
    d = c.to_dict()
    c2 = PersonaComposition.from_dict(d)
    assert c2 == c


# ---------------------------------------------------------------------------
# 3. random_persona_composition
# ---------------------------------------------------------------------------


def test_random_composition_with_numpy_rng() -> None:
    rng = np.random.default_rng(0)
    c = random_persona_composition(rng, n=3)
    assert len(c.persona_ids) == 3
    assert sum(c.weights) == pytest.approx(1.0)


def test_random_composition_with_stdlib_rng() -> None:
    import random as stdrandom
    rng = stdrandom.Random(0)
    c = random_persona_composition(rng, n=4)
    assert len(c.persona_ids) == 4
    assert sum(c.weights) == pytest.approx(1.0)


def test_random_composition_rejects_too_many() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="ontology size"):
        random_persona_composition(rng, n=100)


# ---------------------------------------------------------------------------
# 4. PersonaCompositionMutation
# ---------------------------------------------------------------------------


def test_mutation_returns_valid_composition() -> None:
    c = PersonaComposition(
        persona_ids=("oka-kiyoshi", "feynman"),
        weights=(0.5, 0.5),
    )
    mut = PersonaCompositionMutation()
    rng = np.random.default_rng(0)
    for _ in range(10):
        c = mut(c, rng)
        assert sum(c.weights) == pytest.approx(1.0, abs=1e-6)
        assert len(set(c.persona_ids)) == len(c.persona_ids)
        for pid in c.persona_ids:
            assert pid in PERSONA_ONTOLOGY


def test_mutation_respects_min_max() -> None:
    c = PersonaComposition(
        persona_ids=("oka-kiyoshi",),
        weights=(1.0,),
    )
    mut = PersonaCompositionMutation(
        p_swap=0.0, p_add_remove=1.0, p_weight_perturb=0.0,
        min_personas=1, max_personas=2,
    )
    rng = np.random.default_rng(0)
    for _ in range(20):
        c = mut(c, rng)
        assert 1 <= len(c.persona_ids) <= 2


def test_mutation_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="probabilities"):
        PersonaCompositionMutation(p_swap=1.5)
    with pytest.raises(ValueError, match="min_personas"):
        PersonaCompositionMutation(min_personas=0)
    with pytest.raises(ValueError, match="weight_sigma"):
        PersonaCompositionMutation(weight_sigma=0.0)


# ---------------------------------------------------------------------------
# 5. persona_dissimilarity
# ---------------------------------------------------------------------------


def test_dissimilarity_identical_zero() -> None:
    c = PersonaComposition(
        persona_ids=("oka-kiyoshi", "feynman"),
        weights=(0.5, 0.5),
    )
    assert persona_dissimilarity(c, c) == pytest.approx(0.0, abs=1e-6)


def test_dissimilarity_completely_different_high() -> None:
    a = PersonaComposition(
        persona_ids=("oka-kiyoshi",),
        weights=(1.0,),
    )
    b = PersonaComposition(
        persona_ids=("sun-tzu",),
        weights=(1.0,),
    )
    d = persona_dissimilarity(a, b)
    # Jaccard = 0, L2 diff is non-negligible. 期待 > 0.5
    assert d > 0.5
    assert d <= 1.0


def test_dissimilarity_partial_overlap() -> None:
    a = PersonaComposition(
        persona_ids=("oka-kiyoshi", "feynman"),
        weights=(0.5, 0.5),
    )
    b = PersonaComposition(
        persona_ids=("feynman", "newton"),
        weights=(0.5, 0.5),
    )
    d = persona_dissimilarity(a, b)
    assert 0.0 < d < 1.0
