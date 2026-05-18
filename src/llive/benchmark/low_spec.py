# SPDX-License-Identifier: Apache-2.0
"""Low-spec PC benchmark harness — non-transformer ROADMAP §0.2.

Goal: measure each LLM backend (mamba / rwkv / jamba / openai / etc.) on
the **user's primary deployment env** — a low-spec personal PC — across a
progressive token-length matrix. Until a candidate hits the §0.2 targets
here, it is not eligible for promotion to "implements case A/B/C/D/E".

Design:

* xs/s/m/l/xl payload sizes (matching feedback_benchmark_progressive_tokens).
* Each run records wall-clock latency, peak RSS, tokens/s, and the backend
  tag (so feedback_llive_measurement_purity 2-stream separation holds).
* psutil is optional — when missing, RSS is reported as ``None`` and only
  latency / tok/s are recorded. The harness still runs end-to-end so this
  module stays useful in skeleton form before extras are installed.
* All cloud backends (openai-with-real-key, anthropic) are *explicitly
  excluded* by default — the harness refuses to measure them in low_spec
  mode unless ``allow_cloud=True`` is passed. This enforces the on-prem
  primary discipline.

Output: a list of :class:`LowSpecRunResult` (JSON-friendly via ``asdict``).
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from typing import Iterable

from llive.llm import GenerateRequest, LLMBackend, resolve_backend

# Approximate token counts for each size bucket (English-ish, ~4 chars/tok).
SIZE_CHARS: dict[str, int] = {
    "xs": 2_000,    # ≈ 500 tok
    "s":  8_000,    # ≈ 2k tok
    "m":  32_000,   # ≈ 8k tok
    "l":  128_000,  # ≈ 32k tok
    "xl": 512_000,  # ≈ 128k tok
}

# §0.2 targets (latency seconds, RAM MB) for low-spec CPU-only PC.
TARGETS: dict[str, tuple[float, int]] = {
    "xs": (3.0,    4_000),
    "s":  (8.0,    6_000),
    "m":  (20.0,   8_000),
    "l":  (60.0,  10_000),
    "xl": (180.0, 14_000),
}

# Backends that DO call out to a paid cloud LLM service — refused unless
# allow_cloud=True. Local OpenAI-compatible servers (llama-server / vLLM /
# LM Studio) are still allowed under "openai" because the discriminator is
# OPENAI_BASE_URL: if it's localhost/LAN, we permit; otherwise reject.
_CLOUD_BACKEND_NAMES: frozenset[str] = frozenset({"anthropic"})


@dataclass
class LowSpecRunResult:
    backend: str
    size: str
    prompt_chars: int
    latency_s: float
    output_chars: int
    tokens_per_second: float | None
    peak_rss_mb: float | None
    target_latency_s: float
    target_rss_mb: int
    meets_latency_target: bool
    meets_rss_target: bool | None  # None when RSS unmeasured
    finish_reason: str
    notes: list[str] = field(default_factory=list)


def _peak_rss_mb() -> float | None:
    """Best-effort process RSS in MB. Returns None when psutil is missing."""
    try:
        import psutil  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return None
    rss = psutil.Process().memory_info().rss
    return rss / (1024 * 1024)


def _is_cloud_openai() -> bool:
    """Heuristic: OPENAI_BASE_URL pointing at a public host = cloud OpenAI."""
    base = os.environ.get("OPENAI_BASE_URL", "").lower()
    if not base:
        # Default openai.com endpoint = cloud
        return True
    return not any(token in base for token in ("localhost", "127.0.0.1", "0.0.0.0"))


def _refuse_cloud(backend_name: str, allow_cloud: bool) -> str | None:
    """Return a refusal note string, or None if backend is permitted."""
    bn = (backend_name or "").lower()
    if bn in _CLOUD_BACKEND_NAMES and not allow_cloud:
        return f"refused: {bn!r} is a cloud backend; pass allow_cloud=True to override"
    if bn == "openai" and _is_cloud_openai() and not allow_cloud:
        return (
            "refused: 'openai' backend with cloud OPENAI_BASE_URL detected; "
            "set OPENAI_BASE_URL to a localhost/LAN llama-server or pass allow_cloud=True"
        )
    return None


def _make_prompt(char_count: int) -> str:
    """Generate a deterministic prompt of approx ``char_count`` characters."""
    # Single tokenisable sentence repeated — keeps the LM warm but doesn't
    # bias toward any particular benchmark dataset.
    base = (
        "Summarise the technical merits of state-space models for on-prem "
        "language inference on low-spec hardware. "
    )
    if char_count <= 0:
        return base
    reps = max(1, char_count // len(base))
    body = base * reps
    return body[:char_count]


def run_size(
    backend: LLMBackend,
    size: str,
    *,
    max_tokens: int = 256,
    temperature: float = 0.2,
    allow_cloud: bool = False,
) -> LowSpecRunResult:
    """Run one (backend, size) cell of the progressive matrix."""
    if size not in SIZE_CHARS:
        raise ValueError(f"unknown size {size!r}; valid: {tuple(SIZE_CHARS)}")
    target_latency, target_rss = TARGETS[size]
    prompt = _make_prompt(SIZE_CHARS[size])
    notes: list[str] = []

    refusal = _refuse_cloud(backend.name, allow_cloud)
    if refusal is not None:
        notes.append(refusal)
        return LowSpecRunResult(
            backend=backend.name,
            size=size,
            prompt_chars=len(prompt),
            latency_s=0.0,
            output_chars=0,
            tokens_per_second=None,
            peak_rss_mb=None,
            target_latency_s=target_latency,
            target_rss_mb=target_rss,
            meets_latency_target=False,
            meets_rss_target=None,
            finish_reason="refused",
            notes=notes,
        )

    t0 = time.perf_counter()
    resp = backend.generate(
        GenerateRequest(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
    )
    latency = time.perf_counter() - t0

    out_chars = len(resp.text)
    # Rough tok/s: assume ~4 chars/tok on the output side
    tok_per_s = (out_chars / 4.0) / latency if latency > 0 else None
    rss = _peak_rss_mb()

    return LowSpecRunResult(
        backend=resp.backend or backend.name,
        size=size,
        prompt_chars=len(prompt),
        latency_s=latency,
        output_chars=out_chars,
        tokens_per_second=tok_per_s,
        peak_rss_mb=rss,
        target_latency_s=target_latency,
        target_rss_mb=target_rss,
        meets_latency_target=latency <= target_latency,
        meets_rss_target=(rss is not None and rss <= target_rss) if rss is not None else None,
        finish_reason=resp.finish_reason,
        notes=notes,
    )


def run_matrix(
    backend_names: Iterable[str],
    *,
    sizes: Iterable[str] = ("xs", "s", "m"),
    max_tokens: int = 256,
    allow_cloud: bool = False,
) -> list[LowSpecRunResult]:
    """Run the progressive matrix across multiple backends.

    Default sizes are xs/s/m — l and xl are opt-in because a single l cell can
    take minutes on a low-spec PC. Run xl only after smaller cells confirm
    the candidate is viable.
    """
    results: list[LowSpecRunResult] = []
    for name in backend_names:
        backend = resolve_backend(name)
        for size in sizes:
            results.append(
                run_size(
                    backend,
                    size,
                    max_tokens=max_tokens,
                    allow_cloud=allow_cloud,
                )
            )
    return results


def to_json(results: Iterable[LowSpecRunResult]) -> list[dict]:
    """Convert results to JSON-friendly dicts (for ``json.dumps``)."""
    return [asdict(r) for r in results]
