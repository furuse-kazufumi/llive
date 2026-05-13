"""Shared pytest fixtures for the llive test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(monkeypatch, tmp_path: Path):
    """Redirect all on-disk side effects to a per-test tmp dir."""
    monkeypatch.setenv("LLIVE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLIVE_EMBED_FALLBACK", "1")
    monkeypatch.setenv("LLIVE_LOG_LEVEL", "WARNING")
    # reset process-shared memory backends between tests
    from llive.container.subblocks import builtin

    builtin.set_memory_backends(None)
    yield


@pytest.fixture
def project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "specs" / "schemas").is_dir():
            return parent
    raise RuntimeError("could not locate project root")
