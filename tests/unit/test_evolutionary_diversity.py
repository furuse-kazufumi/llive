# SPDX-License-Identifier: Apache-2.0
"""Diversity preservation (v0.E CE-24/27/28/29) — unit tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    DiversityMetrics,
    DiversityMonitor,
    DiversityPreservingBreedFilter,
    Genome,
    GenomeBounds,
    Individual,
    NoveltyScorer,
    Population,
    latin_hypercube_population,
)


# ---------------------------------------------------------------------------
# 1. LatinHypercubeInitialization
# ---------------------------------------------------------------------------


def test_lhs_returns_size_individuals() -> None:
    b = GenomeBounds(lower=(0.0, 0.0, 0.0), upper=(1.0, 1.0, 1.0))
    pop = latin_hypercube_population(b, size=10, seed=0)
    assert pop.size == 10
    for ind in pop.individuals:
        arr = ind.genome.as_array()
        assert arr.shape == (3,)
        assert (arr >= 0.0).all() and (arr <= 1.0).all()


def test_lhs_more_uniform_than_random() -> None:
    """LHS は uniform random より各 dim で空間カバレッジが高い."""
    b = GenomeBounds(lower=(0.0,) * 5, upper=(1.0,) * 5)
    n = 30
    lhs_pop = latin_hypercube_population(b, size=n, seed=0)
    rng = np.random.default_rng(0)
    rand_inds = [
        Individual.from_genome(Genome.random(b, rng)) for _ in range(n)
    ]
    rand_pop = Population(individuals=rand_inds, bounds=b, seed=0)

    def _coverage(pop: Population) -> float:
        # 各 dim を 5 bin に分割し, 各 bin に少なくとも 1 サンプルあるかを集計
        vals = np.stack([ind.genome.as_array() for ind in pop.individuals])
        bins = 5
        coverage = 0
        for d in range(vals.shape[1]):
            hist, _ = np.histogram(vals[:, d], bins=bins, range=(0.0, 1.0))
            coverage += (hist > 0).sum() / bins
        return coverage / vals.shape[1]

    lhs_cov = _coverage(lhs_pop)
    rand_cov = _coverage(rand_pop)
    # LHS は単調にカバレッジ高い (sample が多いほど差は縮むが seed 固定で
    # 安定して LHS >= rand を期待)
    assert lhs_cov >= rand_cov


def test_lhs_rejects_zero_size() -> None:
    b = GenomeBounds(lower=(0.0,), upper=(1.0,))
    with pytest.raises(ValueError, match="size"):
        latin_hypercube_population(b, size=0, seed=0)


# ---------------------------------------------------------------------------
# 2. NoveltyScorer
# ---------------------------------------------------------------------------


def test_novelty_empty_archive_returns_1() -> None:
    s = NoveltyScorer(k=3)
    assert s.novelty(np.array([0.0, 0.0])) == pytest.approx(1.0)


def test_novelty_add_archive() -> None:
    s = NoveltyScorer(k=2)
    s.add_to_archive(np.array([0.0, 0.0]))
    s.add_to_archive(np.array([1.0, 0.0]))
    # (0.5, 0.0) の novelty = mean(0.5, 0.5) = 0.5
    nov = s.novelty(np.array([0.5, 0.0]))
    assert nov == pytest.approx(0.5, abs=1e-6)


def test_novelty_archive_max_size_fifo() -> None:
    s = NoveltyScorer(k=1, archive_max_size=3)
    for i in range(5):
        s.add_to_archive(np.array([float(i), 0.0]))
    assert len(s.archive) == 3
    # 最後の 3 件 (2, 3, 4) が残る
    assert s.archive[0][0] == pytest.approx(2.0)
    assert s.archive[-1][0] == pytest.approx(4.0)


def test_novelty_rejects_invalid_k() -> None:
    with pytest.raises(ValueError, match="k"):
        NoveltyScorer(k=0)


def test_novelty_batch_returns_per_individual() -> None:
    b = GenomeBounds(lower=(0.0,), upper=(1.0,))
    inds = [
        Individual.from_genome(Genome.from_values((v,), bounds=b))
        for v in [0.1, 0.5, 0.9]
    ]
    pop = Population(individuals=inds, bounds=b, seed=0)
    s = NoveltyScorer(k=1)
    s.add_to_archive(np.array([0.0]))
    scores = s.novelty_batch(pop)
    assert scores.shape == (3,)
    assert scores[0] == pytest.approx(0.1, abs=1e-6)
    assert scores[2] == pytest.approx(0.9, abs=1e-6)


# ---------------------------------------------------------------------------
# 3. DiversityPreservingBreedFilter
# ---------------------------------------------------------------------------


def test_filter_passes_diverse_children() -> None:
    b = GenomeBounds(lower=(0.0,), upper=(1.0,))
    parents = Population(
        individuals=[
            Individual.from_genome(Genome.from_values((0.0,), bounds=b))
        ],
        bounds=b,
        seed=0,
    )
    s = NoveltyScorer(k=1)
    filt = DiversityPreservingBreedFilter(
        scorer=s, min_novelty=0.3, max_attempts=3, novelty_pool="parents"
    )
    children = [
        Individual.from_genome(Genome.from_values((0.8,), bounds=b))
    ]
    # parent (0.0) からの distance = 0.8 >= 0.3 → pass
    rng = np.random.default_rng(0)
    out = filt.filter_children(
        children, parents=parents, resample_fn=lambda: children[0], rng=rng
    )
    assert out[0].genome.values[0] == pytest.approx(0.8)


def test_filter_resamples_low_novelty() -> None:
    b = GenomeBounds(lower=(0.0,), upper=(1.0,))
    parents = Population(
        individuals=[
            Individual.from_genome(Genome.from_values((0.0,), bounds=b))
        ],
        bounds=b,
        seed=0,
    )
    s = NoveltyScorer(k=1)
    filt = DiversityPreservingBreedFilter(
        scorer=s, min_novelty=0.5, max_attempts=3, novelty_pool="parents"
    )
    # 子は parent (0.0) のすぐ近く → novelty 0.05 < threshold 0.5
    initial_child = Individual.from_genome(Genome.from_values((0.05,), bounds=b))
    # resample_fn は遠い個体を返す
    far_child = Individual.from_genome(Genome.from_values((0.95,), bounds=b))
    rng = np.random.default_rng(0)
    out = filt.filter_children(
        [initial_child],
        parents=parents,
        resample_fn=lambda: far_child,
        rng=rng,
    )
    assert out[0].genome.values[0] == pytest.approx(0.95)


def test_filter_validates_options() -> None:
    s = NoveltyScorer(k=1)
    with pytest.raises(ValueError, match="min_novelty"):
        DiversityPreservingBreedFilter(scorer=s, min_novelty=-0.1)
    with pytest.raises(ValueError, match="max_attempts"):
        DiversityPreservingBreedFilter(scorer=s, max_attempts=0)
    with pytest.raises(ValueError, match="novelty_pool"):
        DiversityPreservingBreedFilter(scorer=s, novelty_pool="bogus")


# ---------------------------------------------------------------------------
# 4. DiversityMonitor
# ---------------------------------------------------------------------------


def test_monitor_observe_records_metrics() -> None:
    b = GenomeBounds(lower=(0.0,) * 2, upper=(1.0,) * 2)
    inds = [
        Individual.from_genome(Genome.from_values((0.0, 0.0), bounds=b)),
        Individual.from_genome(Genome.from_values((1.0, 1.0), bounds=b)),
        Individual.from_genome(Genome.from_values((0.5, 0.5), bounds=b)),
    ]
    pop = Population(individuals=inds, bounds=b, seed=0)
    monitor = DiversityMonitor(min_diversity_l2=0.1, min_spread=0.1)
    m = monitor.observe(pop)
    assert m.n_individuals == 3
    assert m.spread > 1.0  # max distance = sqrt(2)
    assert m.diversity_l2 > 0.1
    assert not m.alarm
    assert len(monitor.history) == 1


def test_monitor_alarm_when_below_threshold() -> None:
    b = GenomeBounds(lower=(0.0,), upper=(1.0,))
    # 全員ほぼ同じ位置 → diversity_l2 ≈ 0
    inds = [
        Individual.from_genome(Genome.from_values((0.5,), bounds=b))
        for _ in range(5)
    ]
    pop = Population(individuals=inds, bounds=b, seed=0)
    alerts = []
    monitor = DiversityMonitor(
        min_diversity_l2=0.1,
        min_spread=0.1,
        on_alarm=alerts.append,
    )
    m = monitor.observe(pop)
    assert m.alarm  # 何か alarm
    assert len(alerts) == 1  # callback 呼ばれた


def test_monitor_handles_single_individual() -> None:
    b = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population(
        individuals=[Individual.from_genome(Genome.from_values((0.5,), bounds=b))],
        bounds=b,
        seed=0,
    )
    monitor = DiversityMonitor()
    m = monitor.observe(pop)
    assert m.n_individuals == 1
    assert m.diversity_l2 == 0.0


def test_metrics_to_dict_serializable() -> None:
    m = DiversityMetrics(
        generation=3,
        n_individuals=10,
        diversity_l2=2.0,
        spread=5.0,
        median_distance=1.5,
        bounding_volume_log=-3.0,
        alarm=["test alarm"],
    )
    d = m.to_dict()
    assert d["generation"] == 3
    assert d["alarm"] == ["test alarm"]
