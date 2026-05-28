# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/poc_cvt_map_elites.py.

CVT-MAP-Elites toy (Vassiliades, Chatzilygeroudis, Mouret 2018; fixed-k centroidal Voronoi
niches vs exploding b**D grid) の決定論的 verdict を固定。proxy・CPU・LLM/Docker ゼロ・
llive import ゼロ (隔離 toy)。

命題: 高次元 behavior 記述子 (D>=4) では grid MAP-Elites が cell 数 b**D 爆発で破綻
(空セル膨大・coverage 崩壊 / メモリ非現実的) するが、CVT (固定 k centroid に空間分割) は
固定 niche 数で高次元でも coverage / QD-score を保ち、同 budget で grid を上回る。
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

import poc_cvt_map_elites as cvt  # noqa: E402


# ---------------------------------------------------------------------------
# population: deterministic individuals in [0,1]^D with a smooth toy fitness
# ---------------------------------------------------------------------------
def test_generate_population_in_unit_cube_and_deterministic():
    b1, f1 = cvt.generate_population(budget=500, d=6, seed=0)
    b2, f2 = cvt.generate_population(budget=500, d=6, seed=0)
    np.testing.assert_array_equal(b1, b2)
    np.testing.assert_array_equal(f1, f2)
    assert b1.shape == (500, 6)
    # behaviors are clipped into the unit cube.
    assert b1.min() >= 0.0 and b1.max() <= 1.0
    # fitness is in [0,1] for points in [0,1]^D (1 - mean squared dist to centre).
    assert f1.min() >= 0.0 and f1.max() <= 1.0


def test_toy_fitness_peaks_at_centre():
    centre = np.full((1, 5), 0.5)
    corner = np.zeros((1, 5))
    assert cvt.toy_fitness(centre)[0] > cvt.toy_fitness(corner)[0]
    # centre is the maximum (fitness == 1.0 there).
    assert abs(cvt.toy_fitness(centre)[0] - 1.0) < 1e-12


# ---------------------------------------------------------------------------
# grid cell-count explosion + sparse encoding
# ---------------------------------------------------------------------------
def test_grid_total_cells_explodes_with_dimension():
    # b**D — the quantity that blows up. Python int (arbitrary precision) so no overflow.
    assert cvt.grid_total_cells(10, 2) == 100
    assert cvt.grid_total_cells(10, 4) == 10_000
    assert cvt.grid_total_cells(10, 6) == 1_000_000
    assert cvt.grid_total_cells(10, 8) == 100_000_000


def test_grid_cell_index_is_mixed_radix_and_distinguishes_cells():
    # two points in clearly different per-axis bins map to different codes.
    pts = np.array([[0.05, 0.05], [0.95, 0.95]])
    codes = cvt.grid_cell_index(pts, bins=10)
    assert codes[0] != codes[1]
    # point in bin (0,0) encodes to 0; point in bin (9,9) encodes to 9*10+9 = 99.
    assert codes[0] == 0
    assert codes[1] == 99


def test_grid_keeps_best_elite_per_cell():
    # two individuals in the SAME cell -> archive keeps the higher fitness only.
    behaviors = np.array([[0.5, 0.5], [0.5, 0.5]])
    fitness = np.array([0.3, 0.9])
    res = cvt.run_grid_map_elites(behaviors, fitness, bins=10)
    assert res["occupied_niches"] == 1
    assert res["qd_score"] == 0.9            # best of the two
    assert res["mean_elite_fitness"] == 0.9


# ---------------------------------------------------------------------------
# CVT: k-means centroids + nearest-centroid assignment
# ---------------------------------------------------------------------------
def test_kmeans_centroids_fixed_count_independent_of_dimension():
    rng = np.random.default_rng(0)
    for d in (2, 4, 8):
        samples = rng.uniform(0, 1, (1000, d))
        cents = cvt.kmeans_centroids(samples, k=32, iters=10, seed=0)
        # niche count is k regardless of D — the whole point of CVT scaling.
        assert cents.shape == (32, d)


def test_kmeans_centroids_deterministic_for_fixed_seed():
    rng = np.random.default_rng(1)
    samples = rng.uniform(0, 1, (500, 4))
    c1 = cvt.kmeans_centroids(samples, k=16, iters=10, seed=2)
    c2 = cvt.kmeans_centroids(samples, k=16, iters=10, seed=2)
    np.testing.assert_array_equal(c1, c2)


def test_assign_nearest_centroid_picks_closest():
    centroids = np.array([[0.0, 0.0], [1.0, 1.0]])
    behaviors = np.array([[0.1, 0.1], [0.9, 0.9], [0.2, 0.0]])
    assign = cvt.assign_nearest_centroid(behaviors, centroids)
    np.testing.assert_array_equal(assign, np.array([0, 1, 0]))


def test_cvt_keeps_best_elite_per_niche_and_fixed_denominator():
    behaviors, fitness = cvt.generate_population(budget=800, d=6, seed=0)
    res = cvt.run_cvt_map_elites(
        behaviors, fitness, k=64, n_samples=2000, kmeans_iters=15, seed=0
    )
    # denominator is the (fixed) centroid count, independent of D.
    assert res["total_niches"] == res["k"] == 64
    assert res["coverage"] == res["occupied_niches"] / 64
    assert 0.0 < res["coverage"] <= 1.0
    # mean elite fitness == qd_score / occupied (the fair, niche-count-normalised measure).
    assert abs(res["mean_elite_fitness"] - res["qd_score"] / res["occupied_niches"]) < 1e-12


# ---------------------------------------------------------------------------
# coverage collapse vs scaling: the core mechanism at D=8
# ---------------------------------------------------------------------------
def test_grid_coverage_collapses_at_high_dimension():
    behaviors, fitness = cvt.generate_population(budget=2000, d=8, seed=0)
    grid = cvt.run_grid_map_elites(behaviors, fitness, bins=10)
    # nominal 1e8 cells but only ~budget individuals -> coverage near zero (collapse).
    assert grid["total_niches"] == 100_000_000
    assert grid["coverage"] < 1e-4


def test_cvt_coverage_holds_at_high_dimension():
    behaviors, fitness = cvt.generate_population(budget=2000, d=8, seed=0)
    res = cvt.run_cvt_map_elites(
        behaviors, fitness, k=256, n_samples=5000, kmeans_iters=25, seed=0
    )
    # CVT fills almost all of its fixed k niches even at D=8.
    assert res["coverage"] > 0.5


# ---------------------------------------------------------------------------
# the niche-count confound (the design trap, made explicit and tested)
# ---------------------------------------------------------------------------
def test_raw_qd_score_is_confounded_but_mean_elite_is_fair():
    # at high D, grid's RAW QD-score sum exceeds CVT's purely because grid has far more
    # occupied niches (one individual per cell) — NOT because grid elites are better.
    behaviors, fitness = cvt.generate_population(budget=2000, d=8, seed=0)
    grid = cvt.run_grid_map_elites(behaviors, fitness, bins=10)
    cvt_res = cvt.run_cvt_map_elites(
        behaviors, fitness, k=256, n_samples=5000, kmeans_iters=25, seed=0
    )
    # confounded raw sum favours grid (more terms summed)...
    assert grid["qd_score"] > cvt_res["qd_score"]
    assert grid["occupied_niches"] > cvt_res["occupied_niches"]
    # ...but the fair per-niche mean elite quality favours CVT.
    assert cvt_res["mean_elite_fitness"] >= grid["mean_elite_fitness"]


# ---------------------------------------------------------------------------
# deterministic composite verdict (seed 0)
# ---------------------------------------------------------------------------
def test_verdict_cvt_scales_to_high_dim_seed0():
    out = cvt.run(seed=0)
    v = out["verdict"]
    # (1) coverage: CVT strictly beats grid at every high-D point.
    assert v["high_d_coverage_wins"] is True
    # (2) fair QD: CVT mean-elite >= grid mean-elite at every high-D point.
    assert v["high_d_qd_non_inferior"] is True
    assert v["qd_metric_used"] == "mean_elite_fitness_per_occupied_niche"
    # headline composite AND-gate verdict.
    assert v["cvt_scales_to_high_dim"] is True
    # honest transparency: the RAW (confounded) QD-score does favour grid at high D.
    assert v["raw_qd_score_favours_grid_high_d"] is True
    # honest low-D finding: grid is competitive at low D (CVT not needed there).
    assert v["grid_competitive_at_low_d"] is True


def test_verdict_per_dim_shows_coverage_explosion_ratio():
    out = cvt.run(seed=0)
    rows = {r["d"]: r for r in out["per_dim"]}
    # grid nominal niche count follows b**D exactly.
    assert rows[2]["grid_total_niches"] == 100
    assert rows[8]["grid_total_niches"] == 100_000_000
    # CVT niche count is the fixed k at every dimension.
    assert all(r["cvt_total_niches"] == out["config"]["k"] for r in out["per_dim"])
    # coverage advantage of CVT over grid GROWS sharply with dimension.
    assert rows[8]["cvt_coverage_over_grid_ratio"] > rows[6]["cvt_coverage_over_grid_ratio"]
    assert rows[6]["cvt_coverage_over_grid_ratio"] > rows[4]["cvt_coverage_over_grid_ratio"]
    # at D=2 the two schemes are comparable (grid is competitive / equal).
    assert rows[2]["cvt_coverage_over_grid_ratio"] <= 1.5


def test_verdict_is_deterministic_for_fixed_seed():
    a = cvt.run(seed=1)["verdict"]
    b = cvt.run(seed=1)["verdict"]
    assert a == b  # same seed -> identical verdict dict


def test_verdict_holds_across_several_seeds():
    # the mechanism is not a single-seed fluke: it holds across a small seed sweep.
    for s in range(5):
        v = cvt.run(seed=s)["verdict"]
        assert v["cvt_scales_to_high_dim"] is True, f"failed at seed {s}"


def test_k_sensitivity_verdict_robust():
    # k is a hyperparameter; the headline verdict holds across a range of k.
    for k in (64, 128, 512):
        v = cvt.run(seed=0, k=k)["verdict"]
        assert v["cvt_scales_to_high_dim"] is True, f"failed at k={k}"


# ---------------------------------------------------------------------------
# schema + honest disclosure
# ---------------------------------------------------------------------------
def test_output_schema_and_honest_notes_present():
    out = cvt.run(seed=0)
    assert out["schema"] == "poc_cvt_map_elites/v1"
    assert "proposition" in out and out["proposition"]
    # honest disclosure: notes must mention the proxy/llive-isolation, the QD-score confound,
    # and the low-D caveat.
    notes = " ".join(out["honest_notes"])
    assert "proxy" in notes.lower()
    assert "llive" in notes.lower()
    assert "qd-score" in notes.lower()       # raw-QD confound disclosed
    assert "aurora" in notes.lower()         # partner-PoC linkage disclosed
    # the verdict carries the falsifiable boolean.
    assert "cvt_scales_to_high_dim" in out["verdict"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
