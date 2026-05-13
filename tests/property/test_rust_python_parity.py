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


# ---------------------------------------------------------------------------
# bulk_time_decay (RUST-03 baseline)
# ---------------------------------------------------------------------------

_REL_STRATEGY = st.sampled_from(["linked_concept", "co_occurs_with", "temporal_after", "unknown"])
_EDGE_STRATEGY = st.tuples(
    _REL_STRATEGY,
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)


@settings(max_examples=50, deadline=None)
@given(
    edges=st.lists(_EDGE_STRATEGY, min_size=0, max_size=30),
    tau_linked=st.floats(min_value=0.5, max_value=60.0, allow_nan=False),
    tau_coocc=st.floats(min_value=0.5, max_value=60.0, allow_nan=False),
)
def test_bulk_time_decay_parity(edges, tau_linked, tau_coocc):
    tau_map = {"linked_concept": tau_linked, "co_occurs_with": tau_coocc, "temporal_after": 14.0}
    py = _bulk_time_decay_py(edges, tau_map)
    active = rust_ext.bulk_time_decay(edges, tau_map)
    assert len(py) == len(active)
    for a, b in zip(py, active, strict=True):
        assert _isclose(a, b, tol=1e-9), (a, b)


def test_bulk_time_decay_unknown_rel_passthrough():
    edges = [("unknown_rel", 0.7, 12.0)]
    out = rust_ext.bulk_time_decay(edges, {"linked_concept": 30.0})
    assert out == [0.7]


def test_bulk_time_decay_zero_tau_passthrough():
    edges = [("foo", 0.5, 7.0)]
    out = rust_ext.bulk_time_decay(edges, {"foo": 0.0})
    assert out == [0.5]


def test_bulk_time_decay_empty_input():
    assert rust_ext.bulk_time_decay([], {"x": 10.0}) == []


def test_bulk_time_decay_known_value():
    # exp(-7 / 14) ≈ 0.6065306597126334
    out = rust_ext.bulk_time_decay([("linked_concept", 1.0, 7.0)], {"linked_concept": 14.0})
    assert _isclose(out[0], math.exp(-0.5), tol=1e-6)
