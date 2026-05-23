# SPDX-License-Identifier: Apache-2.0
"""CMA-ES adapter skeleton — 28 件 pytest.

[[project_ai_algorithms_taxonomy]] 優先度 #1 / [[project_llive_thought_factor_per_layer]]
(40-dim genome) の mutation operator 互換性確認.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from llive.perf.evolutionary.cma_es import CMAESAdapter, CMAESState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _quadratic_fitness(x: np.ndarray, offset: float = 0.0) -> float:
    """Sphere function (convex): f(x) = Σ (x_i - offset)^2."""
    return float(np.sum((x - offset) ** 2))


# ---------------------------------------------------------------------------
# Construction & validation
# ---------------------------------------------------------------------------


def test_construct_default_40dim() -> None:
    """40-dim genome (Genome3D.c_factors = 10 × 4) で default 構築."""
    es = CMAESAdapter(dim=40)
    assert es.dim == 40
    assert es.sigma == pytest.approx(0.3)
    assert es.population_size >= 2
    # Hansen default λ = 4 + floor(3 ln 40) ≈ 4 + 11 = 15
    assert es.population_size == 4 + int(math.floor(3 * math.log(40)))
    assert es.mu == es.population_size // 2
    assert es.generation == 0
    assert es.mean.shape == (40,)
    assert es.C.shape == (40, 40)


def test_construct_dim_5() -> None:
    es = CMAESAdapter(dim=5, sigma0=0.5)
    assert es.dim == 5
    assert es.mean.shape == (5,)
    assert es.C.shape == (5, 5)


def test_construct_dim_100() -> None:
    es = CMAESAdapter(dim=100, sigma0=1.0)
    assert es.dim == 100
    assert es.population_size >= 4 + int(math.floor(3 * math.log(100)))


def test_construct_invalid_dim() -> None:
    with pytest.raises(ValueError):
        CMAESAdapter(dim=0)


def test_construct_invalid_sigma() -> None:
    with pytest.raises(ValueError):
        CMAESAdapter(dim=5, sigma0=-0.1)


def test_construct_invalid_population_size() -> None:
    with pytest.raises(ValueError):
        CMAESAdapter(dim=5, population_size=1)


def test_construct_mean0_shape_mismatch() -> None:
    with pytest.raises(ValueError):
        CMAESAdapter(dim=5, mean0=np.zeros(4))


def test_construct_with_custom_mean() -> None:
    m0 = np.array([1.0, 2.0, 3.0])
    es = CMAESAdapter(dim=3, mean0=m0)
    np.testing.assert_allclose(es.mean, m0)


# ---------------------------------------------------------------------------
# ask() shape & determinism
# ---------------------------------------------------------------------------


def test_ask_shape_default() -> None:
    es = CMAESAdapter(dim=40, sigma0=0.3)
    cands = es.ask()
    assert cands.shape == (es.population_size, 40)


def test_ask_shape_custom_lambda() -> None:
    es = CMAESAdapter(dim=10, population_size=20)
    cands = es.ask()
    assert cands.shape == (20, 10)


def test_ask_deterministic_with_seed() -> None:
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    es1 = CMAESAdapter(dim=5, rng=rng1)
    es2 = CMAESAdapter(dim=5, rng=rng2)
    np.testing.assert_allclose(es1.ask(), es2.ask())


def test_ask_different_seeds_differ() -> None:
    es1 = CMAESAdapter(dim=5, rng=np.random.default_rng(1))
    es2 = CMAESAdapter(dim=5, rng=np.random.default_rng(2))
    assert not np.allclose(es1.ask(), es2.ask())


def test_ask_sigma_zero_collapses_to_mean() -> None:
    es = CMAESAdapter(dim=5, sigma0=0.0)
    cands = es.ask()
    # All rows should equal the mean
    for row in cands:
        np.testing.assert_allclose(row, es.mean)


def test_ask_bounds_clipping() -> None:
    es = CMAESAdapter(dim=5, sigma0=10.0, bounds=(-1.0, 1.0))
    cands = es.ask()
    assert cands.min() >= -1.0
    assert cands.max() <= 1.0


# ---------------------------------------------------------------------------
# tell() — mean update & validation
# ---------------------------------------------------------------------------


def test_tell_updates_mean() -> None:
    es = CMAESAdapter(dim=3, sigma0=0.5, rng=np.random.default_rng(0))
    cands = es.ask()
    fits = np.array([_quadratic_fitness(x) for x in cands])
    old_mean = es.mean.copy()
    es.tell(cands, fits)
    assert es.generation == 1
    # mean should have moved (extremely unlikely to be identical)
    assert not np.allclose(es.mean, old_mean)


def test_tell_shape_mismatch_candidates() -> None:
    es = CMAESAdapter(dim=3, sigma0=0.5)
    with pytest.raises(ValueError):
        es.tell(np.zeros((es.population_size, 4)), np.zeros(es.population_size))


def test_tell_shape_mismatch_fitnesses() -> None:
    es = CMAESAdapter(dim=3, sigma0=0.5)
    cands = es.ask()
    with pytest.raises(ValueError):
        es.tell(cands, np.zeros(es.population_size + 1))


def test_tell_maximize_mode() -> None:
    """minimize=False で「高いほど良い」になることを確認."""
    es = CMAESAdapter(dim=3, sigma0=0.5, rng=np.random.default_rng(0))
    cands = es.ask()
    # Higher = better. Best is the row with highest fitness.
    fits = np.linspace(0.0, 1.0, num=es.population_size)
    es.tell(cands, fits, minimize=False)
    # No exception, generation advances.
    assert es.generation == 1


# ---------------------------------------------------------------------------
# Convergence (convex quadratic)
# ---------------------------------------------------------------------------


def test_convergence_sphere_5dim() -> None:
    """Sphere 5-dim で 50 generation. 初期 fitness の 1/10 以下に下がること."""
    es = CMAESAdapter(
        dim=5,
        sigma0=0.5,
        mean0=np.full(5, 2.0),
        rng=np.random.default_rng(0),
    )
    initial = _quadratic_fitness(es.mean)
    for _ in range(50):
        cands = es.ask()
        fits = np.array([_quadratic_fitness(x) for x in cands])
        es.tell(cands, fits)
    final = _quadratic_fitness(es.mean)
    assert final < initial / 10.0, f"final {final} not < initial/10 {initial/10}"


def test_convergence_sphere_40dim() -> None:
    """40-dim (Genome3D.c_factors サイズ) で 80 generation, 1/10 以下."""
    es = CMAESAdapter(
        dim=40,
        sigma0=0.5,
        mean0=np.full(40, 1.0),
        rng=np.random.default_rng(0),
    )
    initial = _quadratic_fitness(es.mean)
    for _ in range(80):
        cands = es.ask()
        fits = np.array([_quadratic_fitness(x) for x in cands])
        es.tell(cands, fits)
    final = _quadratic_fitness(es.mean)
    assert final < initial / 10.0


def test_convergence_with_offset() -> None:
    """Sphere の最適点が原点でない場合 (offset=3.0) も収束."""
    es = CMAESAdapter(
        dim=5,
        sigma0=0.5,
        mean0=np.full(5, 0.0),
        rng=np.random.default_rng(0),
    )
    for _ in range(60):
        cands = es.ask()
        fits = np.array([_quadratic_fitness(x, offset=3.0) for x in cands])
        es.tell(cands, fits)
    # mean should be near (3, 3, 3, 3, 3)
    np.testing.assert_allclose(es.mean, np.full(5, 3.0), atol=0.5)


# ---------------------------------------------------------------------------
# State updates: sigma, C, paths
# ---------------------------------------------------------------------------


def test_sigma_changes_after_tell() -> None:
    es = CMAESAdapter(dim=5, sigma0=0.5, rng=np.random.default_rng(0))
    sigma0 = es.sigma
    for _ in range(10):
        cands = es.ask()
        fits = np.array([_quadratic_fitness(x) for x in cands])
        es.tell(cands, fits)
    # Successful optimization → sigma should change (typically shrinks)
    assert es.sigma != sigma0


def test_covariance_remains_symmetric() -> None:
    es = CMAESAdapter(dim=8, sigma0=0.5, rng=np.random.default_rng(0))
    for _ in range(15):
        cands = es.ask()
        fits = np.array([_quadratic_fitness(x) for x in cands])
        es.tell(cands, fits)
    C = es.C
    np.testing.assert_allclose(C, C.T, atol=1e-10)


def test_covariance_positive_definite() -> None:
    """C remains positive semi-definite (all eigenvalues >= 0 up to FP noise)."""
    es = CMAESAdapter(dim=8, sigma0=0.5, rng=np.random.default_rng(0))
    for _ in range(15):
        cands = es.ask()
        fits = np.array([_quadratic_fitness(x) for x in cands])
        es.tell(cands, fits)
    eigvals = np.linalg.eigvalsh(0.5 * (es.C + es.C.T))
    assert eigvals.min() > -1e-8


def test_generation_counter() -> None:
    es = CMAESAdapter(dim=3, sigma0=0.5, rng=np.random.default_rng(0))
    assert es.generation == 0
    for i in range(5):
        cands = es.ask()
        fits = np.array([_quadratic_fitness(x) for x in cands])
        es.tell(cands, fits)
        assert es.generation == i + 1


# ---------------------------------------------------------------------------
# state_dict round-trip
# ---------------------------------------------------------------------------


def test_state_dict_roundtrip() -> None:
    es = CMAESAdapter(dim=5, sigma0=0.4, rng=np.random.default_rng(0))
    for _ in range(5):
        cands = es.ask()
        fits = np.array([_quadratic_fitness(x) for x in cands])
        es.tell(cands, fits)
    state = es.state_dict()

    # Build a fresh adapter and load
    es2 = CMAESAdapter(dim=5)
    es2.load_state_dict(state)

    np.testing.assert_allclose(es2.mean, es.mean)
    np.testing.assert_allclose(es2.C, es.C)
    assert es2.sigma == pytest.approx(es.sigma)
    assert es2.generation == es.generation
    assert es2.population_size == es.population_size


def test_state_dict_contains_expected_keys() -> None:
    es = CMAESAdapter(dim=5)
    s = es.state_dict()
    expected = {
        "dim", "sigma", "sigma0", "population_size", "mu", "mean", "C",
        "p_sigma", "p_c", "weights", "mu_eff", "cs", "cc", "c1", "cmu",
        "damps", "generation", "chi_n", "bounds",
    }
    assert expected.issubset(set(s.keys()))


def test_state_dict_json_safe_types() -> None:
    """state_dict() output should be JSON-serializable (lists, floats, ints)."""
    import json

    es = CMAESAdapter(dim=5, bounds=(-1.0, 1.0))
    s = es.state_dict()
    blob = json.dumps(s)
    restored = json.loads(blob)
    assert restored["dim"] == 5


def test_load_state_dim_mismatch() -> None:
    es5 = CMAESAdapter(dim=5)
    es10 = CMAESAdapter(dim=10)
    with pytest.raises(ValueError):
        es5.load_state_dict(es10.state_dict())


# ---------------------------------------------------------------------------
# sample_neighborhood — ThoughtFactorPerLayerChromosome compat
# ---------------------------------------------------------------------------


def test_sample_neighborhood_single() -> None:
    """40-dim x (= Genome3D.c_factors.as_flat() の典型 shape) で 1 neighbor."""
    es = CMAESAdapter(dim=40, sigma0=0.1, rng=np.random.default_rng(0))
    x = np.full(40, 0.5)  # ThoughtFactorPerLayerChromosome.default() の as_flat
    out = es.sample_neighborhood(x, n=1)
    assert out.shape == (40,)
    # Should be near x (sigma small)
    assert np.linalg.norm(out - x) < 2.0


def test_sample_neighborhood_many() -> None:
    es = CMAESAdapter(dim=10, sigma0=0.2, rng=np.random.default_rng(0))
    x = np.zeros(10)
    out = es.sample_neighborhood(x, n=7)
    assert out.shape == (7, 10)


def test_sample_neighborhood_invalid_n() -> None:
    es = CMAESAdapter(dim=5)
    with pytest.raises(ValueError):
        es.sample_neighborhood(np.zeros(5), n=0)


def test_sample_neighborhood_shape_mismatch() -> None:
    es = CMAESAdapter(dim=5)
    with pytest.raises(ValueError):
        es.sample_neighborhood(np.zeros(4), n=1)


def test_sample_neighborhood_sigma_zero() -> None:
    es = CMAESAdapter(dim=5, sigma0=0.0)
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    out = es.sample_neighborhood(x, n=3)
    np.testing.assert_allclose(out, np.tile(x, (3, 1)))


def test_sample_neighborhood_scales_with_sigma() -> None:
    """sigma が大きいほど neighborhood の散らばりも大きい (期待値)."""
    rng_seed = 123
    es_small = CMAESAdapter(
        dim=20, sigma0=0.01, rng=np.random.default_rng(rng_seed)
    )
    es_large = CMAESAdapter(
        dim=20, sigma0=1.0, rng=np.random.default_rng(rng_seed)
    )
    x = np.zeros(20)
    out_small = es_small.sample_neighborhood(x, n=100)
    out_large = es_large.sample_neighborhood(x, n=100)
    assert out_small.std() < out_large.std()


def test_sample_neighborhood_thought_factor_compat() -> None:
    """ThoughtFactorPerLayerChromosome.from_array() と shape 互換: (10, 4)."""
    from llive.perf.evolutionary.thought_factor_per_layer import (
        NUM_MEMORY_LAYERS,
        NUM_THOUGHT_FACTORS,
        ThoughtFactorPerLayerChromosome,
    )

    flat_dim = NUM_THOUGHT_FACTORS * NUM_MEMORY_LAYERS
    assert flat_dim == 40

    es = CMAESAdapter(
        dim=flat_dim,
        sigma0=0.05,
        bounds=(0.0, 1.0),  # match factor weight range
        rng=np.random.default_rng(0),
    )
    base = ThoughtFactorPerLayerChromosome.default()
    flat = base.as_flat()
    assert flat.shape == (flat_dim,)

    neighbor_flat = es.sample_neighborhood(flat, n=1)
    assert neighbor_flat.shape == (flat_dim,)
    # Reshape back & wrap as chromosome to confirm compatibility
    neighbor_mat = neighbor_flat.reshape(
        NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS
    )
    neighbor = ThoughtFactorPerLayerChromosome.from_array(neighbor_mat)
    arr = neighbor.as_array()
    assert arr.shape == (NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS)
    # All values in [0, 1] thanks to bounds + from_array clipping
    assert arr.min() >= 0.0
    assert arr.max() <= 1.0


# ---------------------------------------------------------------------------
# Reset / convenience
# ---------------------------------------------------------------------------


def test_reset_restores_initial_state() -> None:
    es = CMAESAdapter(dim=5, sigma0=0.5, rng=np.random.default_rng(0))
    for _ in range(8):
        cands = es.ask()
        fits = np.array([_quadratic_fitness(x) for x in cands])
        es.tell(cands, fits)
    assert es.generation == 8
    es.reset()
    assert es.generation == 0
    assert es.sigma == pytest.approx(0.5)
    np.testing.assert_allclose(es.mean, np.zeros(5))
    np.testing.assert_allclose(es.C, np.eye(5))


def test_best_so_far_returns_mean_copy() -> None:
    es = CMAESAdapter(dim=5, mean0=np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
    best = es.best_so_far()
    # Mutating return should not affect internal state
    best[0] = 999.0
    assert es.mean[0] == 1.0


def test_weights_sum_to_one() -> None:
    es = CMAESAdapter(dim=10)
    assert es.weights.sum() == pytest.approx(1.0)
    assert (es.weights > 0).all()


def test_weights_decreasing() -> None:
    """Recombination weights should be monotonically decreasing."""
    es = CMAESAdapter(dim=10)
    w = es.weights
    assert all(w[i] >= w[i + 1] for i in range(len(w) - 1))


def test_mu_eff_positive() -> None:
    es = CMAESAdapter(dim=10)
    assert es.mu_eff > 0


# ---------------------------------------------------------------------------
# CMAESState dataclass (smoke)
# ---------------------------------------------------------------------------


def test_cmaesstate_dataclass_smoke() -> None:
    """CMAESState dataclass is importable and instantiable."""
    s = CMAESState(
        dim=5,
        sigma=0.3,
        sigma0=0.3,
        population_size=8,
        mu=4,
        mean=np.zeros(5),
        C=np.eye(5),
        p_sigma=np.zeros(5),
        p_c=np.zeros(5),
        weights=np.array([0.4, 0.3, 0.2, 0.1]),
        mu_eff=2.5,
        cs=0.1,
        cc=0.1,
        c1=0.05,
        cmu=0.05,
        damps=1.5,
        generation=0,
        chi_n=2.0,
    )
    assert s.dim == 5
    assert s.mean.shape == (5,)
