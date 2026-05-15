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
   ``ollama`` / ``llama_cpp``.
2. ``$ANTHROPIC_API_KEY`` is set → ``anthropic``.
3. ``$OPENAI_API_KEY`` is set → ``openai``.
4. ``$OLLAMA_HOST`` is set → ``ollama``.
5. Fallback: ``mock`` (deterministic, no network).
"""

from llive.llm.backend import (
    AnthropicBackend,
    GenerateRequest,
    GenerateResponse,
    LLMBackend,
    MockBackend,
    OllamaBackend,
    OpenAIBackend,
    get_default_backend,
    resolve_backend,
)

__all__ = [
    "AnthropicBackend",
    "GenerateRequest",
    "GenerateResponse",
    "LLMBackend",
    "MockBackend",
    "OllamaBackend",
    "OpenAIBackend",
    "get_default_backend",
    "resolve_backend",
]
