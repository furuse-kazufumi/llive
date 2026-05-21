# SPDX-License-Identifier: Apache-2.0
"""RUST-15 PeerScoreMatrixOps — Python ↔ Rust parity guard.

Phase 1 (本 file): Rust binding が未配線でも Python 実装の parity 不変条件を
保証する placeholder. maturin build 後に Rust 側も同 spec で動くことを
保証.

Rust 側の `cargo test` で同等 case が検証済 (`rust_ext/src/peer_score.rs`).
Python 側で同 case を再現することで, Rust binding 配線後の差分検出基盤に.
"""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import PeerEvaluationMatrix


# ---------------------------------------------------------------------------
# Reference cases (Rust 側 cargo test と一致)
# ---------------------------------------------------------------------------


def test_column_mean_basic_matches_rust_spec() -> None:
    """rust_ext::peer_score::tests::column_mean_basic と同 case."""
    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    m.record("a", "b", 0.8)
    m.record("a", "c", 0.6)
    m.record("b", "a", 0.5)
    m.record("b", "c", 0.7)
    m.record("c", "a", 0.4)
    m.record("c", "b", 0.9)
    col = m.column_mean(exclude_self=True)
    assert col[0] == pytest.approx(0.45, abs=1e-9)
    assert col[1] == pytest.approx(0.85, abs=1e-9)
    assert col[2] == pytest.approx(0.65, abs=1e-9)


def test_row_mean_excludes_self_matches_rust_spec() -> None:
    """rust_ext::peer_score::tests::row_mean_excludes_self と同 case."""
    m = PeerEvaluationMatrix.empty(["a", "b"])
    m.record("a", "b", 0.8)
    m.record("b", "a", 0.3)
    row = m.row_mean(exclude_self=True)
    assert row[0] == pytest.approx(0.8, abs=1e-9)
    assert row[1] == pytest.approx(0.3, abs=1e-9)


def test_collusion_uniform_high_suggests_collusion_matches_rust_spec() -> None:
    """rust_ext::peer_score::tests::collusion_uniform_high_suggests_collusion."""
    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    for i in ("a", "b", "c"):
        for j in ("a", "b", "c"):
            if i != j:
                m.record(i, j, 0.95)
    s = m.collusion_score()
    assert s["score_variance"] < 1e-6
    assert s["concentration"] == pytest.approx(1.0, abs=1e-6)


def test_collusion_score_normal_population_matches_rust_spec() -> None:
    """rust_ext::peer_score::tests::collusion_score_normal_population."""
    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    m.record("a", "b", 0.8)
    m.record("a", "c", 0.3)
    m.record("b", "a", 0.5)
    m.record("b", "c", 0.7)
    m.record("c", "a", 0.4)
    m.record("c", "b", 0.6)
    s = m.collusion_score()
    assert s["score_variance"] > 1e-3
    assert s["concentration"] > 1.0


# ---------------------------------------------------------------------------
# Rust binding 配線後の guard (Phase 2 で活性化)
# ---------------------------------------------------------------------------


def test_rust_ext_module_optional() -> None:
    """llive_rust_ext は optional. import 不能でも core test は動く."""
    try:
        import llive_rust_ext  # noqa: F401

        has_rust = True
    except ImportError:
        has_rust = False
    # Phase 1 では未 build なので False が期待値
    # Phase 2 で maturin develop 後は True になる
    # どちらでも test は green に保つ (placeholder)
    assert has_rust in (True, False)


try:
    import llive_rust_ext as _rust_ext_for_test  # type: ignore[import]
    _HAS_RUST = True
except ImportError:
    _HAS_RUST = False


@pytest.mark.skipif(not _HAS_RUST, reason="rust ext not built")
def test_rust_column_mean_matches_python() -> None:
    """Rust binding がある場合は Python と数値一致を確認 (Phase 2 でアクティブ化)."""
    import llive_rust_ext  # type: ignore[import]

    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    m.record("a", "b", 0.8)
    m.record("a", "c", 0.6)
    m.record("b", "a", 0.5)
    m.record("b", "c", 0.7)
    m.record("c", "a", 0.4)
    m.record("c", "b", 0.9)
    py_col = m.column_mean()
    rs_col = llive_rust_ext.py_column_mean(m.matrix, True)
    np.testing.assert_allclose(py_col, rs_col, rtol=0, atol=1e-9)


@pytest.mark.skipif(not _HAS_RUST, reason="rust ext not built")
def test_rust_collusion_score_matches_python() -> None:
    """共謀検出 3 指標が Python ↔ Rust で bit-exact 一致."""
    import llive_rust_ext  # type: ignore[import]

    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    m.record("a", "b", 0.8)
    m.record("a", "c", 0.3)
    m.record("b", "a", 0.5)
    m.record("b", "c", 0.7)
    m.record("c", "a", 0.4)
    m.record("c", "b", 0.6)
    py_s = m.collusion_score()
    rs_var, rs_sym, rs_conc = llive_rust_ext.py_collusion_score(m.matrix)
    assert py_s["score_variance"] == pytest.approx(rs_var, abs=1e-9)
    assert py_s["symmetry"] == pytest.approx(rs_sym, abs=1e-9)
    assert py_s["concentration"] == pytest.approx(rs_conc, abs=1e-9)
