# SPDX-License-Identifier: Apache-2.0
"""FullSenseLoop x StageBackendRouter wiring tests (Non-Transformer case B).

Covers the stage-wise dispatch path added in 2026-05-18:

1. ``stage_router=`` injection at construction is honoured for the
   ``monologue`` stage (Inner Monologue).
2. If ``stage_router=`` is set but the requested stage is unmapped, the
   resolver falls through to the env-driven default (back-compat).
3. ``stage_router=None`` (default) preserves the legacy single-backend
   resolution exactly.
4. Explicit ``llm_backend=`` injection still wins over the router (highest
   precedence — useful for ad-hoc test overrides).
"""

from __future__ import annotations

import pytest

from llive.fullsense.loop import FullSenseLoop
from llive.fullsense.types import Stimulus
from llive.llm.backend import GenerateRequest, GenerateResponse, LLMBackend
from llive.llm.stage_router import StageBackendRouter


class _StubBackend(LLMBackend):
    name = "stub-default"

    def __init__(self, text: str, tag: str | None = None) -> None:
        self.text = text
        self.name = tag or "stub"
        self.calls: list[GenerateRequest] = []

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.calls.append(request)
        return GenerateResponse(text=self.text, backend=self.name, model=f"{self.name}-1")


def _stim() -> Stimulus:
    return Stimulus(content="A contradiction-themed stimulus for routing.", surprise=0.7)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "LLIVE_LLM_BACKEND",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OLLAMA_HOST",
        "LLIVE_LLM_BACKEND_BY_STAGE",
        "LLIVE_ALLOW_CLOUD_BACKEND",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# 1. Stage-wise routing on the monologue stage
# ---------------------------------------------------------------------------


def test_router_monologue_stage_uses_router_backend() -> None:
    """When the router maps "monologue" → a specific backend, it should be used."""
    monologue_backend = _StubBackend(text="ROUTED THROUGH MONOLOGUE STAGE", tag="route_m")
    router = StageBackendRouter({"monologue": "mock"})  # placeholder mapping
    # Replace the resolved backend so we can observe the call.
    router._cache["mock"] = monologue_backend  # noqa: SLF001
    router._mapping["monologue"] = "mock"      # noqa: SLF001

    loop = FullSenseLoop(sandbox=True, stage_router=router)
    result = loop.process(_stim())
    assert len(monologue_backend.calls) == 1
    assert result.stages["thought"]["text"] == "ROUTED THROUGH MONOLOGUE STAGE"


# ---------------------------------------------------------------------------
# 2. Unmapped stage falls through to env-driven default
# ---------------------------------------------------------------------------


def test_router_unmapped_stage_falls_through_to_env_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If router has no mapping for "monologue", env LLIVE_LLM_BACKEND wins."""
    # Map only "salience" — leave "monologue" unmapped.
    router = StageBackendRouter({"salience": "mock"})
    # Env points to ollama (on-prem, allowed without override). The actual
    # ollama call will fail (no daemon) → template fallback. The important
    # thing here is that no exception bubbles up, i.e. the resolver did NOT
    # short-circuit on the unmapped "monologue" stage.
    monkeypatch.setenv("LLIVE_LLM_BACKEND", "ollama:nonexistent-model")

    loop = FullSenseLoop(sandbox=True, stage_router=router)
    # Must not raise — the unmapped stage falls through to env, env tries
    # ollama, ollama fails, template kicks in.
    result = loop.process(_stim())
    assert result.stages["thought"]["text"].startswith("Observation about")


# ---------------------------------------------------------------------------
# 3. No router → legacy resolution preserved
# ---------------------------------------------------------------------------


def test_no_router_legacy_resolution_preserved() -> None:
    """Default constructor (no router) keeps the rule-based template path."""
    loop = FullSenseLoop(sandbox=True)  # no llm_backend, no stage_router
    result = loop.process(_stim())
    # No backend configured → template
    assert result.stages["thought"]["text"].startswith("Observation about")


# ---------------------------------------------------------------------------
# 4. Explicit llm_backend= wins over router (highest precedence)
# ---------------------------------------------------------------------------


def test_explicit_backend_kwarg_overrides_router() -> None:
    """``llm_backend=`` injected at construction beats the router."""
    router_backend = _StubBackend(text="FROM ROUTER", tag="router")
    direct_backend = _StubBackend(text="FROM DIRECT", tag="direct")

    router = StageBackendRouter({"monologue": "mock"})
    router._cache["mock"] = router_backend  # noqa: SLF001

    loop = FullSenseLoop(
        sandbox=True,
        llm_backend=direct_backend,
        stage_router=router,
    )
    result = loop.process(_stim())
    # The explicit backend must have been used, not the router's.
    assert len(direct_backend.calls) == 1
    assert len(router_backend.calls) == 0
    assert result.stages["thought"]["text"] == "FROM DIRECT"
