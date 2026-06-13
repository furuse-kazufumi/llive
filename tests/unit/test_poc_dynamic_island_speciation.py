# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/poc_dynamic_island_speciation.py.

Dynamic Island / Speciation toy (Island GA: Cohoon 1987 / NEAT speciation: Stanley 2002 /
dynamic deme formation) の決定論的 verdict を固定。proxy・CPU・LLM/Docker ゼロ・llive
import ゼロ (隔離 toy; frozen な src/llive/perf/evolutionary/island_model.py は未 import/未改変)。

命題: 集団を behavior/genome 空間で k-means により動的に島(deme)へ分割し、島ごとに独立進化
+ 周期 migration + 収束島マージを行うと、単一集団 (panmictic) より多峰 fitness 地形で
複数の峰を同時に保持し、早期収束を回避して最終多様性/被覆が高い。
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

import poc_dynamic_island_speciation as isl  # noqa: E402


# ---------------------------------------------------------------------------
# multimodal landscape: separated Gaussian peaks
# ---------------------------------------------------------------------------
def test_make_peaks_shapes_and_positive_heights():
    centres, heights = isl.make_peaks(K=6, d=4, spread=6.0, seed=0)
    assert centres.shape == (6, 4)
    assert heights.shape == (6,)
    assert np.all(heights > 0)  # heights are abs() -> strictly positive


def test_fitness_is_max_over_peaks_and_peaks_are_high():
    centres, heights = isl.make_peaks(K=3, d=2, spread=6.0, seed=0)
    # an individual sitting exactly on peak k gets ~ height_k (the max-over-peaks bump).
    on_peak = centres.copy()
    f = isl.fitness(on_peak, centres, heights, sigma=1.0)
    # each on-centre point scores at least its own peak height (max over peaks >= own peak).
    assert np.all(f >= heights - 1e-9)
    # a point far from every peak scores ~0.
    far = np.full((1, 2), 1000.0)
    assert isl.fitness(far, centres, heights, sigma=1.0)[0] < 1e-6


# ---------------------------------------------------------------------------
# peak occupancy: structural multimodality metric
# ---------------------------------------------------------------------------
def test_peaks_occupied_requires_resident_subpopulation():
    centres = np.array([[0.0, 0.0], [10.0, 10.0]])
    # 3 individuals clustered on peak 0, 1 lone individual near peak 1.
    pop = np.array([[0.1, 0.0], [0.0, 0.1], [-0.1, 0.0], [10.0, 10.0]])
    # occ_min=3 -> only peak 0 has a resident sub-pop; the lone individual on peak 1 doesn't count.
    assert isl.peaks_occupied(pop, centres, radius=1.0, occ_min=3) == 1
    # occ_min=1 -> both peaks counted.
    assert isl.peaks_occupied(pop, centres, radius=1.0, occ_min=1) == 2


def test_peaks_occupied_respects_radius():
    centres = np.array([[0.0, 0.0]])
    pop = np.array([[0.5, 0.0], [0.0, 0.5], [0.4, 0.3]])
    assert isl.peaks_occupied(pop, centres, radius=1.0, occ_min=3) == 1
    # shrink radius below the residents' distance -> peak no longer occupied.
    assert isl.peaks_occupied(pop, centres, radius=0.1, occ_min=3) == 0


def test_genome_spread_zero_when_identical_high_when_spread():
    same = np.zeros((10, 3))
    assert isl.genome_spread(same) == 0.0
    spread = np.array([[0.0, 0.0], [10.0, 10.0], [-10.0, -10.0], [5.0, -5.0]])
    assert isl.genome_spread(spread) > 5.0


# ---------------------------------------------------------------------------
# k-means deme splitting
# ---------------------------------------------------------------------------
def test_kmeans_separates_two_clusters():
    rng = np.random.default_rng(0)
    a = rng.normal([0, 0], 0.2, (30, 2))
    b = rng.normal([10, 10], 0.2, (30, 2))
    pts = np.vstack([a, b])
    labels, centroids = isl.kmeans(pts, 2, iters=20, rng=np.random.default_rng(1))
    assert centroids.shape[0] <= 2
    # the two well-separated blobs end up under different labels.
    assert len(np.unique(labels[:30])) == 1
    assert len(np.unique(labels[30:])) == 1
    assert labels[0] != labels[-1]


def test_kmeans_k_capped_to_population():
    pts = np.array([[0.0, 0.0], [1.0, 1.0]])
    labels, centroids = isl.kmeans(pts, 10, iters=5, rng=np.random.default_rng(0))
    assert centroids.shape[0] <= 2  # cannot have more clusters than points


# ---------------------------------------------------------------------------
# island merge: converged centroids fuse, island count shrinks
# ---------------------------------------------------------------------------
def test_merge_close_centroids_fuses_near_pairs():
    # 3 centroids: 0 and 1 are within eps, 2 is far -> {0,1} merge, 2 stays.
    centroids = np.array([[0.0, 0.0], [0.2, 0.0], [10.0, 10.0]])
    labels = np.array([0, 0, 1, 1, 2, 2])
    merged = isl.merge_close_centroids(centroids, labels, eps=0.5)
    # islands 0 and 1 collapse to one id; island 2 keeps a distinct id.
    assert len(np.unique(merged)) == 2
    # the members of original islands 0 and 1 now share a label.
    assert merged[0] == merged[2]
    assert merged[0] != merged[4]


def test_merge_close_centroids_noop_when_all_far():
    centroids = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]])
    labels = np.array([0, 1, 2])
    merged = isl.merge_close_centroids(centroids, labels, eps=0.5)
    assert len(np.unique(merged)) == 3  # nothing within eps -> no merge


def test_merge_single_island_is_identity():
    centroids = np.array([[1.0, 1.0]])
    labels = np.array([0, 0, 0])
    np.testing.assert_array_equal(isl.merge_close_centroids(centroids, labels, eps=5.0), labels)


# ---------------------------------------------------------------------------
# migration: islands arm performs migration events when migrate_frac > 0
# ---------------------------------------------------------------------------
def test_migration_occurs_when_rate_positive():
    out = isl.run(gens=64, seed=0, migrate_frac=0.01)
    assert out["islands"]["migrate_events"] > 0


def test_migration_disabled_at_zero_rate():
    out = isl.run(gens=64, seed=0, migrate_frac=0.0)
    # migrate_frac=0 genuinely disables migration (no forced floor of 1 migrant).
    assert out["islands"]["migrate_events"] == 0


def test_island_count_shrinks_via_merge():
    out = isl.run(gens=200, seed=0)
    counts = out["islands"]["island_count"]
    # dynamic count: starts at k_max and merges reduce it over the run.
    assert counts[0] >= counts[-1]
    assert out["islands"]["merge_total"] >= 1


# ---------------------------------------------------------------------------
# panmictic arm prematurely converges to a single peak
# ---------------------------------------------------------------------------
def test_panmictic_converges_to_single_peak_and_collapses_diversity():
    out = isl.run(gens=200, seed=0)
    v = out["verdict"]
    # panmictic ends occupying ~1 peak and its diversity collapses below threshold.
    assert v["panmictic_tail_peaks_occupied"] <= 1.5
    assert v["panmictic_diversity_retention"] < v["collapse_threshold"]


# ---------------------------------------------------------------------------
# composite deterministic verdict
# ---------------------------------------------------------------------------
def test_verdict_islands_preserve_multimodality_seed0():
    out = isl.run(gens=200, seed=0)
    v = out["verdict"]
    # all three composite conditions hold (AND gate).
    assert v["cond_more_peaks"] is True
    assert v["cond_more_diversity"] is True
    assert v["cond_avoids_collapse"] is True
    # islands occupy strictly more peaks and keep strictly more diversity than panmictic.
    assert v["islands_tail_peaks_occupied"] > v["panmictic_tail_peaks_occupied"]
    assert v["islands_tail_diversity"] > v["panmictic_tail_diversity"]
    # the headline deterministic verdict.
    assert v["islands_preserve_multimodality"] is True


def test_verdict_holds_across_multiple_seeds():
    for seed in (0, 1, 2, 3, 4):
        v = isl.run(gens=200, seed=seed)["verdict"]
        assert v["islands_preserve_multimodality"] is True, f"seed {seed} failed"


def test_verdict_is_deterministic_for_fixed_seed():
    a = isl.run(gens=120, seed=1)["verdict"]
    b = isl.run(gens=120, seed=1)["verdict"]
    assert a == b  # same seed -> identical verdict dict


def test_high_migration_can_break_multimodality_honest_sensitivity():
    """Honest hyperparameter sensitivity: heavy gene flow between near-equal-height peaks
    homogenizes the demes back toward panmictic behaviour. The verdict is NOT robust to an
    over-large migration rate — we assert that this regime measurably degrades the islands
    (fewer peaks and/or lower diversity than the working low-migration default)."""
    low = isl.run(gens=200, seed=0, migrate_frac=0.01)["verdict"]
    high = isl.run(gens=200, seed=0, migrate_frac=0.05)["verdict"]
    # heavy migration degrades multimodality retention relative to the low-migration run.
    assert high["islands_tail_diversity"] < low["islands_tail_diversity"]
    assert high["islands_tail_peaks_occupied"] <= low["islands_tail_peaks_occupied"]


# ---------------------------------------------------------------------------
# schema + honest disclosure
# ---------------------------------------------------------------------------
def test_output_schema_and_honest_notes_present():
    out = isl.run(gens=120, seed=0)
    assert out["schema"] == "poc_dynamic_island_speciation/v1"
    assert "proposition" in out and out["proposition"]
    notes = " ".join(out["honest_notes"])
    # honest disclosure: proxy + llive-isolation caveat must be present.
    assert "proxy" in notes.lower()
    assert "llive" in notes.lower()
    # the verdict carries the falsifiable boolean.
    assert "islands_preserve_multimodality" in out["verdict"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
