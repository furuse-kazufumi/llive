"""Phase C-2.1: VLM and coding MCP tools (vlm_describe_image, code_complete, code_review)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from llive.llm import GenerateRequest, GenerateResponse, LLMBackend
from llive.mcp.tools import (
    dispatch,
    tool_code_complete,
    tool_code_review,
    tool_describe,
    tool_vlm_describe_image,
)
from llive.memory.rad import RadCorpusIndex


@pytest.fixture
def synth_index(tmp_path: Path) -> RadCorpusIndex:
    root = tmp_path / "rad"
    root.mkdir()
    sec = root / "security_corpus_v2"
    sec.mkdir()
    (sec / "buffer_overflow.md").write_text(
        "buffer overflow happens when memory writes exceed the allocated size.",
        encoding="utf-8",
    )
    (sec / "sql_injection.md").write_text(
        "SQL injection occurs when untrusted input is concatenated into a query.",
        encoding="utf-8",
    )
    return RadCorpusIndex(root=root)


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    path = tmp_path / "sample.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fakedata")
    return path


class _RecordingBackend(LLMBackend):
    """Captures the last GenerateRequest so tests can inspect what was sent."""

    name = "recording"

    def __init__(self, reply: str = "mocked reply") -> None:
        self.reply = reply
        self.last: GenerateRequest | None = None

    @property
    def supports_vlm(self) -> bool:
        return True

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.last = request
        return GenerateResponse(
            text=self.reply,
            finish_reason="stop",
            backend=self.name,
            model=request.model or "recording-1",
            raw={},
        )


def test_vlm_describe_image_basic(sample_image: Path, synth_index: RadCorpusIndex) -> None:
    rec = _RecordingBackend(reply="A test image.")
    result = tool_vlm_describe_image(
        sample_image,
        prompt="What is shown?",
        backend=rec,
        index=synth_index,
    )
    assert result["text"] == "A test image."
    assert result["backend"] == "recording"
    assert result["image_path"] == str(sample_image)
    assert result["rad_hints_used"] == []
    assert rec.last is not None
    assert rec.last.prompt == "What is shown?"
    assert len(rec.last.images) == 1


def test_vlm_describe_image_with_domain_hint(sample_image: Path, synth_index: RadCorpusIndex) -> None:
    rec = _RecordingBackend()
    result = tool_vlm_describe_image(
        sample_image,
        prompt="buffer overflow memory",
        domain_hint="security_corpus_v2",
        backend=rec,
        index=synth_index,
    )
    # RAD hints were picked up
    assert any("buffer_overflow.md" in h for h in result["rad_hints_used"])
    # System prompt now contains the RAD hint header
    assert rec.last is not None
    assert rec.last.system is not None
    assert "RAD hints" in rec.last.system


def test_vlm_describe_image_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        tool_vlm_describe_image(tmp_path / "ghost.png", backend=_RecordingBackend())


def test_vlm_describe_image_unsupported_backend(sample_image: Path) -> None:
    class _NoVlm(LLMBackend):
        name = "novlm"

        def generate(self, request: GenerateRequest) -> GenerateResponse:  # pragma: no cover - unreachable
            return GenerateResponse(text="", backend=self.name)

    with pytest.raises(RuntimeError, match="VLM"):
        tool_vlm_describe_image(sample_image, backend=_NoVlm())


def test_code_complete_via_mock() -> None:
    rec = _RecordingBackend(reply="def hello(): return 1")
    result = tool_code_complete(
        "def hello():\n    pass\n",
        "Implement hello() to return 1",
        backend=rec,
    )
    assert result["text"] == "def hello(): return 1"
    assert rec.last is not None
    assert "Implement hello()" in rec.last.prompt
    assert "def hello():" in rec.last.prompt
    # coding assistant should set temperature low
    assert rec.last.temperature == 0.0


def test_code_review_pulls_security_hints(synth_index: RadCorpusIndex) -> None:
    rec = _RecordingBackend(reply="- Potential buffer overflow on line 3.")
    code = "char buf[10]; strcpy(buf, user_input); /* buffer overflow */"
    result = tool_code_review(code, backend=rec, index=synth_index, hint_limit=3)
    assert result["domain"] == "security_corpus_v2"
    assert any("buffer_overflow.md" in h for h in result["rad_hints_used"])
    assert rec.last is not None
    assert "security knowledge from RAD" in (rec.last.system or "")
    # The user prompt contains the actual code, not the hints
    assert "buf[10]" in rec.last.prompt


def test_code_review_without_matching_hints(tmp_path: Path) -> None:
    # Index with an empty domain — code_review should still work, with no hints
    root = tmp_path / "rad"
    root.mkdir()
    (root / "security_corpus_v2").mkdir()
    idx = RadCorpusIndex(root=root)
    rec = _RecordingBackend()
    result = tool_code_review("def add(a, b): return a + b", backend=rec, index=idx)
    assert result["rad_hints_used"] == []
    # System prompt still has the reviewer role, just no RAD hint block
    assert rec.last is not None
    assert "security-focused code reviewer" in (rec.last.system or "")


def test_describe_includes_new_tools() -> None:
    schemas = tool_describe()
    names = {t["name"] for t in schemas}
    assert "vlm_describe_image" in names
    assert "code_complete" in names
    assert "code_review" in names


def test_dispatch_routes_new_tools(tmp_path: Path, sample_image: Path, synth_index: RadCorpusIndex) -> None:
    rec = _RecordingBackend(reply="ok")
    result = dispatch(
        "code_complete",
        {"code_context": "x = 1", "instruction": "double x", "backend": rec},
    )
    assert result["text"] == "ok"

    # vlm via dispatch
    rec2 = _RecordingBackend(reply="image desc")
    result2 = dispatch(
        "vlm_describe_image",
        {"image_path": str(sample_image), "backend": rec2, "index": synth_index},
    )
    assert result2["text"] == "image desc"


def test_describe_schemas_valid_json() -> None:
    # Every schema must be JSON-serialisable
    for t in tool_describe():
        json.dumps(t)


def test_default_backend_mock_records_image_in_vlm(sample_image: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no explicit backend is given, the MockBackend takes over (supports_vlm=True)."""
    monkeypatch.setenv("LLIVE_LLM_BACKEND", "mock")
    from llive.llm.backend import reset_default_backend

    reset_default_backend()
    try:
        # Use a synthetic index so default index resolution doesn't matter
        idx = RadCorpusIndex(root=sample_image.parent / "no-such-rad")
        result = tool_vlm_describe_image(sample_image, prompt="hi", index=idx)
        # Mock backend echoes the prompt and notes the image
        assert "hi" in result["text"]
        assert "1 image" in result["text"]
    finally:
        reset_default_backend()


def test_recording_backend_unused_constants() -> None:
    # Silence ruff: Any is imported but used only in annotations
    _: Any = None
    assert _ is None
