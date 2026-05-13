"""CONC-02 / CONC-03: ConcurrentPipeline + BranchExplorer."""

from __future__ import annotations

import pytest

from llive.orchestration.concurrent import (
    BranchExplorer,
    ConcurrentPipeline,
)
from llive.orchestration.pipeline import Pipeline


@pytest.fixture
def pipeline():
    return Pipeline(adapter=None, write_trace_to_disk=False)


def test_concurrent_pipeline_run_parallel(pipeline):
    with ConcurrentPipeline(pipeline, max_workers=2) as cp:
        results = cp.run_parallel(["hello", "world", "foo", "bar"])
    assert len(results) == 4
    # all four should produce mock outputs and a valid container
    for r in results:
        assert r.container
        assert "mock-output" in r.text


def test_concurrent_pipeline_submit(pipeline):
    with ConcurrentPipeline(pipeline, max_workers=2) as cp:
        fut = cp.submit("hi")
        result = fut.result(timeout=5)
    assert result.text


def test_concurrent_pipeline_rejects_after_close(pipeline):
    cp = ConcurrentPipeline(pipeline, max_workers=1)
    cp.close()
    with pytest.raises(RuntimeError):
        cp.submit("x")
    with pytest.raises(RuntimeError):
        cp.run_parallel(["x"])


def test_branch_explorer_runs_all_containers(pipeline):
    with BranchExplorer(pipeline, ["fast_path_v1", "adaptive_reasoning_v1"], max_workers=2) as be:
        branches = be.explore("what is consolidation?")
    cids = [b.container_id for b in branches]
    assert cids == ["fast_path_v1", "adaptive_reasoning_v1"]
    for b in branches:
        assert b.latency_ms >= 0.0
        assert b.result.container == b.container_id


def test_branch_explorer_empty_rejected(pipeline):
    with pytest.raises(ValueError):
        BranchExplorer(pipeline, [], max_workers=2)


def test_branch_explorer_close_rejects(pipeline):
    be = BranchExplorer(pipeline, ["fast_path_v1"], max_workers=1)
    be.close()
    with pytest.raises(RuntimeError):
        be.explore("x")


def test_concurrent_pipeline_preserves_order(pipeline):
    """Even with workers > 1, results must come back in the input order."""
    prompts = [f"prompt-{i}" for i in range(8)]
    with ConcurrentPipeline(pipeline, max_workers=4) as cp:
        results = cp.run_parallel(prompts)
    for i, r in enumerate(results):
        assert f"prompt-{i}" in r.text


def test_concurrent_pipeline_double_close_is_idempotent(pipeline):
    cp = ConcurrentPipeline(pipeline, max_workers=1)
    cp.close()
    cp.close()  # should not raise


def test_branch_explorer_context_manager(pipeline):
    with BranchExplorer(pipeline, ["fast_path_v1"]) as be:
        out = be.explore("hi")
    assert out[0].container_id == "fast_path_v1"


def test_pipeline_run_with_container_bypasses_router(pipeline):
    result = pipeline.run_with_container("a short prompt", "adaptive_reasoning_v1")
    # router would have picked fast_path_v1 for a short prompt, but we forced adaptive
    assert result.container == "adaptive_reasoning_v1"
    assert result.extras.get("router_bypass") is True
