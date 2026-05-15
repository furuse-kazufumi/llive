# SPDX-License-Identifier: Apache-2.0
"""BC-01/02 component tests: ContainerSpec → executor with built-in sub-blocks."""

from __future__ import annotations

from pathlib import Path

from llive.container import BlockContainerExecutor, BlockState


def test_fast_path_executes_three_subblocks(project_root: Path):
    exe = BlockContainerExecutor(project_root / "specs/containers/fast_path_v1.yaml")
    assert exe.container_id == "fast_path_v1"
    assert exe.subblock_types == ["pre_norm", "causal_attention", "ffn_swiglu"]
    state = exe.execute(BlockState(prompt="Hello"))
    assert [t.type for t in state.trace] == exe.subblock_types
    assert all(t.note == "" for t in state.trace)


def test_adaptive_reasoning_reads_and_writes_memory(project_root: Path):
    exe = BlockContainerExecutor(project_root / "specs/containers/adaptive_reasoning_v1.yaml")
    types = [
        "pre_norm",
        "causal_attention",
        "memory_read",
        "ffn_swiglu",
        "memory_write",
    ]
    assert exe.subblock_types == types
    state = exe.execute(BlockState(prompt="What is RL?", output="RL is reinforcement learning."))
    assert state.surprise is not None and state.surprise > 0.0
    ops = [a.get("op") for a in state.memory_accesses]
    assert "read" in ops
    assert "write" in ops


def test_unknown_subblock_type_raises(project_root: Path, tmp_path):
    bogus = tmp_path / "bogus.yaml"
    bogus.write_text(
        """\
schema_version: 1
container_id: bogus_v1
subblocks:
  - type: nonexistent_kind
""",
        encoding="utf-8",
    )
    import pytest

    with pytest.raises(KeyError):
        BlockContainerExecutor(bogus)
