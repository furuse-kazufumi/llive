# SPDX-License-Identifier: Apache-2.0
"""Tests for ``llive brief`` CLI subcommands (LLIVE-002 Step 6)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from llive.cli.main import app

runner = CliRunner()


_MINIMAL_BRIEF_YAML = """\
brief_id: cli-smoke
goal: A short novel exploration to flex the loop.
priority: 0.7
approval_required: false
"""


def _write_brief(tmp_path: Path, contents: str = _MINIMAL_BRIEF_YAML) -> Path:
    p = tmp_path / "brief.yaml"
    p.write_text(contents, encoding="utf-8")
    return p


def test_brief_submit_from_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLIVE_BRIEF_LEDGER_DIR", str(tmp_path / "ledgers"))
    brief_path = _write_brief(tmp_path)

    result = runner.invoke(app, ["brief", "submit", str(brief_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["brief"]["brief_id"] == "cli-smoke"
    assert payload["result"]["status"] in {"completed", "silent", "awaiting_approval"}


def test_brief_submit_inline_goal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLIVE_BRIEF_LEDGER_DIR", str(tmp_path / "ledgers"))

    result = runner.invoke(
        app,
        [
            "brief",
            "submit",
            "--goal",
            "An inline brief",
            "--brief-id",
            "inline-1",
            "--no-approval",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["brief"]["brief_id"] == "inline-1"


def test_brief_submit_requires_input() -> None:
    result = runner.invoke(app, ["brief", "submit"])
    assert result.exit_code != 0


def test_brief_submit_inline_requires_brief_id() -> None:
    result = runner.invoke(app, ["brief", "submit", "--goal", "x"])
    assert result.exit_code != 0


def test_brief_ledger_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLIVE_BRIEF_LEDGER_DIR", str(tmp_path / "ledgers"))
    brief_path = _write_brief(tmp_path)
    runner.invoke(app, ["brief", "submit", str(brief_path), "--json"])

    result = runner.invoke(app, ["brief", "ledger", "cli-smoke", "--json"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output.strip())
    events = [r["event"] for r in rows]
    assert "brief_submitted" in events
    assert events[-1] == "outcome"


def test_brief_ledger_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLIVE_BRIEF_LEDGER_DIR", str(tmp_path / "missing"))
    result = runner.invoke(app, ["brief", "ledger", "never-existed"])
    assert result.exit_code != 0
