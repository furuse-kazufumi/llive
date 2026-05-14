"""Scenario 5: OpenAI-compatible HTTP server with x_rad_domain.

Boots the OpenAI HTTP server on an ephemeral port, sends two requests:

1. Plain chat (no RAD)
2. Same prompt + ``x_rad_domain="security_corpus_v2"`` -> RAG-on-by-flag

Prints both responses side-by-side so the hint injection effect is
visible. Uses the MockBackend so no API keys are required.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any, ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext
from llive.llm.backend import reset_default_backend
from llive.mcp.tools import reset_default_index
from llive.server.openai_api import LLIVE_MODEL_ID, OpenAIAPIHandler

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "HTTP server を ephemeral port で起動し、RAD on/off の差分を出します。",
        "boot": "サーバ起動: http://127.0.0.1:{port}/v1",
        "seed": "ミニ security_corpus を準備...",
        "plain": "POST (RAD オフ):",
        "with_rad": "POST (RAD オン: x_rad_domain=security_corpus_v2):",
        "reply_head": "  応答 text 抜粋:",
        "hints": "  注入されたヒント: {n} 件 / {paths}",
        "summary": "RAD オンにすると同じプロンプトに {n} 件のヒントが system に追加されました。",
    },
    "en": {
        "intro": "Boot the HTTP server on an ephemeral port and contrast RAD on/off.",
        "boot": "Server listening at http://127.0.0.1:{port}/v1",
        "seed": "Seeding a tiny security_corpus...",
        "plain": "POST (RAD off):",
        "with_rad": "POST (RAD on: x_rad_domain=security_corpus_v2):",
        "reply_head": "  Reply excerpt:",
        "hints": "  Hints injected: {n} via {paths}",
        "summary": "Switching RAD on appended {n} system hints for the same prompt.",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as fh:
            return json.loads(fh.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8")
        return {"error": body_text, "status": exc.code}


class OpenAIHTTPScenario(Scenario):
    id = "openai-http"
    titles: ClassVar[dict[str, str]] = {
        "ja": "OpenAI 互換 HTTP server で RAG-on-by-flag",
        "en": "OpenAI-compat HTTP server with RAG-on-by-flag",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, object]:
        ctx.say("  " + _t("intro"))
        # Force the mock backend + an isolated RAD root so the demo is
        # hermetic regardless of the user's env.
        prior_env = {k: os.environ.get(k) for k in ("LLIVE_LLM_BACKEND", "LLIVE_RAD_DIR")}
        os.environ["LLIVE_LLM_BACKEND"] = "mock"
        rad_root = ctx.tmp_path / "rad"
        sec = rad_root / "security_corpus_v2"
        sec.mkdir(parents=True)
        (sec / "buffer_overflow.md").write_text(
            "Buffer overflow attacks happen when writes exceed buffer bounds. "
            "Use strncpy / snprintf to bound copies.",
            encoding="utf-8",
        )
        os.environ["LLIVE_RAD_DIR"] = str(rad_root)
        reset_default_backend()
        reset_default_index()

        port = _free_port()
        server = ThreadingHTTPServer(("127.0.0.1", port), OpenAIAPIHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            ctx.say("  " + _t("boot", port=port))
            ctx.say("  " + _t("seed"))
            prompt = "Explain buffer overflow in C in two sentences."

            ctx.step(1, 2, _t("plain"))
            resp_plain = _post(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                {
                    "model": LLIVE_MODEL_ID,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 60,
                },
            )
            text = (resp_plain.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
            ctx.say(_t("reply_head"))
            for line in str(text).splitlines()[:3]:
                ctx.say(f"    {line}")
            ctx.say(_t("hints", n=len(resp_plain.get("x_llive_rad_hints", []) or []), paths="-"))

            ctx.step(2, 2, _t("with_rad"))
            resp_rag = _post(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                {
                    "model": LLIVE_MODEL_ID,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 60,
                    "x_rad_domain": "security_corpus_v2",
                    "x_rad_hint_limit": 3,
                },
            )
            text2 = (resp_rag.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
            ctx.say(_t("reply_head"))
            for line in str(text2).splitlines()[:3]:
                ctx.say(f"    {line}")
            hints = resp_rag.get("x_llive_rad_hints", []) or []
            ctx.say(_t(
                "hints",
                n=len(hints),
                paths=", ".join(h.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for h in hints) or "-",
            ))

            ctx.hr()
            ctx.say("  " + _t("summary", n=len(hints)))
            return {
                "hints_off": len(resp_plain.get("x_llive_rad_hints", []) or []),
                "hints_on": len(hints),
            }
        finally:
            server.shutdown()
            server.server_close()
            for k, v in prior_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            reset_default_backend()
            reset_default_index()
