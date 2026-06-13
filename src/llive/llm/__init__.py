# SPDX-License-Identifier: Apache-2.0
"""LLM backend abstraction (Phase C-1, llive v0.2 RAD epic).

Provides a thin, transport-uniform adapter over multiple LLM backends so that
the rest of llive (consolidation, MCP tool implementations, etc.) does not
care whether the model is Anthropic Claude, OpenAI, Ollama, or llama-cpp.

Phase C-1.0 (this milestone): text-only ``generate`` API across all backends.
Phase C-1.1 (next): multimodal (VLM) — image inputs for LLaVA / Qwen2.5-VL /
Phi-3.5-vision / Llama 3.2 Vision.
Phase C-1.2 (next): coding-specialised backends — Qwen2.5-Coder /
DeepSeek-Coder / Code Llama with explicit ``code_context`` support.

Default backend resolution (when no explicit choice is provided):

1. ``$LLIVE_LLM_BACKEND``: one of ``mock`` / ``anthropic`` / ``openai`` /
   ``ollama`` / ``mamba`` / ``rwkv`` / ``jamba`` / ``diffusion``.
2. ``$ANTHROPIC_API_KEY`` is set → ``anthropic``.
3. ``$OPENAI_API_KEY`` is set → ``openai``.
4. ``$OLLAMA_HOST`` is set → ``ollama``.
5. Fallback: ``mock`` (deterministic, no network).

Model-name env overrides (default-model selection without code changes):

* ``$LLIVE_OPENAI_MODEL`` — overrides ``OpenAIBackend.DEFAULT_MODEL``.
  Required when ``LLIVE_LLM_BACKEND=openai`` is used to target an
  OpenAI-compatible server (LM Studio / vLLM / llama-server) whose actual
  model name is not ``gpt-4o-mini``.
* ``$LLIVE_MAMBA_MODEL`` / ``$LLIVE_MAMBA_TRANSPORT`` — Mamba/SSM backend
  (non-transformer track, ROADMAP case A). Transport options:
  ``llama_cpp_server`` (default) / ``mamba_ssm`` (Phase 5).
* ``$LLIVE_RWKV_MODEL`` / ``$LLIVE_RWKV_TRANSPORT`` — RWKV-7 backend
  (non-transformer case E, CPU-first). Transports: ``rwkv_cpp_server`` (default)
  / ``rwkv_py``.
* ``$LLIVE_JAMBA_MODEL`` / ``$LLIVE_JAMBA_TRANSPORT`` — Jamba hybrid
  (non-transformer case B). Single transport: ``llama_cpp_server``.
* ``$LLIVE_DIFFUSION_MODEL`` / ``$LLIVE_DIFFUSION_TRANSPORT`` — Diffusion LM
  (non-transformer case D, experimental). Single transport: ``openai_compatible``.

Stage-wise routing (Phase 4+):
* ``$LLIVE_LLM_BACKEND_BY_STAGE`` — JSON map of llive 6 stage → backend name.
  E.g. ``{"salience":"mamba","monologue":"openai","action_plan":"jamba"}``.
  See :class:`llive.llm.stage_router.StageBackendRouter`.

Thought-factor → Δ bridge (Phase 5, ROADMAP case C):
* :mod:`llive.llm.factor_hook` defines the :class:`ThoughtFactorDeltaHook`
  protocol. Backends that support dynamic Δ (Mamba SSM transport) can
  consume hooks; others ignore them (no-op).
"""

from llive.llm.backend import (
    AnthropicBackend,
    DiffusionBackend,
    GenerateRequest,
    GenerateResponse,
    HFTransformersBackend,
    JambaBackend,
    LLMBackend,
    MambaBackend,
    MockBackend,
    OllamaBackend,
    OpenAIBackend,
    RwkvBackend,
    get_default_backend,
    resolve_backend,
)

__all__ = [
    "AnthropicBackend",
    "DiffusionBackend",
    "GenerateRequest",
    "GenerateResponse",
    "HFTransformersBackend",
    "JambaBackend",
    "LLMBackend",
    "MambaBackend",
    "MockBackend",
    "OllamaBackend",
    "OpenAIBackend",
    "RwkvBackend",
    "get_default_backend",
    "resolve_backend",
]
