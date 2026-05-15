# SPDX-License-Identifier: Apache-2.0
"""llive MCP server.

Exposes llive's RAD knowledge base and memory operations as MCP (Model Context
Protocol) tools so that Claude Desktop / LM Studio / Open WebUI / Cursor /
Continue.dev can call them as external LLM tools.

Phase C-2 (v0.2.2). Tool implementations live in :mod:`tools` and are
synchronous and testable without an MCP runtime. The :mod:`server` module
wraps them into the official ``mcp`` package's stdio server.
"""

from llive.mcp.tools import (
    tool_append_learning,
    tool_code_complete,
    tool_code_review,
    tool_get_domain_info,
    tool_list_rad_domains,
    tool_query_rad,
    tool_read_document,
    tool_vlm_describe_image,
)

__all__ = [
    "tool_append_learning",
    "tool_code_complete",
    "tool_code_review",
    "tool_get_domain_info",
    "tool_list_rad_domains",
    "tool_query_rad",
    "tool_read_document",
    "tool_vlm_describe_image",
]
