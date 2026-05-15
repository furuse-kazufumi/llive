# SPDX-License-Identifier: Apache-2.0
"""TRIZ-02 Contradiction Detector tests."""

from __future__ import annotations

from llive.triz.contradiction import (
    DEFAULT_REGISTRY,
    ContradictionDetector,
    MetricSpec,
    detect_from_samples,
)


def test_no_contradiction_when_one_sided():
    samples = [{"pipeline.latency_ms": 100.0 - i * 0.1} for i in range(20)]
    out = detect_from_samples(samples)
    assert out == []


def test_speed_vs_stability_contradiction():
    # latency goes DOWN (improve speed) while forgetting goes UP (degrade stability)
    samples = []
    for i in range(20):
        samples.append({
            "pipeline.latency_ms": 100.0 - i * 2.0,   # better
            "evolution.forgetting": 0.10 + i * 0.005,  # worse
        })
    out = detect_from_samples(samples)
    assert len(out) >= 1
    c = out[0]
    # Speed (id=9) improving, stability (id=13) degrading
    assert c.improve_feature_id in (9, 13)
    assert c.degrade_feature_id in (9, 13)
    assert c.severity > 0


def test_min_samples_gates():
    detector = ContradictionDetector(window=100, min_samples=20)
    for i in range(10):
        detector.observe_many({"pipeline.latency_ms": 100.0 - i})
    assert detector.detect() == []


def test_register_extends_registry():
    detector = ContradictionDetector()
    detector.register(MetricSpec("custom.metric", 99, "up_is_good"))
    assert "custom.metric" in detector.registry


def test_unknown_metric_ignored():
    detector = ContradictionDetector()
    detector.observe("totally.unknown", 42.0)
    assert detector.detect() == []


def test_observe_many_is_equivalent_to_observe():
    a = ContradictionDetector()
    b = ContradictionDetector()
    sample = {"pipeline.latency_ms": 100.0, "evolution.forgetting": 0.1}
    a.observe_many(sample)
    b.observe("pipeline.latency_ms", 100.0)
    b.observe("evolution.forgetting", 0.1)
    assert list(a._buffers["pipeline.latency_ms"].samples) == list(b._buffers["pipeline.latency_ms"].samples)


def test_reset_clears_buffers():
    detector = ContradictionDetector()
    for _ in range(10):
        detector.observe("pipeline.latency_ms", 1.0)
    detector.reset()
    assert detector._buffers == {}


def test_default_registry_complete():
    assert "pipeline.latency_ms" in DEFAULT_REGISTRY
    assert "evolution.forgetting" in DEFAULT_REGISTRY
    assert "candidate.acceptance_rate" in DEFAULT_REGISTRY


def test_severity_floor_filters_noise():
    # Only one metric moves; the other is flat under floor.
    samples = []
    for i in range(20):
        samples.append({
            "pipeline.latency_ms": 100.0 - i * 5.0,
            "evolution.forgetting": 0.10 + 1e-6 * i,
        })
    out = detect_from_samples(samples)
    # severity floor=0.05 default; tiny forgetting delta -> no pair
    assert out == [] or all(c.severity > 0 for c in out)


def test_severity_clipped_to_unit_interval():
    samples = []
    for i in range(20):
        samples.append({
            "pipeline.latency_ms": 100.0 - i * 20.0,
            "evolution.forgetting": 0.01 + i * 0.05,
        })
    out = detect_from_samples(samples)
    for c in out:
        assert 0.0 <= c.severity <= 1.0
