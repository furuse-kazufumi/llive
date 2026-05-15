# SPDX-License-Identifier: Apache-2.0
"""llive.output — production-side output buses.

`SandboxOutputBus` (`llive.fullsense.sandbox`) は副作用ゼロの観測専用。
`ProductionOutputBus` はファイル / MCP push / llove bridge / HTTP 等の
**実際の副作用**を、ApprovalBus を gate に通して emit する。
"""

from llive.output.production import (
    EmitResult,
    LlovePushFn,
    McpPushFn,
    ProductionOutputBus,
    ProductionRecord,
)

__all__ = [
    "EmitResult",
    "LlovePushFn",
    "McpPushFn",
    "ProductionOutputBus",
    "ProductionRecord",
]
