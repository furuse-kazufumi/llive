# SPDX-License-Identifier: Apache-2.0
"""Phase C-2 smoke test: spawn the MCP server in-process and exercise the protocol.

Skipped automatically when the ``mcp`` package is not installed (since the test
spawns the official MCP stdio client).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")


def _server_params(rad_root: Path) -> Any:
    from mcp import StdioServerParameters

    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "llive.mcp.server"],
        env={
            "LLIVE_RAD_DIR": str(rad_root),
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    )


async def _list_tools_via_client(rad_root: Path) -> list[str]:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(_server_params(rad_root)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return sorted(t.name for t in tools.tools)


async def _call_query_rad(rad_root: Path) -> list[dict[str, Any]]:
    import json as _json

    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(_server_params(rad_root)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.call_tool(
                "query_rad",
                {"keywords": "buffer", "limit": 5},
            )
            blocks = [c for c in response.content if getattr(c, "type", None) == "text"]
            assert blocks, "expected at least one TextContent block"
            return _json.loads(blocks[0].text)


def test_mcp_server_lists_expected_tools(tmp_path: Path) -> None:
    # Build a minimal RAD root so the server's get_default_index works
    root = tmp_path / "rad"
    root.mkdir()
    (root / "_index.json").write_text(
        '{"schema_version": 1, "source": "smoke", "dest": "x", '
        '"imported_at": "2026-05-15T00:00:00Z", "corpora": {}}',
        encoding="utf-8",
    )

    names = asyncio.run(_list_tools_via_client(root))
    assert {
        "list_rad_domains",
        "get_domain_info",
        "query_rad",
        "read_document",
        "append_learning",
    } <= set(names)


def test_mcp_server_call_tool_round_trip(tmp_path: Path) -> None:
    # Build a synthetic corpus the server can search
    root = tmp_path / "rad"
    sec = root / "security_corpus_v2"
    sec.mkdir(parents=True)
    (sec / "buffer_overflow.md").write_text(
        "Buffer overflow attacks happen when writes exceed buffer bounds.",
        encoding="utf-8",
    )
    (root / "_index.json").write_text(
        '{"schema_version": 1, "source": "smoke", "dest": "x", '
        '"imported_at": "2026-05-15T00:00:00Z", '
        '"corpora": {"security_corpus_v2": {"file_count": 1, "bytes": 64, '
        '"imported_at": "2026-05-15T00:00:00Z"}}}',
        encoding="utf-8",
    )

    result = asyncio.run(_call_query_rad(root))
    assert result, "expected at least one hit for 'buffer'"
    top = result[0]
    assert top["domain"] == "security_corpus_v2"
    assert "buffer" in top["matched_terms"]
