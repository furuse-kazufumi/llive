"""Phase C-3: OpenAI-compatible HTTP API server.

Spins up the server in a background thread on an ephemeral port and exercises
each endpoint with stdlib ``urllib.request``. Uses the Mock LLM backend so
no network access is required.
"""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from llive.llm.backend import reset_default_backend
from llive.server.openai_api import LLIVE_MODEL_ID, OpenAIAPIHandler


@pytest.fixture(autouse=True)
def _force_mock_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLIVE_LLM_BACKEND", "mock")
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    reset_default_backend()


@pytest.fixture(autouse=True)
def _isolate_rad_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Point RAD index at a synthetic root with one corpus
    root = tmp_path / "rad"
    sec = root / "security_corpus_v2"
    sec.mkdir(parents=True)
    (sec / "buffer_overflow.md").write_text(
        "Buffer overflow attacks happen when writes exceed buffer bounds.",
        encoding="utf-8",
    )
    monkeypatch.setenv("LLIVE_RAD_DIR", str(root))
    # Drop the MCP tools cached index so it re-resolves
    from llive.mcp.tools import reset_default_index

    reset_default_index()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server() -> Iterator[str]:
    port = _free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), OpenAIAPIHandler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base
    finally:
        srv.shutdown()
        srv.server_close()


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as fh:
        return json.loads(fh.read().decode("utf-8"))


def _post_json(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as fh:
            return fh.status, json.loads(fh.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body) if body else {}


def test_health(server: str) -> None:
    out = _get_json(f"{server}/health")
    assert out["status"] == "ok"
    assert "llive-openai" in out["server"]


def test_models(server: str) -> None:
    out = _get_json(f"{server}/v1/models")
    assert out["object"] == "list"
    ids = [m["id"] for m in out["data"]]
    assert LLIVE_MODEL_ID in ids
    assert any(m.get("backend") == "mock" for m in out["data"])


def test_tools(server: str) -> None:
    out = _get_json(f"{server}/v1/tools")
    assert "tools" in out
    names = {t["name"] for t in out["tools"]}
    assert {"query_rad", "vlm_describe_image", "code_review"} <= names


def test_chat_completions_basic(server: str) -> None:
    status, resp = _post_json(
        f"{server}/v1/chat/completions",
        {
            "model": LLIVE_MODEL_ID,
            "messages": [{"role": "user", "content": "hello world"}],
            "max_tokens": 64,
        },
    )
    assert status == 200
    assert resp["object"] == "chat.completion"
    assert resp["model"] == LLIVE_MODEL_ID
    assert resp["choices"][0]["message"]["role"] == "assistant"
    # Mock backend echoes the prompt
    assert "hello world" in resp["choices"][0]["message"]["content"]
    assert resp["x_llive_backend"] == "mock"
    assert resp["x_llive_rad_hints"] == []


def test_chat_completions_with_rad_augmentation(server: str) -> None:
    status, resp = _post_json(
        f"{server}/v1/chat/completions",
        {
            "messages": [{"role": "user", "content": "Explain buffer overflow"}],
            "max_tokens": 200,
            "x_rad_domain": "security_corpus_v2",
            "x_rad_hint_limit": 3,
        },
    )
    assert status == 200
    hints = resp["x_llive_rad_hints"]
    assert hints, "expected at least one RAD hint to be injected"
    assert any("buffer_overflow.md" in h for h in hints)


def test_chat_completions_invalid_body(server: str) -> None:
    status, resp = _post_json(f"{server}/v1/chat/completions", {"foo": "bar"})
    assert status == 400
    assert "messages" in resp["error"]["message"]


def test_chat_completions_model_routing(server: str) -> None:
    # llive-rad/<inner> should forward the inner part to the backend
    status, resp = _post_json(
        f"{server}/v1/chat/completions",
        {
            "model": f"{LLIVE_MODEL_ID}/llama3.1",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )
    assert status == 200
    # Mock backend records the forwarded model id in resp.x_llive_model
    assert resp["x_llive_model"] == "llama3.1"


def test_unknown_route_returns_404(server: str) -> None:
    try:
        _get_json(f"{server}/v1/no_such_endpoint")
        raise AssertionError("expected 404 HTTPError")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404


def test_unknown_post_route_returns_404(server: str) -> None:
    status, resp = _post_json(f"{server}/v1/no_such_post", {})
    assert status == 404
    assert "unknown path" in resp["error"]["message"]
