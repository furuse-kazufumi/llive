# SPDX-License-Identifier: Apache-2.0
"""L2 Orchestration: end-to-end pipeline smoke (mock adapter)."""

from __future__ import annotations

from pathlib import Path

from llive.orchestration.pipeline import Pipeline, load_template


def test_pipeline_mock_run_writes_trace(project_root: Path):
    pipe = Pipeline(
        containers_dir=project_root / "specs/containers",
        router_spec=project_root / "specs/routes/default.yaml",
        adapter=None,
    )
    result = pipe.run("Hello world")
    assert result.container == "fast_path_v1"
    assert "mock-output" in result.text
    assert result.trace.container == "fast_path_v1"
    assert len(result.trace.subblocks) == 3


def test_pipeline_long_prompt_routes_to_adaptive(project_root: Path):
    pipe = Pipeline(
        containers_dir=project_root / "specs/containers",
        router_spec=project_root / "specs/routes/default.yaml",
        adapter=None,
    )
    long = "x" * 300
    result = pipe.run(long)
    assert result.container == "adaptive_reasoning_v1"
    assert any(t.type == "memory_read" for t in result.state.trace)
    assert any(t.type == "memory_write" for t in result.state.trace)


def test_load_template_returns_dict(project_root: Path):
    data = load_template(project_root / "specs/templates/qwen2_5_0_5b.yaml")
    assert isinstance(data, dict)
    assert "model" in data
    assert data["model"]["name"]
