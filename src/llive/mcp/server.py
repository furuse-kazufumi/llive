# SPDX-License-Identifier: Apache-2.0
"""MCP (Model Context Protocol) server entry point for llive.

This module wires the synchronous tool functions in :mod:`tools` into the
asynchronous MCP runtime. Run with::

    py -3.11 -m llive.mcp.server

The official ``mcp`` Python SDK is imported lazily so the rest of the llive
package can be installed without the MCP dependency. When ``mcp`` is missing
this module prints an actionable hint and exits.

Configure your MCP host (Claude Desktop, LM Studio, Open WebUI, Cursor,
Continue.dev) with::

    {
      "mcpServers": {
        "llive": {
          "command": "py",
          "args": ["-3.11", "-m", "llive.mcp.server"],
          "env": {
            "LLIVE_RAD_DIR": "D:/projects/llive/data/rad"
          }
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from llive.mcp.tools import dispatch, tool_describe

log = logging.getLogger("llive.mcp")


def _import_mcp() -> tuple[Any, Any, Any]:
    """Lazy import the MCP SDK. Returns (Server, stdio_server, types module).

    Raises:
        SystemExit: with an actionable hint if the SDK is not installed.
    """
    try:
        from mcp import types  # type: ignore[import-not-found]
        from mcp.server import Server  # type: ignore[import-not-found]
        from mcp.server.stdio import stdio_server  # type: ignore[import-not-found]
    except ImportError as exc:
        sys.stderr.write(
            "ERROR: the 'mcp' package is not installed.\n"
            "       Install with:  py -3.11 -m pip install 'mcp>=1.0'\n"
            f"       (cause: {exc})\n"
        )
        raise SystemExit(2) from exc
    return Server, stdio_server, types


def _to_text_content(types_mod: Any, result: Any) -> list[Any]:
    """Wrap a JSON-serialisable tool result into MCP TextContent."""
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    return [types_mod.TextContent(type="text", text=text)]


async def _amain() -> None:
    Server, stdio_server, types_mod = _import_mcp()
    server = Server("llive")
    descriptions = tool_describe()

    @server.list_tools()  # type: ignore[misc]
    async def _list_tools() -> list[Any]:
        return [
            types_mod.Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["input_schema"],
            )
            for t in descriptions
        ]

    @server.call_tool()  # type: ignore[misc]
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        log.info("call_tool: %s %s", name, list((arguments or {}).keys()))
        try:
            result = dispatch(name, arguments or {})
        except KeyError as exc:
            return _to_text_content(types_mod, {"error": str(exc), "kind": "unknown_tool"})
        except Exception as exc:
            log.exception("tool error")
            return _to_text_content(
                types_mod,
                {"error": str(exc), "kind": exc.__class__.__name__},
            )
        return _to_text_content(types_mod, result)

    async with stdio_server() as (read_stream, write_stream):
        init = server.create_initialization_options()
        await server.run(read_stream, write_stream, init)


def main() -> int:
    import os

    level_name = (os.environ.get("LLIVE_MCP_LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # MCP SDK's lowlevel server logs every request at INFO; silence those too
    # when the user explicitly asked for a quieter run.
    if level > logging.INFO:
        logging.getLogger("mcp").setLevel(level)
    import asyncio

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
