# SPDX-License-Identifier: Apache-2.0
"""Parity tests for decay_variants."""
from __future__ import annotations

import math

import numpy as np
import pytest

from llive.perf.variants.decay_variants import (
    ALL_VARIANTS,
    NUMPY_VARIANTS,
    PYTHON_VARIANTS,
    decay_numpy_einsum,
    decay_numpy_inplace,
    decay_python_listcomp,
    decay_python_loop,
    decay_python_map,
)

_EPS = 1e-12


@pytest.mark.parametrize("n", [0, 1, 10, 100, 1000])
def test_python_variants_parity(n: int) -> None:
    """全 python variant が同じ結果を返す."""
    rng = np.random.default_rng(n + 1)
    weights = list(rng.uniform(0.0, 10.0, size=n))
    rate = 0.95

    r_loop = decay_python_loop(weights, rate)
    r_lc = decay_python_listcomp(weights, rate)
    r_map = decay_python_map(weights, rate)

    assert len(r_loop) == n
    for a, b in zip(r_loop, r_lc):
        assert math.isclose(a, b, abs_tol=_EPS)
    for a, b in zip(r_loop, r_map):
        assert math.isclose(a, b, abs_tol=_EPS)


@pytest.mark.parametrize("n", [0, 1, 10, 100, 1000])
def test_numpy_variants_parity(n: int) -> None:
    rng = np.random.default_rng(n + 7)
    weights = rng.uniform(0.0, 10.0, size=n)
    rate = 0.95

    r_in = decay_numpy_inplace(weights, rate)
    r_ein = decay_numpy_einsum(weights, rate)

    assert r_in.shape == (n,)
    assert r_ein.shape == (n,)
    np.testing.assert_allclose(r_in, r_ein, atol=_EPS)


def test_python_and_numpy_results_match() -> None:
    rng = np.random.default_rng(0)
    weights = rng.uniform(0.0, 10.0, size=64)
    rate = 0.8
    r_py = decay_python_listcomp(list(weights), rate)
    r_np = decay_numpy_inplace(weights, rate)
    for a, b in zip(r_py, r_np):
        assert math.isclose(a, b, abs_tol=_EPS)


def test_input_not_mutated_for_numpy_inplace() -> None:
    """decay_numpy_inplace は input array を変更しない (copy する)."""
    w = np.array([1.0, 2.0, 3.0])
    snap = w.copy()
    _ = decay_numpy_inplace(w, 0.5)
    np.testing.assert_array_equal(w, snap)


def test_zero_rate() -> None:
    weights = [1.0, 2.0, 3.0]
    for name, fn in PYTHON_VARIANTS:
        r = fn(weights, 0.0)
        assert all(x == 0.0 for x in r)
    for name, fn in NUMPY_VARIANTS:
        r = fn(np.asarray(weights), 0.0)
        np.testing.assert_array_equal(r, np.zeros(3))


def test_one_rate_is_identity() -> None:
    weights = [1.0, 2.0, 3.0]
    for name, fn in PYTHON_VARIANTS:
        r = fn(weights, 1.0)
        for a, b in zip(r, weights):
            assert math.isclose(a, b, abs_tol=_EPS)


def test_all_variants_callable() -> None:
    for name, fn in ALL_VARIANTS:
        assert callable(fn), f"{name} not callable"
    assert len({n for n, _ in ALL_VARIANTS}) == len(ALL_VARIANTS)
