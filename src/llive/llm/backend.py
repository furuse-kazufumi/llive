"""LLM backend adapter — text-only ``generate`` for now (Phase C-1.0).

All backends share the same ``LLMBackend.generate(request) -> GenerateResponse``
signature so that downstream code (Consolidator, MCP tools, etc.) is
backend-agnostic. Each concrete backend lazy-imports its SDK so the rest of
llive can run without optional dependencies installed.

Example:

    from llive.llm import get_default_backend, GenerateRequest

    backend = get_default_backend()  # picks mock / anthropic / openai / ollama
    response = backend.generate(
        GenerateRequest(
            prompt="Summarise: buffer overflow is...",
            max_tokens=256,
            temperature=0.2,
        )
    )
    print(response.text)
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Sentinel for unset optional fields
_UNSET = object()

# Phase C-1.1: VLM image input types
ImageInput = bytes | Path | str  # bytes payload, file path, or base64-encoded string

_EXT_TO_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def _normalise_image(img: ImageInput) -> tuple[str, str]:
    """Return (media_type, base64_str) for an image input.

    Accepts:
        * ``bytes`` — raw image bytes (media type guessed from magic bytes,
          defaults to ``image/png``).
        * ``Path`` — read from filesystem; media type from extension.
        * ``str`` — assumed to already be base64-encoded; default media type
          ``image/png``.
    """
    if isinstance(img, Path):
        data = img.read_bytes()
        media = _EXT_TO_MEDIA.get(img.suffix.lower(), "image/png")
        return media, base64.b64encode(data).decode("ascii")
    if isinstance(img, bytes):
        media = "image/png"
        if img.startswith(b"\xff\xd8\xff"):
            media = "image/jpeg"
        elif img.startswith(b"GIF8"):
            media = "image/gif"
        elif img.startswith(b"RIFF") and b"WEBP" in img[:32]:
            media = "image/webp"
        return media, base64.b64encode(img).decode("ascii")
    # str — assume already base64
    return "image/png", img


@dataclass
class GenerateRequest:
    """Unified request shape across backends."""

    prompt: str
    system: str | None = None
    max_tokens: int = 1024
    temperature: float = 0.2
    stop: list[str] = field(default_factory=list)
    # The model id is backend-specific; if omitted the backend chooses its
    # default. e.g. ``claude-haiku-4-5-20251001`` for Anthropic,
    # ``gpt-4o-mini`` for OpenAI, ``llama3.1`` for Ollama.
    model: str | None = None
    # Phase C-1.1 (VLM): list of image inputs sent alongside the prompt.
    # Each item can be ``bytes`` (raw image), ``Path`` (file to read), or
    # ``str`` (already base64-encoded payload).
    images: list[ImageInput] = field(default_factory=list)


@dataclass
class GenerateResponse:
    """Unified response shape across backends."""

    text: str
    finish_reason: str = "stop"  # "stop" | "length" | "error" | <backend-specific>
    backend: str = ""
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class LLMBackend:
    """Abstract base — subclass to add a new backend."""

    name: str = "abstract"

    def generate(self, request: GenerateRequest) -> GenerateResponse:  # pragma: no cover - interface
        raise NotImplementedError

    @property
    def supports_vlm(self) -> bool:
        """Whether this backend's models can accept image inputs (Phase C-1.1)."""
        return False

    @property
    def supports_coding(self) -> bool:
        """Whether this backend has a coding-specialised model variant (Phase C-1.2)."""
        return False


# ---------------------------------------------------------------------------
# Mock backend — deterministic, network-free, used as fallback and in tests
# ---------------------------------------------------------------------------


class MockBackend(LLMBackend):
    """Echoes the prompt with a deterministic prefix. No network.

    Multimodal: when ``request.images`` is non-empty, the count is appended to
    the echoed text and the normalised payloads are recorded in ``raw``.
    """

    name = "mock"

    def __init__(self, prefix: str = "[mock]") -> None:
        self.prefix = prefix

    @property
    def supports_vlm(self) -> bool:
        return True

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        text = f"{self.prefix} {request.prompt[: max(0, request.max_tokens)]}".strip()
        normed = [_normalise_image(im) for im in request.images]
        if normed:
            text = f"{text} (with {len(normed)} image{'s' if len(normed) != 1 else ''})"
        raw: dict[str, Any] = {"echo": True}
        if normed:
            raw["images"] = [
                {"media_type": m, "base64_len": len(b64)} for m, b64 in normed
            ]
        return GenerateResponse(
            text=text,
            finish_reason="stop",
            backend=self.name,
            model=request.model or "mock-1",
            raw=raw,
        )


# ---------------------------------------------------------------------------
# Anthropic backend (Claude)
# ---------------------------------------------------------------------------


class AnthropicBackend(LLMBackend):
    """Calls Claude via the official ``anthropic`` SDK.

    Requires ``[llm]`` extra: ``pip install llmesh-llive[llm]``.
    """

    name = "anthropic"
    DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, model: str | None = None) -> None:
        try:
            import anthropic  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:  # pragma: no cover - exercised when SDK missing
            raise ModuleNotFoundError(
                "AnthropicBackend requires the [llm] extra: pip install 'llmesh-llive[llm]'"
            ) from exc
        self._client = anthropic.Anthropic()
        self.model = model or self.DEFAULT_MODEL

    def generate(self, request: GenerateRequest) -> GenerateResponse:  # pragma: no cover - requires API key
        kwargs: dict[str, Any] = {
            "model": request.model or self.model,
            "max_tokens": int(request.max_tokens),
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": float(request.temperature),
        }
        if request.system:
            kwargs["system"] = request.system
        if request.stop:
            kwargs["stop_sequences"] = list(request.stop)
        resp = self._client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        return GenerateResponse(
            text=text,
            finish_reason=getattr(resp, "stop_reason", "stop") or "stop",
            backend=self.name,
            model=kwargs["model"],
            raw={"id": getattr(resp, "id", "")},
        )


# ---------------------------------------------------------------------------
# OpenAI backend
# ---------------------------------------------------------------------------


class OpenAIBackend(LLMBackend):
    """Calls OpenAI (or any OpenAI-compatible HTTP API) via the ``openai`` SDK.

    Requires ``[openai]`` extra: ``pip install openai>=1.0``.
    Set ``OPENAI_BASE_URL`` to point at LM Studio / vLLM / etc.
    """

    name = "openai"
    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        try:
            import openai  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise ModuleNotFoundError(
                "OpenAIBackend requires:  pip install openai>=1.0"
            ) from exc
        kwargs: dict[str, Any] = {}
        if base_url or os.environ.get("OPENAI_BASE_URL"):
            kwargs["base_url"] = base_url or os.environ["OPENAI_BASE_URL"]
        self._client = openai.OpenAI(**kwargs)
        self.model = model or self.DEFAULT_MODEL

    def generate(self, request: GenerateRequest) -> GenerateResponse:  # pragma: no cover - requires API key
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        resp = self._client.chat.completions.create(
            model=request.model or self.model,
            messages=messages,
            max_tokens=int(request.max_tokens),
            temperature=float(request.temperature),
            stop=request.stop or None,
        )
        choice = resp.choices[0]
        return GenerateResponse(
            text=choice.message.content or "",
            finish_reason=getattr(choice, "finish_reason", "stop") or "stop",
            backend=self.name,
            model=request.model or self.model,
            raw={"id": getattr(resp, "id", "")},
        )


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------


class OllamaBackend(LLMBackend):
    """Calls a local Ollama server via its HTTP API. No SDK required (stdlib only).

    The server URL is taken from ``$OLLAMA_HOST`` (default
    ``http://localhost:11434``).
    """

    name = "ollama"
    DEFAULT_MODEL = "llama3.1"

    def __init__(self, model: str | None = None, host: str | None = None, timeout: float = 120.0) -> None:
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        self.model = model or self.DEFAULT_MODEL
        self.timeout = float(timeout)

    def generate(self, request: GenerateRequest) -> GenerateResponse:  # pragma: no cover - requires running ollama
        import urllib.error
        import urllib.request

        body = {
            "model": request.model or self.model,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                "temperature": float(request.temperature),
                "num_predict": int(request.max_tokens),
                "stop": list(request.stop or []),
            },
        }
        if request.system:
            body["system"] = request.system
        data = json.dumps(body).encode("utf-8")
        url = f"{self.host}/api/generate"
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as fh:
                payload = json.loads(fh.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return GenerateResponse(
                text="",
                finish_reason="error",
                backend=self.name,
                model=body["model"],
                raw={"http_status": exc.code, "error": str(exc)},
            )
        return GenerateResponse(
            text=str(payload.get("response", "")),
            finish_reason="stop" if payload.get("done") else "length",
            backend=self.name,
            model=body["model"],
            raw={"eval_count": payload.get("eval_count")},
        )

    @property
    def supports_vlm(self) -> bool:
        # Ollama hosts VLM models like llava / qwen2.5-vl; the generate path accepts
        # ``images`` (Phase C-1.1 — not yet wired here).
        return True

    @property
    def supports_coding(self) -> bool:
        # qwen2.5-coder / deepseek-coder / codellama are popular Ollama models.
        return True


# ---------------------------------------------------------------------------
# Default backend resolution
# ---------------------------------------------------------------------------


def resolve_backend(name: str | None = None) -> LLMBackend:
    """Return a backend by explicit name, env var, or auto-detected fallback.

    Order:
        1. ``name`` arg (one of: mock / anthropic / openai / ollama).
        2. ``$LLIVE_LLM_BACKEND`` env var.
        3. ``$ANTHROPIC_API_KEY`` set → anthropic.
        4. ``$OPENAI_API_KEY`` set → openai.
        5. ``$OLLAMA_HOST`` set → ollama.
        6. Fallback: mock.

    Raises:
        ValueError: if an unknown name is given.
    """
    candidate = (name or os.environ.get("LLIVE_LLM_BACKEND") or "").lower().strip()
    if not candidate:
        if os.environ.get("ANTHROPIC_API_KEY"):
            candidate = "anthropic"
        elif os.environ.get("OPENAI_API_KEY"):
            candidate = "openai"
        elif os.environ.get("OLLAMA_HOST"):
            candidate = "ollama"
        else:
            candidate = "mock"

    if candidate == "mock":
        return MockBackend()
    if candidate == "anthropic":
        return AnthropicBackend()
    if candidate == "openai":
        return OpenAIBackend()
    if candidate == "ollama":
        return OllamaBackend()
    raise ValueError(f"unknown LLM backend: {candidate!r}")


_DEFAULT: LLMBackend | None = None


def get_default_backend() -> LLMBackend:
    """Lazy-init shared default backend."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = resolve_backend()
    return _DEFAULT


def reset_default_backend() -> None:
    """Drop the cached default backend — for tests."""
    global _DEFAULT
    _DEFAULT = None


# Silence ruff: _UNSET is intentionally kept for forward use
_ = _UNSET
