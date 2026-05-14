"""Scenario 4: MCP server local round-trip.

Spawns ``llive.mcp.server`` in a subprocess via the official ``mcp``
client SDK, performs ``initialize`` / ``list_tools`` / ``call_tool``,
and prints the result. Falls back to a clear message when the ``mcp``
package is not installed (the demo never crashes).
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "MCP server を subprocess で起動し、公式 client から呼びます。",
        "missing": "  ! mcp パッケージ未導入のためスキップ (pip install -e .[mcp])",
        "spawn": "subprocess で `py -m llive.mcp.server` を起動中...",
        "init": "initialize() 成功",
        "list": "list_tools() = {names}",
        "call": "call_tool('query_rad', keywords='buffer') 実行中...",
        "hit": "  - {domain}/{name}",
        "no_hit": "  (該当なし — synthetic corpus が空でも server 自体は応答)",
        "summary": "{n} tool 検出、1 ラウンドトリップ完了。Claude Desktop と同じ経路です。",
    },
    "en": {
        "intro": "Start the MCP server in a subprocess and call it with the official client.",
        "missing": "  ! mcp package not installed; skipping (pip install -e .[mcp])",
        "spawn": "Spawning `py -m llive.mcp.server`...",
        "init": "initialize() ok",
        "list": "list_tools() = {names}",
        "call": "Calling call_tool('query_rad', keywords='buffer')...",
        "hit": "  - {domain}/{name}",
        "no_hit": "  (no hits -- server still responded with valid JSON)",
        "summary": "{n} tools advertised. Same path Claude Desktop uses.",
    },
    "zh": {
        "intro": "通过 subprocess 启动 MCP server,并以官方 client 调用。",
        "missing": "  ! 未安装 mcp 包,跳过 (pip install -e .[mcp])",
        "spawn": "subprocess 启动 `py -m llive.mcp.server`...",
        "init": "initialize() 成功",
        "list": "list_tools() = {names}",
        "call": "执行 call_tool('query_rad', keywords='buffer')...",
        "hit": "  - {domain}/{name}",
        "no_hit": "  (无命中 — 但 server 仍然以合法 JSON 回应)",
        "summary": "检出 {n} 个 tool,完成一次往返。与 Claude Desktop 同路径。",
    },
    "ko": {
        "intro": "MCP server 를 subprocess 로 띄우고 공식 client 로 호출합니다.",
        "missing": "  ! mcp 패키지가 없어 건너뜁니다 (pip install -e .[mcp])",
        "spawn": "subprocess 로 `py -m llive.mcp.server` 기동 중...",
        "init": "initialize() 성공",
        "list": "list_tools() = {names}",
        "call": "call_tool('query_rad', keywords='buffer') 실행 중...",
        "hit": "  - {domain}/{name}",
        "no_hit": "  (히트 없음 — 그래도 server 는 유효 JSON 으로 응답)",
        "summary": "{n}개 tool 감지, 1 라운드 트립 완료. Claude Desktop 과 동일 경로.",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


async def _run(ctx: ScenarioContext) -> dict[str, Any]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        ctx.say(_t("missing"))
        return {"skipped": True}

    # Build an empty RAD root so the server starts cleanly
    rad_root = ctx.tmp_path / "rad"
    rad_root.mkdir()
    (rad_root / "_index.json").write_text(
        '{"schema_version":1,"source":"demo","dest":"x",'
        '"imported_at":"2026-05-15T00:00:00Z","corpora":{}}',
        encoding="utf-8",
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "llive.mcp.server"],
        env={
            "LLIVE_RAD_DIR": str(rad_root),
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "LLIVE_MCP_LOG_LEVEL": "WARNING",  # silence server-side INFO logs
        },
    )

    ctx.step(1, 3, _t("spawn"))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            ctx.say("  ✓ " + _t("init"))
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            ctx.step(2, 3, _t("list", names=",".join(names)))
            ctx.step(3, 3, _t("call"))
            response = await session.call_tool(
                "query_rad", {"keywords": "buffer", "limit": 5}
            )
            text_blocks = [c for c in response.content if getattr(c, "type", None) == "text"]
            payload = json.loads(text_blocks[0].text) if text_blocks else []
            if not payload:
                ctx.say(_t("no_hit"))
            for hit in payload[:3]:
                ctx.say(_t("hit", domain=hit["domain"], name=hit["doc_path"]))
            return {"tools": names, "hits": len(payload)}


class MCPRoundTripScenario(Scenario):
    id = "mcp-roundtrip"
    titles: ClassVar[dict[str, str]] = {
        "ja": "MCP server を実 client で呼ぶ",
        "en": "Call the MCP server with the real client",
        "zh": "用真实 client 调用 MCP server",
        "ko": "실 client 로 MCP server 호출",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, object]:
        ctx.say("  " + _t("intro"))
        result = asyncio.run(_run(ctx))
        if result.get("skipped"):
            return result
        ctx.hr()
        ctx.say("  " + _t("summary", n=len(result.get("tools", []))))
        return result
