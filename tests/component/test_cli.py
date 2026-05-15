# SPDX-License-Identifier: Apache-2.0
"""CLI smoke tests via typer.testing.CliRunner."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from llive.cli.main import app

runner = CliRunner()


def test_cli_help_shows_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = result.stdout
    for sub in ("run", "bench", "memory", "schema", "route", "triz"):
        assert sub in out


def test_cli_triz_stats():
    result = runner.invoke(app, ["triz", "stats"])
    assert result.exit_code == 0
    assert "principles" in result.stdout
    assert "40" in result.stdout


def test_cli_schema_list():
    result = runner.invoke(app, ["schema", "list"])
    assert result.exit_code == 0
    assert "container-spec.v1" in result.stdout


def test_cli_route_dry_run():
    result = runner.invoke(app, ["route", "dry-run", "--prompt", "hello"])
    assert result.exit_code == 0
    assert "fast_path_v1" in result.stdout


def test_cli_run_mock(project_root: Path):
    template = project_root / "specs/templates/qwen2_5_0_5b.yaml"
    result = runner.invoke(
        app, ["run", "--template", str(template), "--prompt", "hi", "--mock"]
    )
    assert result.exit_code == 0
    assert "fast_path_v1" in result.stdout
    assert "mock-output" in result.stdout


def test_cli_schema_validate_container(project_root: Path):
    target = project_root / "specs/containers/fast_path_v1.yaml"
    result = runner.invoke(app, ["schema", "validate", str(target), "--kind", "container"])
    assert result.exit_code == 0
    assert "OK" in result.stdout


def test_cli_schema_validate_candidate(project_root: Path):
    target = project_root / "specs/candidates/example_001.yaml"
    result = runner.invoke(app, ["schema", "validate", str(target), "--kind", "candidate"])
    assert result.exit_code == 0
    assert "OK" in result.stdout
