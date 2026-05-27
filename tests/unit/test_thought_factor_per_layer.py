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
