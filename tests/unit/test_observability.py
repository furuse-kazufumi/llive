"""OBS-01/02: trace + metrics."""

from __future__ import annotations

import json
import math
from pathlib import Path

from llive.observability.metrics import MetricsStore, compute_route_entropy
from llive.observability.trace import (
    MemoryAccessTrace,
    RouteTrace,
    SubblockTrace,
    write_trace,
)


def test_compute_route_entropy_uniform():
    e = compute_route_entropy({"a": 2, "b": 2})
    assert math.isclose(e, 1.0, rel_tol=1e-6)


def test_compute_route_entropy_singleton():
    e = compute_route_entropy({"a": 5})
    assert e == 0.0


def test_compute_route_entropy_empty():
    assert compute_route_entropy({}) == 0.0


def test_metrics_store_roundtrip(tmp_path: Path):
    store = MetricsStore(db_path=tmp_path / "m.duckdb")
    try:
        store.record("run-1", "latency_ms", 1.5)
        store.record_many("run-1", {"entropy": 1.0, "reads": 3.0})
        rows = store.query("run-1")
        keys = {r["key"] for r in rows}
        assert keys == {"latency_ms", "entropy", "reads"}
    finally:
        store.close()


def test_route_trace_jsonl_append(tmp_path: Path):
    target = tmp_path / "trace.jsonl"
    t = RouteTrace(
        container="fast_path_v1",
        subblocks=[SubblockTrace(name="pre_norm", type="pre_norm", duration_ms=1.0)],
        memory_accesses=[MemoryAccessTrace(op="read", layer="semantic", hits=[])],
        metrics={"latency_ms": 2.5},
    )
    write_trace(t, target)
    write_trace(t, target)
    lines = [ln for ln in target.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    obj = json.loads(lines[0])
    assert obj["container"] == "fast_path_v1"
    assert obj["subblocks"][0]["type"] == "pre_norm"
