# SPDX-License-Identifier: Apache-2.0
"""Tests for cosine_variants — bit-similar parity check.

4 variants は実装系が違っても **同じ入力に対し ε 以内で同じ結果を返す**
ことを保証する (浮動小数の桁数差は許容).
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from llive.perf.variants.cosine_variants import (
    ALL_VARIANTS,
    cosine_numpy_dot,
    cosine_numpy_einsum,
    cosine_numpy_normalized,
    cosine_pure_python,
)


_EPS = 1e-9


def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


@pytest.mark.parametrize("dim", [3, 16, 128, 768])
def test_unnormalized_variants_agree(dim: int) -> None:
    """pure_python / numpy_dot / numpy_einsum は同じ入力で同じ値."""
    rng = np.random.default_rng(2026 + dim)
    a = rng.normal(size=dim)
    b = rng.normal(size=dim)
    r_pure = cosine_pure_python(a, b)
    r_dot = cosine_numpy_dot(a, b)
    r_ein = cosine_numpy_einsum(a, b)
    assert math.isclose(r_pure, r_dot, abs_tol=_EPS)
    assert math.isclose(r_dot, r_ein, abs_tol=_EPS)


@pytest.mark.parametrize("dim", [3, 16, 128])
def test_normalized_variant_matches_when_preconditioned(dim: int) -> None:
    """事前 L2 normalize した入力なら numpy_normalized も他 variant と一致."""
    rng = np.random.default_rng(7 + dim)
    a = _normalize(rng.normal(size=dim))
    b = _normalize(rng.normal(size=dim))
    r_dot = cosine_numpy_dot(a, b)
    r_norm = cosine_numpy_normalized(a, b)
    assert math.isclose(r_dot, r_norm, abs_tol=_EPS)


def test_zero_vector_returns_zero() -> None:
    z = np.zeros(8)
    v = np.arange(1.0, 9.0)
    for name, fn in ALL_VARIANTS:
        if name == "numpy_normalized":
            # normalized 前提 variant は safe-input guarantee なし.
            continue
        assert fn(z, v) == 0.0, f"{name} should return 0.0 for zero vector"


def test_self_similarity_one() -> None:
    rng = np.random.default_rng(0)
    v = rng.normal(size=64)
    for name, fn in ALL_VARIANTS:
        if name == "numpy_normalized":
            v_norm = _normalize(v)
            assert math.isclose(fn(v_norm, v_norm), 1.0, abs_tol=_EPS)
        else:
            assert math.isclose(fn(v, v), 1.0, abs_tol=_EPS)


def test_all_variants_are_callable() -> None:
    for name, fn in ALL_VARIANTS:
        assert callable(fn), f"{name} must be callable"
    assert len({n for n, _ in ALL_VARIANTS}) == len(ALL_VARIANTS)  # 名前重複なし
