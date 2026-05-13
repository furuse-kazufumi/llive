"""RUST-13 — parity tests for the optional Rust acceleration layer.

The pure-Python fallback in :mod:`llive.rust_ext` and the compiled Rust
crate must produce **bit-equivalent** results (within 1e-6). Both backends
are exercised regardless of whether the Rust extension is installed:

* If ``HAS_RUST is True``, we directly compare the Rust kernel against the
  Python fallback (held in ``llive.rust_ext._compute_surprise_py``).
* If the Rust extension is absent, only the Python path is exercised —
  these tests still pass because the fallback is the reference
  implementation.

When iterating on the Rust crate, run::

    maturin develop --release --manifest-path crates/llive_rust_ext/Cargo.toml
    pytest tests/property/test_rust_python_parity.py
"""

from __future__ import annotations

import math
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from llive import rust_ext
from llive.rust_ext import _bulk_time_decay_py, _compute_surprise_py, _jaccard_py


def _isclose(a: float, b: float, tol: float = 1e-6) -> bool:
    if math.isnan(a) or math.isnan(b):
        return False
    return abs(a - b) <= tol


@settings(max_examples=50, deadline=None)
@given(
    new=st.lists(st.floats(min_value=-3.0, max_value=3.0, allow_nan=False), min_size=8, max_size=16),
    mem=st.lists(
        st.lists(st.floats(min_value=-3.0, max_value=3.0, allow_nan=False), min_size=8, max_size=16),
        min_size=0,
        max_size=8,
    ),
)
def test_compute_surprise_parity(new, mem):
    if mem and any(len(row) != len(new) for row in mem):
        # Stress the dimension-mismatch path on both backends
        with pytest.raises((ValueError, Exception)):
            rust_ext.compute_surprise(new, mem)
        return
    surprise_py = _compute_surprise_py(list(new), [list(r) for r in mem])
    surprise_active = rust_ext.compute_surprise(list(new), [list(r) for r in mem])
    assert _isclose(surprise_py, surprise_active), (surprise_py, surprise_active)


@settings(max_examples=50, deadline=None)
@given(
    a=st.lists(st.integers(min_value=0, max_value=1000), min_size=0, max_size=20),
    b=st.lists(st.integers(min_value=0, max_value=1000), min_size=0, max_size=20),
)
def test_jaccard_parity(a, b):
    py = _jaccard_py(sorted(set(a)), sorted(set(b)))
    active = rust_ext.jaccard(a, b)
    assert _isclose(py, active), (py, active)


def test_compute_surprise_empty_memory_returns_one():
    assert rust_ext.compute_surprise([1.0, 0.0, 0.0], []) == 1.0


def test_compute_surprise_identical_vector_returns_zero():
    v = [1.0, 2.0, 3.0]
    assert _isclose(rust_ext.compute_surprise(v, [v]), 0.0)


def test_jaccard_identical_sets_returns_one():
    assert rust_ext.jaccard([1, 2, 3], [3, 2, 1]) == 1.0


def test_jaccard_disjoint_sets_returns_zero():
    assert rust_ext.jaccard([1, 2, 3], [4, 5, 6]) == 0.0


def test_jaccard_empty_pair_returns_one():
    assert rust_ext.jaccard([], []) == 1.0


def test_backend_metadata_consistent():
    # Either Rust or python path; both must populate __backend__ + __version__
    assert rust_ext.__backend__ in {"rust", "python"}
    assert isinstance(rust_ext.__version__, str)
    assert rust_ext.HAS_RUST is (rust_ext.__backend__ == "rust")


def test_dim_mismatch_raises():
    with pytest.raises((ValueError, Exception)):
        rust_ext.compute_surprise([1.0, 2.0], [[1.0, 2.0, 3.0]])


def test_deterministic_under_seeded_random():
    rng = random.Random(42)
    new = [rng.uniform(-1, 1) for _ in range(8)]
    mem = [[rng.uniform(-1, 1) for _ in range(8)] for _ in range(4)]
    a = rust_ext.compute_surprise(list(new), [list(r) for r in mem])
    b = rust_ext.compute_surprise(list(new), [list(r) for r in mem])
    assert a == b
