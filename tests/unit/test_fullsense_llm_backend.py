# SPDX-License-Identifier: Apache-2.0
"""FullSenseLoop x LLM backend wiring tests (LLIVE-001 wiring).

Covers the opt-in path added to ``_inner_monologue``:

1. Explicit ``llm_backend=`` injection is honoured.
2. Backend failure falls through to the rule-based template.
3. ``$LLIVE_LLM_BACKEND`` env opt-in for ollama (on-prem) works.
4. ``$LLIVE_LLM_BACKEND`` env for cloud backends is REFUSED without
   ``LLIVE_ALLOW_CLOUD_BACKEND=1`` (purity guard — see
   ``feedback_llive_measurement_purity``).
5. ``$LLIVE_LLM_BACKEND=mock`` and unset behave identically (template).
"""

from __future__ import annotations

import pytest

from llive.fullsense.loop import BackendConfigurationError, FullSenseLoop
from llive.fullsense.types import Stimulus
from llive.llm.backend import (
    GenerateRequest,
    GenerateResponse,
    LLMBackend,
)


class _StubBackend(LLMBackend):
    """Records calls. ``text`` is returned verbatim; ``raise_with`` simulates failure."""

    name = "stub"

    def __init__(self, text: str = "STUB OUTPUT", raise_with: Exception | None = None) -> None:
        self.text = text
        self.raise_with = raise_with
        self.calls: list[GenerateRequest] = []

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.calls.append(request)
        if self.raise_with is not None:
            raise self.raise_with
        return GenerateResponse(text=self.text, backend="stub", model="stub-1")


def _stim() -> Stimulus:
    return Stimulus(content="A medium-length stimulus about contradiction in design.", surprise=0.7)


# ---------------------------------------------------------------------------
# 1. injection
# ---------------------------------------------------------------------------


def test_inner_monologue_uses_injected_backend() -> None:
    backend = _StubBackend(text="injected LLM thought")
    loop = FullSenseLoop(sandbox=True, llm_backend=backend)
    result = loop.process(_stim())
    thought = result.stages["thought"]
    assert isinstance(thought, dict)
    assert thought["text"] == "injected LLM thought"
    assert len(backend.calls) == 1
    # Prompt should mention the stimulus content somewhere.
    assert "contradiction" in backend.calls[0].prompt.lower()


def test_inner_monologue_falls_back_when_backend_raises() -> None:
    backend = _StubBackend(raise_with=RuntimeError("backend exploded"))
    loop = FullSenseLoop(sandbox=True, llm_backend=backend)
    result = loop.process(_stim())
    # Fall-through means we land on the template, prefixed with "Observation about".
    assert result.stages["thought"]["text"].startswith("Observation about")


def test_inner_monologue_falls_back_when_backend_returns_empty() -> None:
    backend = _StubBackend(text="")
    loop = FullSenseLoop(sandbox=True, llm_backend=backend)
    result = loop.process(_stim())
    assert result.stages["thought"]["text"].startswith("Observation about")


# ---------------------------------------------------------------------------
# 2. env-driven default resolution (no injection)
# ---------------------------------------------------------------------------


def test_default_path_no_env_uses_template(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLIVE_LLM_BACKEND", raising=False)
    monkeypatch.delenv("LLIVE_ALLOW_CLOUD_BACKEND", raising=False)
    loop = FullSenseLoop(sandbox=True)
    result = loop.process(_stim())
    assert result.stages["thought"]["text"].startswith("Observation about")


def test_env_mock_keeps_template(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLIVE_LLM_BACKEND", "mock")
    loop = FullSenseLoop(sandbox=True)
    result = loop.process(_stim())
    assert result.stages["thought"]["text"].startswith("Observation about")


# ---------------------------------------------------------------------------
# 3. cloud purity guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", ["anthropic", "openai"])
def test_cloud_backend_refused_without_explicit_override(
    monkeypatch: pytest.MonkeyPatch, vendor: str
) -> None:
    monkeypatch.setenv("LLIVE_LLM_BACKEND", vendor)
    monkeypatch.delenv("LLIVE_ALLOW_CLOUD_BACKEND", raising=False)
    loop = FullSenseLoop(sandbox=True)
    with pytest.raises(BackendConfigurationError, match=vendor):
        loop.process(_stim())


def test_cloud_backend_override_attempts_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """With override set, ``_resolve_backend_for_loop`` is allowed to try.

    We use an unknown vendor so resolve_backend raises and the loop's
    inner exception handler falls back to the template (no exception
    bubbles up).
    """
    monkeypatch.setenv("LLIVE_LLM_BACKEND", "no-such-vendor")
    monkeypatch.setenv("LLIVE_ALLOW_CLOUD_BACKEND", "1")
    loop = FullSenseLoop(sandbox=True)
    result = loop.process(_stim())
    assert result.stages["thought"]["text"].startswith("Observation about")


# ---------------------------------------------------------------------------
# 4. ollama path stays open without override (on-prem first)
# ---------------------------------------------------------------------------


def test_env_ollama_attempts_resolution_without_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ollama`` is allowed without LLIVE_ALLOW_CLOUD_BACKEND because it's on-prem.

    We don't have a daemon in the test environment, so the call will fail
    and the loop falls back to the template — but the important thing is
    that ``BackendConfigurationError`` is NOT raised for ``ollama``.
    """
    monkeypatch.setenv("LLIVE_LLM_BACKEND", "ollama:no-such-model")
    monkeypatch.delenv("LLIVE_ALLOW_CLOUD_BACKEND", raising=False)
    loop = FullSenseLoop(sandbox=True)
    # Must NOT raise BackendConfigurationError.
    result = loop.process(_stim())
    # The actual ollama call will fail (no daemon / unknown model), so we
    # land on the template.
    assert result.stages["thought"]["text"].startswith("Observation about")
