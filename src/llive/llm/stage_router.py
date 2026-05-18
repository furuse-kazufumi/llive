# SPDX-License-Identifier: Apache-2.0
"""Stage-wise LLM backend routing — non-transformer ROADMAP case B (Jamba-style).

Lets llive's 6-stage FullSenseLoop pick a different backend per stage so the
"in-context learning vs efficiency" trade-off can be tuned per cognitive step
without recompiling. Configuration is via env var
``LLIVE_LLM_BACKEND_BY_STAGE`` — a JSON object whose keys are stage names
and whose values are backend names accepted by :func:`resolve_backend`.

Example::

    $env:LLIVE_LLM_BACKEND_BY_STAGE = '{"salience":"mamba","monologue":"openai"}'

Stage names recognised by the router (matching ``FullSenseLoop`` step ids):

* ``salience`` — Salience Gate
* ``curiosity`` — Curiosity Drive
* ``monologue`` — Inner Monologue
* ``scorer`` — Ego/Altruism Scorer
* ``action_plan`` — Action Plan
* ``finalise`` — Finalise / Approval Bus + Ledger

Unknown stage names fall through to the default backend (``LLIVE_LLM_BACKEND``
env or :func:`resolve_backend` auto-detection).

This module is **read-only at runtime** — backends are instantiated lazily
on first use of a stage and cached per-stage.
"""
from __future__ import annotations

import json
import os
from typing import Mapping

from llive.llm.backend import LLMBackend, get_default_backend, resolve_backend

STAGE_NAMES: tuple[str, ...] = (
    "salience",
    "curiosity",
    "monologue",
    "scorer",
    "action_plan",
    "finalise",
)


class StageBackendRouter:
    """Resolves a backend per llive 6-stage step.

    Construction is cheap; backend instantiation is lazy. Tests can pass an
    explicit ``mapping`` to bypass env parsing.
    """

    def __init__(self, mapping: Mapping[str, str] | None = None) -> None:
        if mapping is None:
            mapping = self._load_from_env()
        self._mapping: dict[str, str] = dict(mapping)
        self._cache: dict[str, LLMBackend] = {}

    @staticmethod
    def _load_from_env() -> dict[str, str]:
        raw = os.environ.get("LLIVE_LLM_BACKEND_BY_STAGE", "")
        if not raw.strip():
            return {}
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            # Invalid JSON → no per-stage routing; everything falls through.
            return {}
        if not isinstance(obj, dict):
            return {}
        return {
            str(k).strip().lower(): str(v).strip().lower()
            for k, v in obj.items()
            if isinstance(k, str) and isinstance(v, str)
        }

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self._mapping)

    def for_stage(self, stage: str) -> LLMBackend:
        """Return the backend assigned to ``stage`` (or the default)."""
        stage_key = (stage or "").strip().lower()
        backend_name = self._mapping.get(stage_key)
        if backend_name is None:
            return get_default_backend()
        cached = self._cache.get(backend_name)
        if cached is not None:
            return cached
        backend = resolve_backend(backend_name)
        self._cache[backend_name] = backend
        return backend

    def reset_cache(self) -> None:
        """For tests: drop the cached backend instances."""
        self._cache.clear()


# Module-level singleton — one router per process.
_DEFAULT_ROUTER: StageBackendRouter | None = None


def get_default_router() -> StageBackendRouter:
    global _DEFAULT_ROUTER
    if _DEFAULT_ROUTER is None:
        _DEFAULT_ROUTER = StageBackendRouter()
    return _DEFAULT_ROUTER


def reset_default_router() -> None:
    """For tests: drop the cached default router."""
    global _DEFAULT_ROUTER
    _DEFAULT_ROUTER = None
