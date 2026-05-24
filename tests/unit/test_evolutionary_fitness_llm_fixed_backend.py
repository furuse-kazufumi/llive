# SPDX-License-Identifier: Apache-2.0
"""LlmFitnessConfig.fixed_backend — real-LLM run backend pinning.

A real ollama run needs every individual evaluated on ollama, but ollama is not
in the evolvable backend vocabulary (_BACKEND_NAMES). fixed_backend pins the
backend without touching genome semantics / the freeze point. on-prem purity is
still enforced by the factory (cloud rejected).
"""

from __future__ import annotations

from llive.llm.backend import MockBackend
from llive.perf.evolutionary.fitness_llm import (
    LLM_GENOME_BOUNDS,
    LLM_GENOME_LABELS,
    LlmFitnessConfig,
    llm_fitness_factory,
)
from llive.perf.evolutionary.genome import Genome


def _genome(backend_id: float = 0.0) -> Genome:
    return Genome.from_values(
        [backend_id, 0.7, 0.9, 0.0, 0.0], LLM_GENOME_BOUNDS, labels=LLM_GENOME_LABELS
    )


def test_fixed_backend_overrides_genome_backend_id() -> None:
    seen: list[str] = []

    def factory(name: str) -> MockBackend:
        seen.append(name)
        return MockBackend()

    cfg = LlmFitnessConfig(
        backend_factory=factory,
        fixed_backend="ollama",
        prompts=("hi",),
        n_stability_samples=1,
        danger_prompts=(),
    )
    # genome selects backend_id=0 (mock), but fixed_backend must win.
    report = llm_fitness_factory(cfg)(_genome(backend_id=0.0))
    assert seen == ["ollama"]
    assert "backend=ollama" in report.notes


def test_fixed_cloud_backend_culled_by_purity() -> None:
    # default factory = on-prem fail-closed → a fixed cloud backend is rejected.
    cfg = LlmFitnessConfig(
        fixed_backend="anthropic",
        prompts=("hi",),
        n_stability_samples=1,
        danger_prompts=(),
    )
    report = llm_fitness_factory(cfg)(_genome())
    assert report.score == 0.0
    assert "purity_violation" in report.breakdown


def test_no_fixed_backend_uses_genome_selection() -> None:
    # default fixed_backend=None → genome backend_id drives selection (regression).
    assert LlmFitnessConfig().fixed_backend is None
    cfg = LlmFitnessConfig(
        backend_factory=None,  # MockBackend fixed
        prompts=("hi",),
        n_stability_samples=1,
        danger_prompts=(),
    )
    report = llm_fitness_factory(cfg)(_genome(backend_id=0.0))
    assert "backend=mock" in report.notes
