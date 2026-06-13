# SPDX-License-Identifier: Apache-2.0
"""Per-evaluation hang guard for LLM fitness (eval_timeout_seconds).

A real on-prem backend (ollama 等) can hang on a stalled generate() and, without
a guard, freeze the whole evolution run on a single individual. This is the
real-LLM counterpart of the population-collapse guard (ユーザー要望 2026-05-24:
長時間 run で停止しないこと). These tests prove a hung evaluation is cut off and
the individual culled (fitness=0), while normal/fast evals are unaffected.
"""

from __future__ import annotations

import threading
import time

from llive.llm.backend import MockBackend
from llive.perf.evolutionary.fitness_llm import (
    LLM_GENOME_BOUNDS,
    LLM_GENOME_LABELS,
    LlmFitnessConfig,
    llm_fitness_factory,
)
from llive.perf.evolutionary.genome import Genome


def _genome() -> Genome:
    # backend_id=0, temperature=0.7, top_p=0.9, kv=0, model=0 (all within bounds)
    return Genome.from_values(
        [0.0, 0.7, 0.9, 0.0, 0.0], LLM_GENOME_BOUNDS, labels=LLM_GENOME_LABELS
    )


class _HangingBackend(MockBackend):
    """generate() blocks until released (or 10s) — simulates a stalled LLM call."""

    def __init__(self, release: threading.Event) -> None:
        super().__init__()
        self._release = release

    def generate(self, request):  # noqa: ANN001
        self._release.wait(timeout=10.0)
        return super().generate(request)


def test_eval_timeout_culls_hung_evaluation() -> None:
    release = threading.Event()
    cfg = LlmFitnessConfig(
        backend_factory=lambda name: _HangingBackend(release),
        eval_timeout_seconds=0.2,
        prompts=("hi",),
        n_stability_samples=1,
        danger_prompts=(),
    )
    fit = llm_fitness_factory(cfg)
    try:
        t0 = time.perf_counter()
        report = fit(_genome())
        elapsed = time.perf_counter() - t0
        # returned at ~timeout, NOT blocked on the 10s hung call
        assert elapsed < 3.0
        assert report.score == 0.0
        assert "eval_timeout" in report.breakdown
        assert "eval_timeout" in report.notes
        assert report.n_samples == 0
    finally:
        release.set()  # let the orphan thread exit promptly (avoid atexit join delay)


def test_fast_eval_under_timeout_succeeds() -> None:
    # timeout set but eval is fast (MockBackend) → no cull, real 5-axis score.
    cfg = LlmFitnessConfig(
        backend_factory=None,  # MockBackend fixed
        eval_timeout_seconds=5.0,
        prompts=("hi",),
        n_stability_samples=1,
        danger_prompts=(),
    )
    report = llm_fitness_factory(cfg)(_genome())
    assert report.score > 0.0
    assert "eval_timeout" not in report.breakdown


def test_no_timeout_is_backward_compatible() -> None:
    # default eval_timeout_seconds=None → inline path, unchanged behaviour.
    assert LlmFitnessConfig().eval_timeout_seconds is None
    cfg = LlmFitnessConfig(
        backend_factory=None,
        prompts=("hi",),
        n_stability_samples=1,
        danger_prompts=(),
    )
    report = llm_fitness_factory(cfg)(_genome())
    assert report.score > 0.0
    assert "eval_timeout" not in report.breakdown
