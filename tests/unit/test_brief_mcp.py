# SPDX-License-Identifier: Apache-2.0
"""Tests for the ``submit_brief`` MCP tool (LLIVE-002 Step 7)."""

from __future__ import annotations

from pathlib import Path

from llive.mcp.tools import dispatch, tool_describe, tool_submit_brief


def test_submit_brief_basic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLIVE_BRIEF_LEDGER_DIR", str(tmp_path / "ledgers"))
    out = tool_submit_brief(
        goal="An MCP-submitted brief asking for novel exploration",
        brief_id="mcp-test-1",
        approval_required=False,
    )
    assert out["brief"]["brief_id"] == "mcp-test-1"
    assert out["brief"]["source"] == "mcp"
    assert out["result"]["brief_id"] == "mcp-test-1"
    assert out["result"]["status"] in {"completed", "silent", "awaiting_approval"}
    assert out["result"]["ledger_entries"] >= 1


def test_submit_brief_autogenerates_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLIVE_BRIEF_LEDGER_DIR", str(tmp_path / "ledgers"))
    out = tool_submit_brief(goal="auto-id brief", approval_required=False)
    assert out["brief"]["brief_id"].startswith("mcp-")
    assert out["result"]["status"] in {"completed", "silent", "awaiting_approval"}


def test_submit_brief_dispatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLIVE_BRIEF_LEDGER_DIR", str(tmp_path / "ledgers"))
    out = dispatch(
        "submit_brief",
        {
            "goal": "dispatched brief",
            "brief_id": "via-dispatch",
            "approval_required": False,
            "constraints": ["no destructive ops"],
        },
    )
    assert out["brief"]["constraints"] == ["no destructive ops"]
    assert out["result"]["brief_id"] == "via-dispatch"


def test_submit_brief_listed_in_describe() -> None:
    schemas = {t["name"]: t for t in tool_describe()}
    assert "submit_brief" in schemas
    schema = schemas["submit_brief"]
    assert "goal" in schema["input_schema"]["required"]
    props = schema["input_schema"]["properties"]
    assert props["priority"]["minimum"] == 0.0
    assert props["priority"]["maximum"] == 1.0
