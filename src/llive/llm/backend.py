# SPDX-License-Identifier: Apache-2.0
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

# Phase C-1.3: multimodal extension — audio + sensor input types (skeleton).
# audio: 同じく bytes / Path / base64-str. 実 encoding (wav / mp3 / ogg) は
# backend ごとに対応, supports_audio で能力を表明.
AudioInput = bytes | Path | str
# sensor: 時系列 numeric / categorical 観測. 1 sample = {"ts": float ISO 8601 or
# epoch, "metric": str, "value": float | str | list, "unit": str | None}.
# llmesh の MQTT / OPC-UA bridge と同じ envelope を想定.
SensorSample = dict[str, Any]
# Phase C-1.4 (Gemini #2 Stage 1, 2026-05-22): KV cache Memory Translator.
# Embedding 結合経路 — テキストトークン化せず memory entry の embedding を
# 直接 LLM の inputs_embeds に注入. **ローカル LLM を内包する FullSense
# だからこそできる hack**. Open LLM (Ollama / llama.cpp / HF Transformers)
# 経路限定 — Closed LLM (Anthropic / OpenAI) はこの API を公開していない.
# 1 prefix = (label: str, vector: ndarray-like 1D of float). label は
# observability 用 (実 LLM には流さない). vector は backend の hidden_dim と
# 一致が必要 (mismatch は generate() 内で reject).
PrefixEmbedding = tuple[str, Any]  # (label, ndarray | list[float])

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
    # Phase C-1.3 (multimodal extension, 2026-05-22 skeleton):
    # audio inputs (bytes/Path/base64) for speech / sound backends.
    audio: list[AudioInput] = field(default_factory=list)
    # sensor sample list (numeric / categorical time-series). 1 sample is a
    # dict with at minimum ``ts`` / ``metric`` / ``value`` keys. llmesh の
    # MQTT/OPC-UA envelope と互換.
    sensor: list[SensorSample] = field(default_factory=list)
    # Phase C-1.4 (Gemini #2 Stage 1, 2026-05-22): KV cache Memory Translator
    # Embedding 結合経路. Open LLM backend が inputs_embeds に注入する用途.
    # backend が supports_prefix_embeddings = False なら無視 (ignore) or reject
    # (実装次第). MockBackend は accept + count を返す.
    prefix_embeddings: list[PrefixEmbedding] = field(default_factory=list)


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

    @property
    def supports_audio(self) -> bool:
        """Whether this backend can accept audio inputs (Phase C-1.3, skeleton).

        実装は backend ごと. Whisper / Gemini Audio / GPT-4o audio 等.
        default False — 各 backend が必要時に override.
        """
        return False

    @property
    def supports_sensor(self) -> bool:
        """Whether this backend can accept structured sensor samples (Phase C-1.3).

        典型的には専用 backend (llmesh MTEngine 直結, time-series LLM 等).
        汎用 backend は通常 False, sensor は事前に prompt に序列化して渡す.
        """
        return False

    @property
    def supports_prefix_embeddings(self) -> bool:
        """Whether this backend can accept prefix embeddings (Phase C-1.4).

        Open LLM (Ollama / llama.cpp / HF Transformers) のうち inputs_embeds を
        受け付ける backend で True. Closed LLM (Anthropic / OpenAI) は API が
        公開されていないため False が default. これは [[project_idea_kv_cache_memory_translator]]
        Stage 1: Embedding 結合経路.
        """
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

    @property
    def supports_audio(self) -> bool:
        # mock は audio も accept する (count を返すだけ, transcription なし).
        return True

    @property
    def supports_sensor(self) -> bool:
        # mock は sensor も accept する (sample 数を返すだけ).
        return True

    @property
    def supports_prefix_embeddings(self) -> bool:
        # mock は prefix embeddings も accept する (count と label 一覧を返す).
        return True

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        text = f"{self.prefix} {request.prompt[: max(0, request.max_tokens)]}".strip()
        normed = [_normalise_image(im) for im in request.images]
        if normed:
            text = f"{text} (with {len(normed)} image{'s' if len(normed) != 1 else ''})"
        if request.audio:
            text = f"{text} (with {len(request.audio)} audio clip{'s' if len(request.audio) != 1 else ''})"
        if request.sensor:
            text = f"{text} (with {len(request.sensor)} sensor sample{'s' if len(request.sensor) != 1 else ''})"
        raw: dict[str, Any] = {"echo": True}
        if normed:
            raw["images"] = [
                {"media_type": m, "base64_len": len(b64)} for m, b64 in normed
            ]
        if request.audio:
            raw["audio_count"] = len(request.audio)
        if request.sensor:
            raw["sensor_count"] = len(request.sensor)
            raw["sensor_metrics"] = sorted(
                {str(s.get("metric", "")) for s in request.sensor if s.get("metric")}
            )
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

    @property
    def supports_vlm(self) -> bool:
        return True

    def generate(self, request: GenerateRequest) -> GenerateResponse:  # pragma: no cover - requires API key
        if request.images:
            content: list[dict[str, Any]] = []
            for im in request.images:
                media, b64 = _normalise_image(im)
                content.append(
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media, "data": b64},
                    }
                )
            content.append({"type": "text", "text": request.prompt})
            messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": request.prompt}]
        kwargs: dict[str, Any] = {
            "model": request.model or self.model,
            "max_tokens": int(request.max_tokens),
            "messages": messages,
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
    Set ``OPENAI_BASE_URL`` to point at LM Studio / vLLM / llama-server / etc.
    Set ``LLIVE_OPENAI_MODEL`` to choose a default model name without code
    changes (useful when ``LLIVE_LLM_BACKEND=openai`` is set in env and the
    actual served model is not ``gpt-4o-mini``).
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
        self.model = model or os.environ.get("LLIVE_OPENAI_MODEL") or self.DEFAULT_MODEL

    @property
    def supports_vlm(self) -> bool:
        return True

    def generate(self, request: GenerateRequest) -> GenerateResponse:  # pragma: no cover - requires API key
        messages: list[dict[str, Any]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        if request.images:
            user_content: list[dict[str, Any]] = [{"type": "text", "text": request.prompt}]
            for im in request.images:
                media, b64 = _normalise_image(im)
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media};base64,{b64}"},
                    }
                )
            messages.append({"role": "user", "content": user_content})
        else:
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

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout: float = 120.0,
        *,
        num_ctx: int | None = None,
    ) -> None:
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        self.model = model or self.DEFAULT_MODEL
        self.timeout = float(timeout)
        # Override Ollama's default context window (typically 2048). Required
        # when prompts exceed ~1500 tokens — otherwise they get silently
        # truncated and benchmarks measure the wrong thing.
        self.num_ctx: int | None = num_ctx

    def generate(self, request: GenerateRequest) -> GenerateResponse:  # pragma: no cover - requires running ollama
        import urllib.error
        import urllib.request

        options: dict[str, Any] = {
            "temperature": float(request.temperature),
            "num_predict": int(request.max_tokens),
            "stop": list(request.stop or []),
        }
        if self.num_ctx is not None:
            options["num_ctx"] = int(self.num_ctx)
        body: dict[str, Any] = {
            "model": request.model or self.model,
            "prompt": request.prompt,
            "stream": False,
            "options": options,
        }
        if request.system:
            body["system"] = request.system
        if request.images:
            # Ollama expects top-level "images": [<base64>, ...]
            body["images"] = [_normalise_image(im)[1] for im in request.images]
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
# Mamba / SSM backend (Phase 5 — non-transformer track)
#
# See docs/non-transformer/ROADMAP.md and COMPARISON.md for the rationale.
# Skeleton-only: the actual SSM kernel is delegated to either:
#   (a) llama.cpp >= b8864 + llama-server (OpenAI-compatible API path —
#       in this case prefer LLIVE_LLM_BACKEND=openai with OPENAI_BASE_URL).
#   (b) mamba-ssm Python package (in-process, requires CUDA).
#
# This class exists primarily as a *naming anchor* so callers can write
# ``LLIVE_LLM_BACKEND=mamba`` declaratively and the resolver can pick the
# right transport. The HTTP path is implemented now; the in-process path
# (b) will land alongside the Phase 5 thought-factor→Δ bridge (case C in
# ROADMAP.md).
# ---------------------------------------------------------------------------


class MambaBackend(LLMBackend):
    """Mamba/SSM LLM backend — Phase 5 skeleton (case A from ROADMAP).

    Transports (selected by ``transport`` arg or ``LLIVE_MAMBA_TRANSPORT`` env):

    * ``"llama_cpp_server"`` (default) — point ``base_url`` at a running
      ``llama-server`` instance serving a Mamba GGUF (e.g. Codestral-Mamba 7B).
      Internally delegates to :class:`OpenAIBackend` so existing transport
      code is reused; the only difference is the *name* (so audit logs +
      analytics can distinguish a Mamba-backed run from a Transformer-backed
      OpenAI-compatible run).
    * ``"mamba_ssm"`` (planned, Phase 5) — in-process via mamba-ssm. Raises
      ``NotImplementedError`` for now; the structure is documented so a
      future PR can fill it in without changing the public surface.
    """

    name = "mamba"
    DEFAULT_MODEL = "codestral-mamba"  # GGUF tag used by llama.cpp builds
    DEFAULT_TRANSPORT = "llama_cpp_server"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        *,
        transport: str | None = None,
    ) -> None:
        self.transport = (
            transport
            or os.environ.get("LLIVE_MAMBA_TRANSPORT")
            or self.DEFAULT_TRANSPORT
        ).lower()
        self.model = model or os.environ.get("LLIVE_MAMBA_MODEL") or self.DEFAULT_MODEL

        if self.transport == "llama_cpp_server":
            # Delegate to OpenAIBackend — llama-server speaks OpenAI-compatible
            # HTTP, and Mamba GGUFs work via the same /v1/chat/completions
            # path. Surface the inner backend so tests can mock through it.
            self._inner: LLMBackend | None = OpenAIBackend(
                model=self.model,
                base_url=base_url,
            )
        elif self.transport == "mamba_ssm":
            # In-process Mamba via mamba-ssm — Phase 5 (thought-factor→Δ
            # bridge implementation). Deferred to keep the dependency optional.
            self._inner = None
        else:
            raise ValueError(
                f"unknown MambaBackend transport: {self.transport!r}; "
                "use 'llama_cpp_server' or 'mamba_ssm'"
            )

    @property
    def supports_vlm(self) -> bool:
        # Pure Mamba LLMs today are text-only; VLM Mamba variants (Sigma etc.)
        # will be exposed through dedicated subclasses in Phase 5.1.
        return False

    @property
    def supports_coding(self) -> bool:
        # Codestral-Mamba ships as a coding-specialised model — default True.
        return True

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        if self.transport == "mamba_ssm" or self._inner is None:
            raise NotImplementedError(
                "MambaBackend transport='mamba_ssm' is not implemented yet. "
                "It lands with the Phase 5 thought-factor→Δ bridge "
                "(see docs/non-transformer/ROADMAP.md case C). For now, "
                "use transport='llama_cpp_server' (default) and a running "
                "llama-server serving a Mamba GGUF model."
            )
        return _delegate_generate(self._inner, request, self.model, self.name)


# ---------------------------------------------------------------------------
# Helper: shared logic for "wrapper" backends that delegate to OpenAIBackend
# ---------------------------------------------------------------------------


def _delegate_generate(
    inner: LLMBackend,
    request: GenerateRequest,
    fallback_model: str,
    wrapper_name: str,
) -> GenerateResponse:
    """Send ``request`` via ``inner`` while preserving the wrapper's identity.

    Used by MambaBackend / RwkvBackend / JambaBackend / DiffusionBackend so
    their analytics tag isn't lost when the actual transport is OpenAI-
    compatible HTTP. Forces the model name onto the request to override the
    inner backend's own default.
    """
    coerced = GenerateRequest(
        prompt=request.prompt,
        system=request.system,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        stop=list(request.stop),
        model=request.model or fallback_model,
        images=list(request.images),
    )
    resp = inner.generate(coerced)
    return GenerateResponse(
        text=resp.text,
        finish_reason=resp.finish_reason,
        backend=wrapper_name,
        model=resp.model,
        raw=dict(resp.raw, inner_backend=resp.backend),
    )


# ---------------------------------------------------------------------------
# RWKV-7 backend (non-transformer case E in ROADMAP.md — CPU-first)
# ---------------------------------------------------------------------------


class RwkvBackend(LLMBackend):
    """RWKV-7 backend — CPU-optimised non-transformer LLM (case E).

    Transports:
    * ``"rwkv_cpp_server"`` (default) — RWKV.cpp built with OpenAI-compatible
      HTTP wrapper. Delegates to :class:`OpenAIBackend` so any
      ``rwkv-cli`` / ``RWKV-Runner`` / custom server with /v1 endpoint works.
    * ``"rwkv_py"`` (planned) — in-process via ``rwkv`` PyPI package. Streaming
      friendly (each step is O(state_dim), not O(L)). Land alongside the
      llove TUI 5-pane wiring.
    """

    name = "rwkv"
    DEFAULT_MODEL = "rwkv-7-world-7b"
    DEFAULT_TRANSPORT = "rwkv_cpp_server"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        *,
        transport: str | None = None,
    ) -> None:
        self.transport = (
            transport
            or os.environ.get("LLIVE_RWKV_TRANSPORT")
            or self.DEFAULT_TRANSPORT
        ).lower()
        self.model = model or os.environ.get("LLIVE_RWKV_MODEL") or self.DEFAULT_MODEL
        if self.transport == "rwkv_cpp_server":
            self._inner: LLMBackend | None = OpenAIBackend(
                model=self.model, base_url=base_url
            )
        elif self.transport == "rwkv_py":
            self._inner = None
        else:
            raise ValueError(
                f"unknown RwkvBackend transport: {self.transport!r}; "
                "use 'rwkv_cpp_server' or 'rwkv_py'"
            )

    @property
    def supports_vlm(self) -> bool:
        return False

    @property
    def supports_coding(self) -> bool:
        return True  # RWKV-7 coding variants exist

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        if self._inner is None:
            raise NotImplementedError(
                "RwkvBackend transport='rwkv_py' is not implemented yet. "
                "Use transport='rwkv_cpp_server' with a running RWKV.cpp HTTP server."
            )
        return _delegate_generate(self._inner, request, self.model, self.name)


# ---------------------------------------------------------------------------
# Jamba backend (non-transformer case B in ROADMAP.md — Mamba/Attention hybrid)
# ---------------------------------------------------------------------------


class JambaBackend(LLMBackend):
    """AI21 Jamba hybrid backend (case B).

    The hybrid is opaque to the caller — internally Jamba interleaves Mamba
    blocks with Attention. We expose it as a single backend with the same
    OpenAI-compatible transport so it slots into the existing run lifecycle.
    Stage-wise routing (see :class:`StageBackendRouter`) is what actually
    surfaces the hybrid character to the llive 6-stage loop.
    """

    name = "jamba"
    DEFAULT_MODEL = "jamba-1.5-mini"
    DEFAULT_TRANSPORT = "llama_cpp_server"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        *,
        transport: str | None = None,
    ) -> None:
        self.transport = (
            transport
            or os.environ.get("LLIVE_JAMBA_TRANSPORT")
            or self.DEFAULT_TRANSPORT
        ).lower()
        self.model = model or os.environ.get("LLIVE_JAMBA_MODEL") or self.DEFAULT_MODEL
        if self.transport == "llama_cpp_server":
            self._inner: LLMBackend | None = OpenAIBackend(
                model=self.model, base_url=base_url
            )
        else:
            raise ValueError(
                f"unknown JambaBackend transport: {self.transport!r}"
            )

    @property
    def supports_vlm(self) -> bool:
        return False  # Jamba-1.5 mini/large are text-only

    @property
    def supports_coding(self) -> bool:
        return True

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        assert self._inner is not None
        return _delegate_generate(self._inner, request, self.model, self.name)


# ---------------------------------------------------------------------------
# Diffusion LM backend (non-transformer case D in ROADMAP.md — experimental)
# ---------------------------------------------------------------------------


class DiffusionBackend(LLMBackend):
    """Diffusion LM backend (case D, experimental).

    Targets Mercury / ELYZA-LLM-Diffusion / Dream-family servers that expose
    an OpenAI-compatible /v1 endpoint. Native sampling parameters (num_steps,
    schedule, refinement_rounds) are passed through via ``request.raw`` /
    extra HTTP params once the upstream API stabilises; for now we keep the
    surface minimal and degrade to a normal chat completion call.
    """

    name = "diffusion"
    DEFAULT_MODEL = "elyza-llm-diffusion"
    DEFAULT_TRANSPORT = "openai_compatible"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        *,
        transport: str | None = None,
    ) -> None:
        self.transport = (
            transport
            or os.environ.get("LLIVE_DIFFUSION_TRANSPORT")
            or self.DEFAULT_TRANSPORT
        ).lower()
        self.model = (
            model or os.environ.get("LLIVE_DIFFUSION_MODEL") or self.DEFAULT_MODEL
        )
        if self.transport == "openai_compatible":
            self._inner: LLMBackend | None = OpenAIBackend(
                model=self.model, base_url=base_url
            )
        else:
            raise ValueError(
                f"unknown DiffusionBackend transport: {self.transport!r}"
            )

    @property
    def supports_vlm(self) -> bool:
        return False

    @property
    def supports_coding(self) -> bool:
        return False  # text-first for now

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        assert self._inner is not None
        return _delegate_generate(self._inner, request, self.model, self.name)


# ---------------------------------------------------------------------------
# Default backend resolution
# ---------------------------------------------------------------------------


def resolve_backend(name: str | None = None) -> LLMBackend:
    """Return a backend by explicit name, env var, or auto-detected fallback.

    Order:
        1. ``name`` arg (one of: mock / anthropic / openai / ollama / mamba).
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
    if candidate == "mamba":
        return MambaBackend()
    if candidate == "rwkv":
        return RwkvBackend()
    if candidate == "jamba":
        return JambaBackend()
    if candidate == "diffusion":
        return DiffusionBackend()
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
