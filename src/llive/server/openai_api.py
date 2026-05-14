"""OpenAI-compatible HTTP API for llive (Phase C-3).

Exposes a tiny ``/v1/chat/completions`` endpoint that:

1. Accepts standard OpenAI chat messages.
2. Optionally augments the last user message with RAD hints
   (``query_rad`` top-N excerpts as a ``system`` block).
3. Forwards to the configured llive LLM backend
   (Mock / Anthropic / OpenAI / Ollama).
4. Returns an OpenAI-shaped response so the call is a drop-in.

Auxiliary endpoints:

* ``GET /v1/models`` — advertises the synthetic ``llive-rad`` model id
  plus the active backend's default model.
* ``GET /v1/tools`` — non-standard helper: returns the MCP tool schema list
  so callers can discover RAD operations.
* ``GET /health`` — liveness probe.

Why does this matter? Ollama and many Ollama-front-end UIs only speak the
OpenAI HTTP protocol; they do not consume MCP servers directly. This
endpoint lets them tap llive's knowledge base by pointing their
``base_url`` at ``http://localhost:8765/v1`` (or wherever you run it).

Run with::

    py -3.11 -m llive.server.openai_api --host 127.0.0.1 --port 8765

"""

from __future__ import annotations

import argparse
import json
import logging
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from llive.llm import GenerateRequest, get_default_backend
from llive.mcp.tools import tool_describe, tool_query_rad
from llive.memory.rad import RadCorpusIndex

log = logging.getLogger("llive.server.openai_api")

LLIVE_MODEL_ID = "llive-rad"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 8 * 1024 * 1024  # 8 MiB; defensive for typical chat payloads


def _now() -> int:
    return int(time.time())


def _augment_with_rad(
    messages: list[dict[str, Any]],
    domain: str | list[str] | None,
    hint_limit: int,
    index: RadCorpusIndex | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """If ``domain`` is given, prepend a RAD hint system message before the user turn.

    Returns ``(augmented_messages, hint_paths)``.
    """
    if not domain or hint_limit <= 0:
        return messages, []
    # Find the latest user message
    user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                user_text = content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        user_text = part.get("text", "")
                        break
            break
    if not user_text.strip():
        return messages, []
    hits = tool_query_rad(
        user_text,
        domain=domain,
        limit=int(hint_limit),
        index=index,
    )
    if not hits:
        return messages, []
    hint_lines = ["# Relevant knowledge from llive RAD"]
    used: list[str] = []
    for h in hits:
        used.append(h["doc_path"])
        if h["excerpt"]:
            hint_lines.append(f"- {h['excerpt']}")
    augmented = [{"role": "system", "content": "\n".join(hint_lines)}, *messages]
    return augmented, used


def _messages_to_generate_request(
    messages: list[dict[str, Any]],
    model: str | None,
    max_tokens: int,
    temperature: float,
    stop: list[str] | None,
) -> GenerateRequest:
    """Flatten OpenAI-style messages into llive's ``GenerateRequest``.

    System messages are merged. The latest user message becomes the prompt.
    Assistant turns are appended above the user prompt as plain text so the
    backend has the conversational context even if it's a one-shot ``generate``
    API.
    """
    system_parts: list[str] = []
    convo: list[str] = []
    last_user_idx = -1
    for i, msg in enumerate(messages):
        if msg.get("role") == "user":
            last_user_idx = i
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Flatten OpenAI multipart content
            text = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        else:
            text = str(content)
        if role == "system":
            system_parts.append(text)
        elif i == last_user_idx and role == "user":
            convo.append(text)
        else:
            convo.append(f"{role}: {text}")
    prompt = "\n\n".join(convo).strip() or messages[-1].get("content", "") if messages else ""
    return GenerateRequest(
        prompt=prompt if isinstance(prompt, str) else str(prompt),
        system="\n\n".join(system_parts) if system_parts else None,
        max_tokens=int(max_tokens),
        temperature=float(temperature),
        stop=list(stop or []),
        model=model,
    )


class OpenAIAPIHandler(BaseHTTPRequestHandler):
    """Minimal OpenAI-compatible request handler."""

    server_version = "llive-openai/0.1"

    # ---- helpers --------------------------------------------------------

    def _write_json(self, status: int, payload: Any) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError(f"invalid Content-Length: {length}")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        log.info("%s - %s", self.client_address[0], format % args)

    # ---- routes ---------------------------------------------------------

    def do_GET(self) -> None:
        if self.path == "/health":
            self._write_json(200, {"status": "ok", "server": self.server_version})
            return
        if self.path.startswith("/v1/models"):
            self._handle_models()
            return
        if self.path.startswith("/v1/tools"):
            self._write_json(200, {"tools": tool_describe()})
            return
        self._write_json(404, {"error": {"message": f"unknown path: {self.path}"}})

    def do_POST(self) -> None:
        if self.path.startswith("/v1/chat/completions"):
            self._handle_chat_completions()
            return
        self._write_json(404, {"error": {"message": f"unknown path: {self.path}"}})

    # ---- handlers -------------------------------------------------------

    def _handle_models(self) -> None:
        try:
            backend = get_default_backend()
        except Exception as exc:
            self._write_json(500, {"error": {"message": f"backend init failed: {exc}"}})
            return
        backend_default = getattr(backend, "model", None) or getattr(
            backend.__class__, "DEFAULT_MODEL", "default"
        )
        models = [
            {
                "id": LLIVE_MODEL_ID,
                "object": "model",
                "created": _now(),
                "owned_by": "llive",
                "backend": backend.name,
                "backend_default_model": backend_default,
            },
            {
                "id": f"{LLIVE_MODEL_ID}/{backend_default}",
                "object": "model",
                "created": _now(),
                "owned_by": "llive",
                "backend": backend.name,
            },
        ]
        self._write_json(200, {"object": "list", "data": models})

    def _handle_chat_completions(self) -> None:
        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self._write_json(400, {"error": {"message": f"bad request body: {exc}"}})
            return

        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            self._write_json(400, {"error": {"message": "missing 'messages' array"}})
            return

        # llive extensions (non-standard but recognised):
        #   x_rad_domain: str | list[str]  — auto-augment with RAD hints
        #   x_rad_hint_limit: int          — top-N RAD excerpts (default 3)
        rad_domain = body.get("x_rad_domain")
        rad_hint_limit = int(body.get("x_rad_hint_limit", 3))

        try:
            augmented, hints_used = _augment_with_rad(messages, rad_domain, rad_hint_limit, index=None)
        except Exception as exc:
            log.warning("RAD augmentation failed: %s", exc)
            augmented, hints_used = messages, []

        # Strip the llive-rad/<backend-model> prefix so we forward the real model id
        model_in = body.get("model", "") or ""
        forwarded_model: str | None = None
        if model_in.startswith(f"{LLIVE_MODEL_ID}/"):
            forwarded_model = model_in.split("/", 1)[1]
        elif model_in and model_in != LLIVE_MODEL_ID:
            forwarded_model = model_in
        # else: forwarded_model stays None → backend picks its default

        req = _messages_to_generate_request(
            augmented,
            model=forwarded_model,
            max_tokens=int(body.get("max_tokens", 1024)),
            temperature=float(body.get("temperature", 0.7)),
            stop=body.get("stop"),
        )

        try:
            backend = get_default_backend()
            resp = backend.generate(req)
        except Exception as exc:
            log.exception("backend generate failed")
            self._write_json(
                502,
                {"error": {"message": f"backend error: {exc}", "kind": exc.__class__.__name__}},
            )
            return

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        payload = {
            "id": completion_id,
            "object": "chat.completion",
            "created": _now(),
            "model": model_in or LLIVE_MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": resp.text},
                    "finish_reason": resp.finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": -1,
                "completion_tokens": -1,
                "total_tokens": -1,
            },
            # Non-standard fields exposed for debugging / introspection:
            "x_llive_backend": resp.backend,
            "x_llive_model": resp.model,
            "x_llive_rad_hints": hints_used,
        }
        self._write_json(200, payload)


def make_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """Build a ThreadingHTTPServer bound to ``(host, port)``."""
    return ThreadingHTTPServer((host, port), OpenAIAPIHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="llive OpenAI-compatible HTTP API")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    server = make_server(args.host, args.port)
    log.info("llive OpenAI API listening on http://%s:%s/v1", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
