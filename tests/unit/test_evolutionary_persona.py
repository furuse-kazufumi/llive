# SPDX-License-Identifier: Apache-2.0
"""Historical Persona Ontology + PersonaCompositionMutation (v0.E CE-19/21) tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    PERSONA_ONTOLOGY,
    RESEARCH_METHODOLOGY_PERSONA_IDS,
    Persona,
    PersonaComposition,
    PersonaCompositionMutation,
    THOUGHT_FACTORS,
    get_persona,
    list_persona_ids,
    persona_dissimilarity,
    random_persona_composition,
)
from llive.perf.evolutionary.thought_factor_per_layer import (
    NUM_THOUGHT_FACTORS,
    ThoughtFactorPerLayerChromosome,
)


# ---------------------------------------------------------------------------
# 1. Persona / ontology
# ---------------------------------------------------------------------------


def test_ontology_has_historical_and_research_personas() -> None:
    # 歴史人物 10 名 + 研究方法論ペルソナ 4 名 (2026-05-23 追加) = 14
    assert len(PERSONA_ONTOLOGY) == 14
    assert len(RESEARCH_METHODOLOGY_PERSONA_IDS) == 4
    for pid in RESEARCH_METHODOLOGY_PERSONA_IDS:
        assert pid in PERSONA_ONTOLOGY


def test_research_methodology_personas_well_formed() -> None:
    """furuse + 予測符号化評議会 (friston/millidge/isomura) の整合性."""
    for pid in RESEARCH_METHODOLOGY_PERSONA_IDS:
        p = get_persona(pid)
        assert len(p.factor_affinity) == len(THOUGHT_FACTORS)
        assert p.thought_patterns  # 非空
        assert p.fields  # 非空

    # furuse 調査者: 来歴 (provenance) が最大級, 自己拡張は低い (規律的)
    furuse = get_persona("furuse-kazufumi")
    fa = dict(zip(THOUGHT_FACTORS, furuse.factor_affinity, strict=True))
    assert fa["factor_provenance"] >= 0.9
    assert fa["factor_self_extend"] <= 0.4

    # Friston: 自己拡張/構造化が高い (統一), 来歴は低い
    friston = get_persona("friston")
    ffa = dict(zip(THOUGHT_FACTORS, friston.factor_affinity, strict=True))
    assert ffa["factor_self_extend"] >= 0.9
    assert ffa["factor_provenance"] <= 0.5

    # Millidge: 不確実性 (honest disclosure 番人) が最大級
    millidge = get_persona("millidge")
    mfa = dict(zip(THOUGHT_FACTORS, millidge.factor_affinity, strict=True))
    assert mfa["factor_uncertainty"] >= 0.9


def test_research_personas_convert_to_genome() -> None:
    """ペルソナ親和度 → ThoughtFactorPerLayerChromosome へゲノム化できる (founder 種)."""
    for pid in RESEARCH_METHODOLOGY_PERSONA_IDS:
        p = get_persona(pid)
        chrom = ThoughtFactorPerLayerChromosome.from_persona_affinity(
            p.factor_affinity, broadcast_strategy="uniform"
        )
        arr = chrom.as_array()
        assert arr.shape[0] == NUM_THOUGHT_FACTORS
        # uniform broadcast なので各層が persona affinity と一致
        for li in range(arr.shape[1]):
            np.testing.assert_allclose(arr[:, li], p.factor_affinity)


def test_research_persona_composition_and_mutation() -> None:
    """research ペルソナで composition を作り mutation が壊れないこと (世代交代に乗る)."""
    rng = np.random.default_rng(0)
    comp = PersonaComposition(
        persona_ids=("friston", "millidge", "isomura-takuya"),
        weights=(1.0, 1.0, 1.0),
        import_policy="moderator",
    ).normalize_weights()
    affinity = comp.effective_factor_affinity()
    assert affinity.shape == (len(THOUGHT_FACTORS),)
    mut = PersonaCompositionMutation()
    child = mut(comp, rng)
    assert 1 <= len(child.persona_ids) <= 5
    for pid in child.persona_ids:
        assert pid in PERSONA_ONTOLOGY


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
