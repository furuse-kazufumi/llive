# SPDX-License-Identifier: Apache-2.0
"""Tests for thought_factor_per_layer (2026-05-23 着地).

10 思考因子 × メモリ層の 2D matrix genome を覆う基本性質テスト群.
"""
from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary.persona import PERSONA_ONTOLOGY, THOUGHT_FACTORS
from llive.perf.evolutionary.thought_factor_per_layer import (
    DEFAULT_MEMORY_LAYER_NAMES,
    NUM_MEMORY_LAYERS,
    NUM_THOUGHT_FACTORS,
    ThoughtFactorPerLayerChromosome,
    argmax_persona_index,
    crossover_per_factor,
    crossover_per_layer,
    mutate_persona_index,
    random_persona_index,
)


def test_constants_consistent_with_persona_module() -> None:
    assert NUM_THOUGHT_FACTORS == 10
    assert NUM_THOUGHT_FACTORS == len(THOUGHT_FACTORS)
    assert NUM_MEMORY_LAYERS == 4
    assert len(DEFAULT_MEMORY_LAYER_NAMES) == NUM_MEMORY_LAYERS


def test_default_is_uniform_neutral() -> None:
    c = ThoughtFactorPerLayerChromosome.default()
    arr = c.as_array()
    assert arr.shape == (NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS)
    assert np.all(arr == 0.5)
    assert c.layer_names == DEFAULT_MEMORY_LAYER_NAMES


def test_random_seed_reproducibility() -> None:
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    c1 = ThoughtFactorPerLayerChromosome.random(rng1)
    c2 = ThoughtFactorPerLayerChromosome.random(rng2)
    assert np.allclose(c1.as_array(), c2.as_array())


def test_random_values_in_unit_range() -> None:
    rng = np.random.default_rng(0)
    c = ThoughtFactorPerLayerChromosome.random(rng)
    arr = c.as_array()
    assert (arr >= 0.0).all()
    assert (arr <= 1.0).all()


def test_from_array_clips_out_of_range() -> None:
    bad = np.full((NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS), 1.7)
    bad[0, 0] = -0.5
    c = ThoughtFactorPerLayerChromosome.from_array(bad)
    arr = c.as_array()
    assert arr[0, 0] == 0.0
    assert (arr[1:, :] == 1.0).all()


def test_from_array_rejects_wrong_shape() -> None:
    bad = np.zeros((5, 4))  # wrong factor count
    with pytest.raises(ValueError):
        ThoughtFactorPerLayerChromosome.from_array(bad)


def test_validation_rejects_out_of_range_in_constructor() -> None:
    bad_rows = tuple(
        tuple(1.5 for _ in range(NUM_MEMORY_LAYERS))
        for _ in range(NUM_THOUGHT_FACTORS)
    )
    with pytest.raises(ValueError):
        ThoughtFactorPerLayerChromosome(factor_weights=bad_rows)


def test_validation_rejects_wrong_row_count() -> None:
    bad = tuple(
        tuple(0.5 for _ in range(NUM_MEMORY_LAYERS)) for _ in range(5)
    )
    with pytest.raises(ValueError):
        ThoughtFactorPerLayerChromosome(factor_weights=bad)


def test_validation_rejects_empty_layer_names() -> None:
    bad = tuple(tuple() for _ in range(NUM_THOUGHT_FACTORS))
    with pytest.raises(ValueError):
        ThoughtFactorPerLayerChromosome(
            factor_weights=bad,
            layer_names=(),
        )


def test_get_factor_layer_returns_correct_value() -> None:
    arr = np.linspace(0.0, 1.0, NUM_THOUGHT_FACTORS * NUM_MEMORY_LAYERS).reshape(
        NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS
    )
    c = ThoughtFactorPerLayerChromosome.from_array(arr)
    assert (
        abs(
            c.get_factor_layer(THOUGHT_FACTORS[3], DEFAULT_MEMORY_LAYER_NAMES[2])
            - arr[3, 2]
        )
        < 1e-9
    )


def test_get_factor_layer_unknown_keys_raise_keyerror() -> None:
    c = ThoughtFactorPerLayerChromosome.default()
    with pytest.raises(KeyError):
        c.get_factor_layer("unknown_factor", DEFAULT_MEMORY_LAYER_NAMES[0])
    with pytest.raises(KeyError):
        c.get_factor_layer(THOUGHT_FACTORS[0], "unknown_layer")


def test_factor_profile_and_layer_profile() -> None:
    arr = np.array(
        [
            [0.1, 0.2, 0.3, 0.4],
            [0.5, 0.6, 0.7, 0.8],
        ]
        + [[0.0] * 4 for _ in range(NUM_THOUGHT_FACTORS - 2)]
    )
    c = ThoughtFactorPerLayerChromosome.from_array(arr)
    assert c.factor_profile(THOUGHT_FACTORS[0]) == (0.1, 0.2, 0.3, 0.4)
    assert c.factor_profile(THOUGHT_FACTORS[1]) == (0.5, 0.6, 0.7, 0.8)
    layer0 = c.layer_profile(DEFAULT_MEMORY_LAYER_NAMES[0])
    assert layer0[0] == 0.1
    assert layer0[1] == 0.5


def test_serialization_roundtrip() -> None:
    rng = np.random.default_rng(7)
    c = ThoughtFactorPerLayerChromosome.random(rng)
    restored = ThoughtFactorPerLayerChromosome.from_dict(c.to_dict())
    assert np.allclose(c.as_array(), restored.as_array())
    assert c.layer_names == restored.layer_names


def test_to_dict_includes_factor_names() -> None:
    c = ThoughtFactorPerLayerChromosome.default()
    d = c.to_dict()
    assert d["factor_names"] == list(THOUGHT_FACTORS)
    assert d["layer_names"] == list(DEFAULT_MEMORY_LAYER_NAMES)


def test_sample_neighborhood_stays_in_bounds() -> None:
    c = ThoughtFactorPerLayerChromosome.default()
    rng = np.random.default_rng(0)
    for _ in range(100):
        c = c.sample_neighborhood(rng, step_size=0.5)
        arr = c.as_array()
        assert (arr >= 0.0).all()
        assert (arr <= 1.0).all()


def test_kolmogorov_proxy_deterministic_and_positive() -> None:
    c = ThoughtFactorPerLayerChromosome.default()
    k1 = c.kolmogorov_proxy()
    k2 = c.kolmogorov_proxy()
    assert k1 == k2
    assert k1 > 0


def test_from_persona_affinity_uniform_broadcast() -> None:
    affinity = tuple([0.7] * NUM_THOUGHT_FACTORS)
    c = ThoughtFactorPerLayerChromosome.from_persona_affinity(affinity)
    arr = c.as_array()
    assert np.allclose(arr, 0.7)


def test_from_persona_affinity_working_heavy() -> None:
    affinity = tuple(float(i) / 10 for i in range(NUM_THOUGHT_FACTORS))
    c = ThoughtFactorPerLayerChromosome.from_persona_affinity(
        affinity, broadcast_strategy="working_heavy"
    )
    arr = c.as_array()
    assert np.allclose(arr[:, 0], affinity)
    assert np.allclose(arr[:, 1:], 0.5)


def test_from_persona_affinity_episodic_heavy() -> None:
    affinity = tuple(float(i) / 10 for i in range(NUM_THOUGHT_FACTORS))
    c = ThoughtFactorPerLayerChromosome.from_persona_affinity(
        affinity, broadcast_strategy="episodic_heavy"
    )
    arr = c.as_array()
    assert np.allclose(arr[:, -1], affinity)
    assert np.allclose(arr[:, :-1], 0.5)


def test_from_persona_affinity_unknown_strategy() -> None:
    affinity = tuple([0.5] * NUM_THOUGHT_FACTORS)
    with pytest.raises(ValueError):
        ThoughtFactorPerLayerChromosome.from_persona_affinity(
            affinity, broadcast_strategy="unknown_strategy"
        )


def test_crossover_per_factor_each_row_comes_from_one_parent() -> None:
    a = ThoughtFactorPerLayerChromosome.from_array(
        np.zeros((NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS))
    )
    b = ThoughtFactorPerLayerChromosome.from_array(
        np.ones((NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS))
    )
    rng = np.random.default_rng(0)
    child = crossover_per_factor(a, b, rng)
    child_arr = child.as_array()
    for row in child_arr:
        assert np.all(row == 0.0) or np.all(row == 1.0)


def test_crossover_per_layer_each_column_comes_from_one_parent() -> None:
    a = ThoughtFactorPerLayerChromosome.from_array(
        np.zeros((NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS))
    )
    b = ThoughtFactorPerLayerChromosome.from_array(
        np.ones((NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS))
    )
    rng = np.random.default_rng(0)
    child = crossover_per_layer(a, b, rng)
    child_arr = child.as_array()
    for col_idx in range(child_arr.shape[1]):
        col = child_arr[:, col_idx]
        assert np.all(col == 0.0) or np.all(col == 1.0)


def test_crossover_rejects_layer_name_mismatch() -> None:
    a = ThoughtFactorPerLayerChromosome.default()
    b = ThoughtFactorPerLayerChromosome.default(
        layer_names=("a", "b", "c", "d")
    )
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError):
        crossover_per_factor(a, b, rng)
    with pytest.raises(ValueError):
        crossover_per_layer(a, b, rng)


def test_frozen_hashable() -> None:
    c1 = ThoughtFactorPerLayerChromosome.default()
    c2 = ThoughtFactorPerLayerChromosome.default()
    assert hash(c1) == hash(c2)
    s = {c1, c2}
    assert len(s) == 1


def test_custom_layer_names() -> None:
    custom = ("L1", "L2", "L3")
    c = ThoughtFactorPerLayerChromosome.default(layer_names=custom)
    arr = c.as_array()
    assert arr.shape == (NUM_THOUGHT_FACTORS, 3)
    assert c.layer_names == custom


# ===========================================================================
# persona_index — additive (default off) 採用テスト (2026-05-28)
# ===========================================================================


def test_persona_index_default_is_none_and_preserves_current_behavior() -> None:
    """default は persona_index=None で, 連続 weights 系は現行挙動を完全維持."""
    c = ThoughtFactorPerLayerChromosome.default()
    assert c.persona_index is None
    # decode は None を返す (現行を変えない signal)
    assert c.persona_indexed_affinity() is None
    # to_dict に persona_index キーは出ない (legacy 形と同じ)
    assert "persona_index" not in c.to_dict()
    # 連続 flat ベクトルは 40-dim のまま (no fourth dim 不変条件)
    assert c.as_flat().size == NUM_THOUGHT_FACTORS * NUM_MEMORY_LAYERS


def test_persona_index_does_not_change_flat_vector() -> None:
    """persona_index を付けても as_array / as_flat は一切変わらない (離散メタデータ)."""
    rng = np.random.default_rng(0)
    base = ThoughtFactorPerLayerChromosome.random(rng)
    pi = random_persona_index(np.random.default_rng(1))
    withpi = base.with_persona_index(pi)
    assert np.allclose(base.as_array(), withpi.as_array())
    assert base.as_flat().size == withpi.as_flat().size == 40
    assert withpi.persona_index == pi


def test_persona_index_decode_matches_small_poc_mapping() -> None:
    """decode: affinity[f] = PERSONA_ONTOLOGY[ids[idx[f]]].factor_affinity[f]
    (小 PoC decode_indexed と同一写像)。argmax index は per-factor 最大 envelope。"""
    ids = sorted(PERSONA_ONTOLOGY.keys())
    A = np.array(
        [list(PERSONA_ONTOLOGY[p].factor_affinity) for p in ids], dtype=float
    )
    pi = argmax_persona_index()  # 各因子で affinity 最大のペルソナ
    c = ThoughtFactorPerLayerChromosome.default().with_persona_index(pi)
    pheno = np.array(c.persona_indexed_affinity())
    np.testing.assert_allclose(pheno, A.max(axis=0))
    # 明示的に写像式と一致することも確認
    expected = [A[pi[f], f] for f in range(NUM_THOUGHT_FACTORS)]
    np.testing.assert_allclose(pheno, expected)


def test_persona_index_round_trip_via_dict() -> None:
    rng = np.random.default_rng(3)
    pi = random_persona_index(rng)
    c = ThoughtFactorPerLayerChromosome.random(rng).with_persona_index(pi)
    d = c.to_dict()
    assert d["persona_index"] == list(pi)
    restored = ThoughtFactorPerLayerChromosome.from_dict(d)
    assert restored.persona_index == c.persona_index
    assert isinstance(restored.persona_index, tuple)
    assert np.allclose(restored.as_array(), c.as_array())


def test_persona_index_from_legacy_dict_without_key_is_none() -> None:
    """旧 snapshot (persona_index キー無し) → None (後方互換)."""
    c = ThoughtFactorPerLayerChromosome.default()
    legacy = {
        "factor_weights": c.to_dict()["factor_weights"],
        "layer_names": c.to_dict()["layer_names"],
    }
    assert "persona_index" not in legacy
    restored = ThoughtFactorPerLayerChromosome.from_dict(legacy)
    assert restored.persona_index is None


def test_persona_index_coerces_list_and_ndarray_to_tuple_of_int() -> None:
    fw = ThoughtFactorPerLayerChromosome.default().factor_weights
    c_list = ThoughtFactorPerLayerChromosome(
        factor_weights=fw, persona_index=[0, 1, 2, 3, 0, 1, 2, 3, 0, 1]
    )
    assert c_list.persona_index == (0, 1, 2, 3, 0, 1, 2, 3, 0, 1)
    assert all(isinstance(v, int) for v in c_list.persona_index)
    # ndarray int 入力も tuple-of-int に正規化され hashable
    c_arr = ThoughtFactorPerLayerChromosome(
        factor_weights=fw, persona_index=np.arange(NUM_THOUGHT_FACTORS)
    )
    assert c_arr.persona_index == tuple(range(NUM_THOUGHT_FACTORS))
    assert hash(c_arr) is not None


def test_persona_index_validation_rejects_wrong_len() -> None:
    fw = ThoughtFactorPerLayerChromosome.default().factor_weights
    with pytest.raises(ValueError):
        ThoughtFactorPerLayerChromosome(factor_weights=fw, persona_index=(0, 1, 2))


def test_persona_index_validation_rejects_out_of_range() -> None:
    fw = ThoughtFactorPerLayerChromosome.default().factor_weights
    n = len(PERSONA_ONTOLOGY)
    with pytest.raises(ValueError):
        ThoughtFactorPerLayerChromosome(
            factor_weights=fw, persona_index=(n,) * NUM_THOUGHT_FACTORS
        )
    with pytest.raises(ValueError):
        ThoughtFactorPerLayerChromosome(
            factor_weights=fw, persona_index=(-1,) * NUM_THOUGHT_FACTORS
        )


def test_persona_index_validation_rejects_bool() -> None:
    """bool は int サブクラスだが persona index として拒否 (fail-closed)."""
    fw = ThoughtFactorPerLayerChromosome.default().factor_weights
    with pytest.raises(ValueError):
        ThoughtFactorPerLayerChromosome(
            factor_weights=fw, persona_index=(True,) * NUM_THOUGHT_FACTORS
        )


def test_mutate_persona_index_changes_at_most_one_factor() -> None:
    rng = np.random.default_rng(0)
    pi = random_persona_index(rng)
    mutated = mutate_persona_index(pi, rng)
    diffs = sum(1 for a, b in zip(pi, mutated) if a != b)
    assert diffs <= 1
    assert len(mutated) == NUM_THOUGHT_FACTORS
    for v in mutated:
        assert 0 <= v < len(PERSONA_ONTOLOGY)


def test_sample_neighborhood_none_individual_stays_none() -> None:
    """persona_index None の個体は mutation で None のまま (現行挙動不変)."""
    c = ThoughtFactorPerLayerChromosome.default()
    rng = np.random.default_rng(0)
    for _ in range(20):
        c = c.sample_neighborhood(rng, step_size=0.2)
        assert c.persona_index is None


def test_sample_neighborhood_set_individual_keeps_and_mutates_persona_index() -> None:
    """persona_index 設定済の個体は mutation 後も persona_index を保持し進化する."""
    rng = np.random.default_rng(0)
    pi = random_persona_index(rng)
    c = ThoughtFactorPerLayerChromosome.default().with_persona_index(pi)
    child = c.sample_neighborhood(rng, step_size=0.1)
    assert child.persona_index is not None
    assert len(child.persona_index) == NUM_THOUGHT_FACTORS
    # 連続層は摂動される (step_size>0 なので weights は変わりうる) が,
    # persona_index は維持され, 高々 1 因子だけ変わる。
    diffs = sum(1 for a, b in zip(pi, child.persona_index) if a != b)
    assert diffs <= 1


def test_crossover_per_factor_both_none_is_noop_for_persona_index() -> None:
    """両親 None → persona_index は None のまま (additive 不変条件)."""
    a = ThoughtFactorPerLayerChromosome.from_array(np.zeros((10, 4)))
    b = ThoughtFactorPerLayerChromosome.from_array(np.ones((10, 4)))
    rng = np.random.default_rng(0)
    child = crossover_per_factor(a, b, rng)
    assert child.persona_index is None
    child2 = crossover_per_layer(a, b, rng)
    assert child2.persona_index is None


def test_crossover_per_factor_both_set_inherits_per_factor() -> None:
    """両親設定 → 子 persona_index は各因子で親 A/B いずれかの値."""
    rng = np.random.default_rng(0)
    pi_a = (0,) * NUM_THOUGHT_FACTORS
    pi_b = (1,) * NUM_THOUGHT_FACTORS
    a = ThoughtFactorPerLayerChromosome.default().with_persona_index(pi_a)
    b = ThoughtFactorPerLayerChromosome.default().with_persona_index(pi_b)
    seen_a = seen_b = False
    for _ in range(50):
        child = crossover_per_factor(a, b, rng)
        assert child.persona_index is not None
        for v in child.persona_index:
            assert v in (0, 1)
            if v == 0:
                seen_a = True
            if v == 1:
                seen_b = True
    assert seen_a and seen_b  # 両親由来の因子が混ざる


def test_crossover_one_parent_set_inherits_that_parent() -> None:
    """片親のみ設定 → 設定側を継承 (None からは合成しない)."""
    rng = np.random.default_rng(0)
    pi = (2,) * NUM_THOUGHT_FACTORS
    a = ThoughtFactorPerLayerChromosome.default().with_persona_index(pi)
    b = ThoughtFactorPerLayerChromosome.default()  # None
    child_ab = crossover_per_factor(a, b, rng)
    child_ba = crossover_per_factor(b, a, rng)
    assert child_ab.persona_index == pi
    assert child_ba.persona_index == pi


def test_with_persona_index_preserves_weights_and_layers() -> None:
    rng = np.random.default_rng(5)
    c = ThoughtFactorPerLayerChromosome.random(rng)
    pi = random_persona_index(rng)
    withpi = c.with_persona_index(pi)
    assert np.allclose(withpi.as_array(), c.as_array())
    assert withpi.layer_names == c.layer_names
    # None に戻すこともできる
    back = withpi.with_persona_index(None)
    assert back.persona_index is None
