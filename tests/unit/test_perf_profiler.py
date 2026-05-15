"""APO Profiler の単体テスト."""

from __future__ import annotations

from llive.perf.profiler import Profiler, diagnose_latency


def test_record_and_snapshot_yields_stats() -> None:
    p = Profiler(window=100)
    for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
        p.record("latency_ms", v)
    snap = p.snapshot()
    s = snap["latency_ms"]
    assert s["count"] == 5
    assert s["mean"] == 3.0
    assert s["p50"] == 3.0
    assert s["max"] == 5.0


def test_window_caps_samples() -> None:
    p = Profiler(window=3)
    for v in range(10):
        p.record("x", float(v))
    snap = p.snapshot()
    assert snap["x"]["count"] == 3
    assert snap["x"]["max"] == 9.0


def test_incr_and_counter() -> None:
    p = Profiler()
    p.incr("triz.hits")
    p.incr("triz.hits", by=3)
    snap = p.snapshot()
    assert snap["triz.hits"]["count"] == 4


def test_gauge() -> None:
    p = Profiler()
    p.set_gauge("phase", 2.0)
    snap = p.snapshot()
    assert snap["phase"]["value"] == 2.0


def test_reset() -> None:
    p = Profiler()
    p.record("x", 1.0)
    p.incr("y")
    p.set_gauge("z", 3.0)
    p.reset()
    assert p.snapshot() == {}


def test_diagnose_latency_healthy() -> None:
    p = Profiler()
    for v in [10.0, 20.0, 30.0]:
        p.record("loop.tick.ms", v)
    d = diagnose_latency(p, budget_ms=200.0)
    assert d["healthy"] is True
    assert d["verdict"] == "ok"


def test_diagnose_latency_breach() -> None:
    p = Profiler()
    for v in [400.0, 500.0, 600.0]:
        p.record("loop.tick.ms", v)
    d = diagnose_latency(p, budget_ms=200.0)
    assert d["healthy"] is False
    assert d["verdict"] == "exceeds_human_speech_budget"


def test_diagnose_latency_no_data() -> None:
    p = Profiler()
    d = diagnose_latency(p)
    assert d["verdict"] == "no_data"
