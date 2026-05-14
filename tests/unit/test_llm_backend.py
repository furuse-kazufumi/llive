"""Phase C-1: LLM backend abstraction — text-only generate API."""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest

from llive.llm import (
    GenerateRequest,
    LLMBackend,
    MockBackend,
    OllamaBackend,
    get_default_backend,
    resolve_backend,
)
from llive.llm.backend import reset_default_backend


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Clear all backend-selection env vars so resolve_backend() falls to mock
    for var in ("LLIVE_LLM_BACKEND", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    reset_default_backend()


def test_mock_backend_generate_basics() -> None:
    backend = MockBackend(prefix="[ECHO]")
    req = GenerateRequest(prompt="hello world", max_tokens=64)
    resp = backend.generate(req)
    assert resp.text.startswith("[ECHO]")
    assert "hello world" in resp.text
    assert resp.finish_reason == "stop"
    assert resp.backend == "mock"


def test_mock_backend_respects_max_tokens_truncation() -> None:
    backend = MockBackend()
    req = GenerateRequest(prompt="abcdefghij", max_tokens=3)
    resp = backend.generate(req)
    # prompt is truncated to first 3 chars before formatting
    assert "abc" in resp.text
    assert "def" not in resp.text


def test_resolve_default_when_no_env() -> None:
    backend = resolve_backend()
    assert isinstance(backend, MockBackend)
    assert backend.name == "mock"


def test_resolve_explicit_name() -> None:
    assert resolve_backend("mock").name == "mock"


def test_resolve_unknown_raises() -> None:
    with pytest.raises(ValueError):
        resolve_backend("ghost-llm")


def test_resolve_env_var_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLIVE_LLM_BACKEND", "mock")
    assert resolve_backend().name == "mock"


def test_resolve_picks_ollama_when_host_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    backend = resolve_backend()
    assert isinstance(backend, OllamaBackend)
    assert backend.host == "http://localhost:11434"


def test_resolve_priority_explicit_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # ANTHROPIC env would normally win, but explicit arg overrides
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    # Use explicit "mock" — should NOT auto-init Anthropic SDK
    assert resolve_backend("mock").name == "mock"


def test_get_default_caches() -> None:
    a = get_default_backend()
    b = get_default_backend()
    assert a is b


def test_backend_supports_flags() -> None:
    # MockBackend now claims VLM support (Phase C-1.1) so it can be used as a
    # test backend for vlm_describe_image without needing Ollama.
    assert MockBackend().supports_vlm is True
    assert MockBackend().supports_coding is False
    # Ollama claims VLM + coding support (it hosts those model families)
    ol = OllamaBackend()
    assert ol.supports_vlm is True
    assert ol.supports_coding is True


def test_ollama_generate_via_mocked_urlopen() -> None:
    """OllamaBackend builds the right HTTP payload."""
    backend = OllamaBackend(model="llama3.1", host="http://x.local:1234")

    class _Resp:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def read(self) -> bytes:
            return self._body

    captured: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: float | None = None) -> _Resp:
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Resp(json.dumps({"response": "ok!", "done": True, "eval_count": 5}).encode("utf-8"))

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        resp = backend.generate(GenerateRequest(prompt="ping", system="be terse", max_tokens=16))

    assert resp.text == "ok!"
    assert resp.backend == "ollama"
    assert resp.model == "llama3.1"
    assert captured["url"] == "http://x.local:1234/api/generate"
    assert captured["body"]["model"] == "llama3.1"
    assert captured["body"]["prompt"] == "ping"
    assert captured["body"]["system"] == "be terse"
    assert captured["body"]["options"]["num_predict"] == 16
    assert captured["body"]["stream"] is False


def test_ollama_generate_http_error_returns_error_response() -> None:
    import urllib.error

    backend = OllamaBackend(host="http://x.local:1234")
    err = urllib.error.HTTPError("http://x.local:1234", 500, "boom", {}, None)
    with mock.patch("urllib.request.urlopen", side_effect=err):
        resp = backend.generate(GenerateRequest(prompt="ping"))
    assert resp.text == ""
    assert resp.finish_reason == "error"
    assert resp.raw["http_status"] == 500


def test_subclass_can_override_generate() -> None:
    class _Stub(LLMBackend):
        name = "stub"

        def generate(self, request: GenerateRequest) -> Any:
            from llive.llm import GenerateResponse

            return GenerateResponse(text=f"stub::{request.prompt}", backend=self.name)

    resp = _Stub().generate(GenerateRequest(prompt="hi"))
    assert resp.text == "stub::hi"
    assert resp.backend == "stub"
