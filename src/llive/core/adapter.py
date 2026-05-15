# SPDX-License-Identifier: Apache-2.0
"""Core Model Adapter (CORE-01, CORE-02).

Phase 1 では `HFAdapter` (HuggingFace transformers) のみ実装する。
torch / transformers / accelerate は optional dependency (`pip install
llmesh-llive[torch]`) で、未インストール環境では `HFAdapter()` が
`ModuleNotFoundError` を raise する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class AdapterConfig:
    """Configuration that abstracts away tokenizer / context / precision differences."""

    model_name: str
    tokenizer_name: str | None = None  # defaults to model_name
    context_length: int | None = None  # None → defer to model config
    dtype: str = "auto"                # "auto" / "float16" / "bfloat16" / "float32"
    device_map: str | None = "auto"    # passed to from_pretrained
    trust_remote_code: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    """Output of `BaseModelAdapter.generate`."""

    text: str
    prompt: str
    output_tokens: list[int]
    prompt_tokens: list[int]
    hidden_states: Any | None = None  # last-layer hidden states (optional)
    logits: Any | None = None         # final-step logits (optional)
    raw: Any | None = None            # backend-specific raw output


@runtime_checkable
class BaseModelAdapter(Protocol):
    """Minimal interface every L3 adapter must satisfy."""

    config: AdapterConfig

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 32,
        *,
        return_hidden_states: bool = False,
        **kwargs: Any,
    ) -> GenerationResult: ...

    def encode(self, text: str) -> list[int]: ...

    def decode(self, tokens: list[int]) -> str: ...


class HFAdapter:
    """HuggingFace transformers-based adapter.

    Lazy-imports `transformers` / `torch` so this module is importable in
    environments without the heavy ML stack (used by tests that mock the
    adapter, or by the CLI when listing schemas).
    """

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config
        self._tokenizer = None
        self._model = None
        self._torch = None

    # -- lazy initialisation -----------------------------------------------

    def _ensure_loaded(self) -> None:  # pragma: no cover - exercised only when torch is installed
        if self._model is not None:
            return
        try:
            import torch  # type: ignore[import-not-found]
            from transformers import (  # type: ignore[import-not-found]
                AutoModelForCausalLM,
                AutoTokenizer,
            )
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "HFAdapter requires the `torch` extra: install with "
                "`pip install llmesh-llive[torch]`"
            ) from exc

        cfg = self.config
        self._torch = torch
        dtype_map = {
            "auto": "auto",
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
        }
        dtype = dtype_map.get(cfg.dtype, "auto")
        tok_name = cfg.tokenizer_name or cfg.model_name
        self._tokenizer = AutoTokenizer.from_pretrained(
            tok_name, trust_remote_code=cfg.trust_remote_code
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            cfg.model_name,
            torch_dtype=dtype,
            device_map=cfg.device_map,
            trust_remote_code=cfg.trust_remote_code,
        )
        self._model.eval()

    # -- public API --------------------------------------------------------

    def encode(self, text: str) -> list[int]:  # pragma: no cover - requires torch
        self._ensure_loaded()
        assert self._tokenizer is not None
        return self._tokenizer.encode(text)

    def decode(self, tokens: list[int]) -> str:  # pragma: no cover - requires torch
        self._ensure_loaded()
        assert self._tokenizer is not None
        return self._tokenizer.decode(tokens, skip_special_tokens=True)

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 32,
        *,
        return_hidden_states: bool = False,
        **kwargs: Any,
    ) -> GenerationResult:  # pragma: no cover - requires torch
        self._ensure_loaded()
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._torch is not None
        torch = self._torch
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            output = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                output_hidden_states=return_hidden_states,
                return_dict_in_generate=True,
                **kwargs,
            )
        sequences = output.sequences[0]
        prompt_len = inputs["input_ids"].shape[1]
        prompt_tokens = sequences[:prompt_len].tolist()
        output_tokens = sequences[prompt_len:].tolist()
        text = self._tokenizer.decode(output_tokens, skip_special_tokens=True)
        hidden = None
        if return_hidden_states and getattr(output, "hidden_states", None) is not None:
            # last layer of last generated step
            hidden = output.hidden_states[-1][-1]
        return GenerationResult(
            text=text,
            prompt=prompt,
            output_tokens=output_tokens,
            prompt_tokens=prompt_tokens,
            hidden_states=hidden,
            raw=output,
        )


__all__ = ["AdapterConfig", "BaseModelAdapter", "GenerationResult", "HFAdapter"]
