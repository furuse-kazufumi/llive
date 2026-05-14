"""Phase C-2 smoke test: spawn the MCP server in-process and exercise the protocol.

Skipped automatically when the ``mcp`` package is not installed (since the test
spawns the official MCP stdio client).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")


@pytest.mark.asyncio
async def _list_tools_via_client(rad_root: Path) -> list[str]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "llive.mcp.server"],
        env={
            "LLIVE_RAD_DIR": str(rad_root),
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return sorted(t.name for t in tools.tools)


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
