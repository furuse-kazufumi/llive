# SPDX-License-Identifier: Apache-2.0
"""Phase C-1.1: VLM (multimodal) extensions to the LLM backend abstraction."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from llive.llm import GenerateRequest, MockBackend, OllamaBackend
from llive.llm.backend import _normalise_image, reset_default_backend


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("LLIVE_LLM_BACKEND", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    reset_default_backend()


def test_normalise_image_from_path(tmp_path: Path) -> None:
    png = tmp_path / "image.png"
    payload = b"\x89PNG\r\n\x1a\n" + b"fake"
    png.write_bytes(payload)
    media, b64 = _normalise_image(png)
    assert media == "image/png"
    assert base64.b64decode(b64) == payload


def test_normalise_image_from_path_jpeg(tmp_path: Path) -> None:
    jpg = tmp_path / "photo.jpg"
    jpg.write_bytes(b"\xff\xd8\xff\xe0fake")
    media, b64 = _normalise_image(jpg)
    assert media == "image/jpeg"
    assert b64


def test_normalise_image_from_bytes_jpeg_detected() -> None:
    media, b64 = _normalise_image(b"\xff\xd8\xff\xe0fake")
    assert media == "image/jpeg"
    assert b64


def test_normalise_image_from_str_assumed_b64() -> None:
    media, b64 = _normalise_image("AAAA")
    assert media == "image/png"
    assert b64 == "AAAA"


def test_mock_backend_records_image_count() -> None:
    backend = MockBackend()
    req = GenerateRequest(
        prompt="describe",
        images=[b"\x89PNG\r\n\x1a\nfake", b"\xff\xd8\xff\xe0fake2"],
    )
    resp = backend.generate(req)
    assert "with 2 images" in resp.text
    assert resp.raw["images"][0]["media_type"] == "image/png"
    assert resp.raw["images"][1]["media_type"] == "image/jpeg"


def test_mock_backend_no_images_unchanged() -> None:
    backend = MockBackend()
    resp = backend.generate(GenerateRequest(prompt="ping", images=[]))
    assert "image" not in resp.text
    assert "images" not in resp.raw


def test_mock_backend_supports_vlm_flag() -> None:
    assert MockBackend().supports_vlm is True


def test_ollama_generate_sends_images_top_level() -> None:
    backend = OllamaBackend(model="llava", host="http://x.local:1234")

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
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Resp(json.dumps({"response": "a cat", "done": True}).encode("utf-8"))

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        resp = backend.generate(
            GenerateRequest(
                prompt="what is in this image?",
                images=[b"\x89PNG\r\n\x1a\nfake"],
            )
        )

    assert resp.text == "a cat"
    # Ollama expects top-level "images": [base64, ...]
    assert "images" in captured["body"]
    assert len(captured["body"]["images"]) == 1
    decoded = base64.b64decode(captured["body"]["images"][0])
    assert decoded.startswith(b"\x89PNG")


def test_ollama_no_images_unchanged() -> None:
    backend = OllamaBackend(host="http://x.local:1234")

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
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _Resp(json.dumps({"response": "ok", "done": True}).encode("utf-8"))

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        backend.generate(GenerateRequest(prompt="ping"))

    assert "images" not in captured["body"]
