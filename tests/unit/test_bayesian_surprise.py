"""MEM-07: BayesianSurpriseGate + WelfordStats."""

from __future__ import annotations

import math

import numpy as np

from llive.memory.bayesian_surprise import BayesianSurpriseGate, WelfordStats


def test_welford_empty():
    s = WelfordStats()
    assert s.n == 0
    assert s.mean == 0.0
    assert s.variance == 0.0
    assert s.stddev == 0.0


def test_welford_updates_match_numpy():
    s = WelfordStats()
    values = [0.1, 0.4, 0.2, 0.3, 0.5, 0.05, 0.45]
    for v in values:
        s.update(v)
    arr = np.array(values)
    assert math.isclose(s.mean, arr.mean(), rel_tol=1e-12)
    assert math.isclose(s.variance, arr.var(ddof=1), rel_tol=1e-9)


def test_welford_persistence_roundtrip():
    s = WelfordStats()
    for v in [0.1, 0.2, 0.3]:
        s.update(v)
    s2 = WelfordStats.from_dict(s.to_dict())
    assert s2.to_dict() == s.to_dict()


def test_cold_start_threshold_until_min_samples():
    g = BayesianSurpriseGate(k=1.0, min_samples=5, cold_start_theta=0.4)
    assert g.threshold == 0.4
    assert g.should_write(0.5)  # 0.5 >= 0.4
    # 4 updates total, still cold start
    for _ in range(3):
        g.update(0.05)
    assert g.threshold == 0.4


def test_dynamic_threshold_after_warmup():
    g = BayesianSurpriseGate(k=1.0, min_samples=3, cold_start_theta=0.0)
    for v in [0.10, 0.12, 0.11, 0.13, 0.09]:
        g.update(v)
    # now in dynamic mode; threshold = mean + k*sigma
    assert g.threshold > 0.0
    assert g.threshold < 0.20  # not absurdly high


def test_should_write_updates_stats_by_default():
    g = BayesianSurpriseGate(k=1.0, min_samples=2, cold_start_theta=0.0)
    g.should_write(0.5)
    assert g.stats.n == 1
    g.should_write(0.6, update_stats=False)
    assert g.stats.n == 1  # unchanged


def test_compute_surprise_with_existing_memory():
    g = BayesianSurpriseGate()
    new = np.array([1.0, 0.0, 0.0])
    existing = np.array([[0.0, 1.0, 0.0]])  # orthogonal
    s = g.compute_surprise(new, existing)
    assert s == 1.0  # orthogonal -> max sim 0 -> surprise 1


def test_compute_surprise_empty_memory():
    g = BayesianSurpriseGate()
    assert g.compute_surprise(np.array([1.0, 0.0]), None) == 1.0
    assert g.compute_surprise(np.array([1.0, 0.0]), np.zeros((0, 2))) == 1.0


def test_compute_surprise_near_duplicate():
    g = BayesianSurpriseGate()
    new = np.array([1.0, 0.0])
    existing = np.array([[1.0, 0.0]])
    s = g.compute_surprise(new, existing)
    assert s == 0.0


def test_to_dict_from_dict():
    g = BayesianSurpriseGate(k=0.5, min_samples=4, cold_start_theta=0.25)
    for v in [0.2, 0.3, 0.4]:
        g.update(v)
    g2 = BayesianSurpriseGate.from_dict(g.to_dict())
    assert g2.k == 0.5
    assert g2.min_samples == 4
    assert g2.cold_start_theta == 0.25
    assert g2.stats.to_dict() == g.stats.to_dict()
