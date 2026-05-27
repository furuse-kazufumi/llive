# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/poc_aurora_descriptors.py.

AURORA-style data-driven QD descriptor toy (Cully 2019; learned + container-refreshed
behavior descriptor) の決定論的 verdict を固定。proxy・CPU・LLM/Docker ゼロ・
llive import ゼロ (隔離 toy)。

命題: 行動信号からデータ駆動で低次元記述子を学習 (PCA/SVD) し periodic に refresh して
QD archive を張ると、(a) ハンドコード記述子が取りこぼす行動分散軸を捉え、(b) archive
coverage / 行動多様性がハンドコード記述子と同等以上になる。
([[feedback_staged_poc_individual_structure]] / [[feedback_benchmark_honest_disclosure]])
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import poc_aurora_descriptors as aur  # noqa: E402


# ---------------------------------------------------------------------------
# behavior generator: the handcoded blind spot is real
# ---------------------------------------------------------------------------
def test_handcoded_dims_are_low_variance_blind_spot():
    behaviors, _R, _latent = aur.generate_behaviors(
        n=800, d=12, n_factors=4, seed=0, hi_var=1.0, lo_var=0.02
    )
    var = np.var(behaviors, axis=0)
    # dims 0,1 (the handcoded axes) carry far less variance than the rest of the vector.
    assert var[0] < 0.01 and var[1] < 0.01
    assert var[2:].mean() > 10 * var[:2].mean()


def test_handcoded_dims_are_near_collinear():
    behaviors, _R, _latent = aur.generate_behaviors(
        n=800, d=12, n_factors=4, seed=0, hi_var=1.0, lo_var=0.02
    )
    # dims 0,1 are a near-degenerate (collinear) readout of the same factor -> highly
    # correlated, so binning on them collapses to a near-1D diagonal (the failure mode).
    corr = np.corrcoef(behaviors[:, 0], behaviors[:, 1])[0, 1]
    assert corr > 0.9


def test_generate_behaviors_is_deterministic():
    a, _, _ = aur.generate_behaviors(n=200, d=10, n_factors=3, seed=3, hi_var=1.0, lo_var=0.02)
    b, _, _ = aur.generate_behaviors(n=200, d=10, n_factors=3, seed=3, hi_var=1.0, lo_var=0.02)
    np.testing.assert_array_equal(a, b)


# ---------------------------------------------------------------------------
# PCA fit / projection: top-2 variance directions, deterministic sign
# ---------------------------------------------------------------------------
def test_fit_pca_recovers_dominant_variance_direction():
    rng = np.random.default_rng(0)
    n = 500
    # data with variance concentrated along axis 0 (>> axis 1 >> axis 2).
    data = np.zeros((n, 3))
    data[:, 0] = rng.normal(0, 5.0, n)
    data[:, 1] = rng.normal(0, 1.0, n)
    data[:, 2] = rng.normal(0, 0.1, n)
    _mean, comps = aur.fit_pca(data, k=2)
    assert comps.shape == (2, 3)
    # first PC aligns with axis 0 (|cos| ~ 1); second with axis 1.
    assert abs(comps[0, 0]) > 0.95
    assert abs(comps[1, 1]) > 0.9


def test_fit_pca_sign_is_pinned_deterministic():
    rng = np.random.default_rng(1)
    data = rng.normal(0, 1, (300, 5))
    _m1, c1 = aur.fit_pca(data, k=2)
    _m2, c2 = aur.fit_pca(data, k=2)
    np.testing.assert_array_equal(c1, c2)
    # sign convention: the largest-magnitude entry of each component is positive.
    for i in range(c1.shape[0]):
        j = int(np.argmax(np.abs(c1[i])))
        assert c1[i, j] > 0


def test_pca_projection_captures_more_variance_than_two_low_var_dims():
    behaviors, _R, _latent = aur.generate_behaviors(
        n=800, d=12, n_factors=4, seed=0, hi_var=1.0, lo_var=0.02
    )
    mean, comps = aur.fit_pca(behaviors, k=2)
    proj = aur.pca_project(behaviors, mean, comps)
    hc = aur.handcoded_descriptor(behaviors, dims=(0, 1))
    assert aur.captured_variance(behaviors, proj) > aur.captured_variance(behaviors, hc)


# ---------------------------------------------------------------------------
# grid coverage: range-normalised occupied-cell fraction
# ---------------------------------------------------------------------------
def test_grid_coverage_full_spread_vs_degenerate():
    bins = 8
    # a well-spread 2D cloud occupies many cells.
    rng = np.random.default_rng(0)
    spread = rng.uniform(-1, 1, (2000, 2))
    cov_spread, occ_spread, total = aur.grid_coverage(spread, bins=bins)
    assert total == bins * bins
    # a near-1D (collinear) cloud collapses onto a diagonal -> few cells.
    t = rng.uniform(-1, 1, 2000)
    degenerate = np.stack([t, t + rng.normal(0, 1e-3, 2000)], axis=1)
    cov_deg, occ_deg, _ = aur.grid_coverage(degenerate, bins=bins)
    # the diagonal cloud hugs the main diagonal, so it occupies only a small fraction of
    # the grid (~the bins along the diagonal, a little spillover from the tiny jitter),
    # far fewer than a full 2D spread.
    assert occ_deg < occ_spread / 2
    assert cov_spread > cov_deg


def test_grid_coverage_empty_is_zero():
    cov, occ, total = aur.grid_coverage(np.empty((0, 2)), bins=10)
    assert cov == 0.0 and occ == 0 and total == 100


def test_grid_coverage_handles_zero_span_axis():
    # one axis constant -> span guard prevents div-by-zero; all points share that axis bin.
    pts = np.stack([np.linspace(0, 1, 50), np.full(50, 0.5)], axis=1)
    cov, occ, total = aur.grid_coverage(pts, bins=10)
    assert occ >= 1 and cov > 0.0


# ---------------------------------------------------------------------------
# container refresh: periodic re-fit history
# ---------------------------------------------------------------------------
def test_aurora_refresh_history_recorded():
    behaviors, _R, _latent = aur.generate_behaviors(
        n=800, d=12, n_factors=4, seed=0, hi_var=1.0, lo_var=0.02
    )
    res = aur.run_aurora_with_refresh(
        behaviors=behaviors, bins=16, refresh_every=200, batch=100
    )
    # at least one refresh, history entries grow in collected count.
    assert res["n_refreshes"] >= 1
    after_ns = [h["after_n"] for h in res["refresh_history"]]
    assert after_ns == sorted(after_ns)
    assert after_ns[-1] <= behaviors.shape[0]
    # final descriptor projects the full set -> coverage in (0,1].
    assert 0.0 < res["coverage"] <= 1.0


# ---------------------------------------------------------------------------
# deterministic verdict: AURORA matches-or-beats handcoded (seed 0)
# ---------------------------------------------------------------------------
def test_verdict_aurora_matches_or_beats_handcoded_seed0():
    out = aur.run(seed=0)
    v = out["verdict"]
    # (b) coverage non-inferior: AURORA >= handcoded (here strongly better — handcoded's
    #     degenerate blind-spot axes collapse the archive).
    assert v["aurora_coverage"] >= v["handcoded_coverage"]
    assert v["coverage_non_inferior"] is True
    # (a) blind-spot capture: AURORA's learned axes capture far more behavior variance.
    assert v["aurora_captured_variance"] > v["handcoded_captured_variance"]
    assert v["captures_blind_spot"] is True
    # headline deterministic verdict.
    assert v["aurora_matches_or_beats_handcoded"] is True
    # sanity on the margins (robust, not knife-edge).
    assert v["coverage_ratio_aurora_over_handcoded"] > 2.0
    assert v["variance_ratio_aurora_over_handcoded"] > 100.0


def test_verdict_is_deterministic_for_fixed_seed():
    a = aur.run(seed=1)["verdict"]
    b = aur.run(seed=1)["verdict"]
    assert a == b  # same seed -> identical verdict dict


def test_verdict_holds_across_several_seeds():
    # the mechanism is not a single-seed fluke: it holds across a small seed sweep.
    for s in range(6):
        v = aur.run(seed=s)["verdict"]
        assert v["aurora_matches_or_beats_handcoded"] is True, f"failed at seed {s}"


def test_output_schema_and_honest_notes_present():
    out = aur.run(seed=0)
    assert out["schema"] == "poc_aurora_descriptors/v1"
    assert "proposition" in out and out["proposition"]
    # honest disclosure: notes must mention the proxy/llive-isolation and the linear-PCA caveat.
    notes = " ".join(out["honest_notes"])
    assert "proxy" in notes.lower()
    assert "llive" in notes.lower()
    assert "pca" in notes.lower()  # linear-vs-autoencoder caveat present
    # the verdict carries the falsifiable boolean.
    assert "aurora_matches_or_beats_handcoded" in out["verdict"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
