# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the 4 new non-transformer backend skeletons + StageBackendRouter
+ ThoughtFactorDeltaHook (ROADMAP cases A/B/C/D/E).

All tests stub ``sys.modules["openai"]`` because every wrapper delegates to
OpenAIBackend which requires the openai SDK.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any
from unittest import mock

import pytest

from llive.llm import (
    DiffusionBackend,
    GenerateRequest,
    GenerateResponse,
    JambaBackend,
    LLMBackend,
    MambaBackend,
    RwkvBackend,
    resolve_backend,
)
from llive.llm.backend import reset_default_backend
from llive.llm.factor_hook import (
    FACTOR_NAMES,
    FactorSnapshot,
    HeuristicFactorHook,
    NoopFactorHook,
    ThoughtFactorDeltaHook,
    get_default_hook,
    reset_default_hook,
    set_default_hook,
)
from llive.llm.stage_router import (
    STAGE_NAMES,
    StageBackendRouter,
    get_default_router,
    reset_default_router,
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "LLIVE_LLM_BACKEND",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OLLAMA_HOST",
        "LLIVE_OPENAI_MODEL",
        "LLIVE_MAMBA_MODEL",
        "LLIVE_MAMBA_TRANSPORT",
        "LLIVE_RWKV_MODEL",
        "LLIVE_RWKV_TRANSPORT",
        "LLIVE_JAMBA_MODEL",
        "LLIVE_JAMBA_TRANSPORT",
        "LLIVE_DIFFUSION_MODEL",
        "LLIVE_DIFFUSION_TRANSPORT",
        "LLIVE_LLM_BACKEND_BY_STAGE",
    ):
        monkeypatch.delenv(var, raising=False)
    reset_default_backend()
    reset_default_router()
    reset_default_hook()


def _stub_openai(monkeypatch: pytest.MonkeyPatch) -> mock.MagicMock:
    fake = mock.MagicMock()
    monkeypatch.setitem(sys.modules, "openai", fake)
    return fake


# ---------------------------------------------------------------------------
# resolve_backend dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,cls",
    [
        ("mamba", MambaBackend),
        ("rwkv", RwkvBackend),
        ("jamba", JambaBackend),
        ("diffusion", DiffusionBackend),
    ],
)
def test_resolve_backend_dispatches_new_backends(
    monkeypatch: pytest.MonkeyPatch, name: str, cls: type[LLMBackend]
) -> None:
    _stub_openai(monkeypatch)
    backend = resolve_backend(name)
    assert isinstance(backend, cls)
    assert backend.name == name


def test_resolve_backend_unknown_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    with pytest.raises(ValueError, match="unknown LLM backend"):
        resolve_backend("nonexistent-backend")


# ---------------------------------------------------------------------------
# MambaBackend
# ---------------------------------------------------------------------------


def test_mamba_default_transport_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    backend = MambaBackend()
    assert backend.transport == "llama_cpp_server"
    assert backend.model == "codestral-mamba"
    assert backend.name == "mamba"
    assert backend.supports_coding is True
    assert backend.supports_vlm is False


def test_mamba_model_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    monkeypatch.setenv("LLIVE_MAMBA_MODEL", "codestral-mamba-7b-Q4_K_M")
    backend = MambaBackend()
    assert backend.model == "codestral-mamba-7b-Q4_K_M"


def test_mamba_ssm_transport_raises_not_implemented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_openai(monkeypatch)
    backend = MambaBackend(transport="mamba_ssm")
    with pytest.raises(NotImplementedError, match="mamba_ssm"):
        backend.generate(GenerateRequest(prompt="x"))


def test_mamba_unknown_transport_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    with pytest.raises(ValueError, match="unknown MambaBackend transport"):
        MambaBackend(transport="something_else")


def test_mamba_delegates_to_openai_with_overridden_backend_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_openai(monkeypatch)
    backend = MambaBackend()
    fake_response = GenerateResponse(
        text="hello", finish_reason="stop", backend="openai", model="codestral-mamba", raw={"id": "x"}
    )
    with mock.patch.object(backend._inner, "generate", return_value=fake_response):
        resp = backend.generate(GenerateRequest(prompt="hi"))
    assert resp.backend == "mamba"            # rewritten
    assert resp.raw["inner_backend"] == "openai"  # preserved for traceability


# ---------------------------------------------------------------------------
# RwkvBackend
# ---------------------------------------------------------------------------


def test_rwkv_default_transport_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    backend = RwkvBackend()
    assert backend.transport == "rwkv_cpp_server"
    assert backend.model == "rwkv-7-world-7b"
    assert backend.name == "rwkv"


def test_rwkv_model_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    monkeypatch.setenv("LLIVE_RWKV_MODEL", "rwkv-7-world-1.5b")
    backend = RwkvBackend()
    assert backend.model == "rwkv-7-world-1.5b"


def test_rwkv_py_transport_raises_not_implemented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_openai(monkeypatch)
    backend = RwkvBackend(transport="rwkv_py")
    with pytest.raises(NotImplementedError, match="rwkv_py"):
        backend.generate(GenerateRequest(prompt="x"))


# ---------------------------------------------------------------------------
# JambaBackend / DiffusionBackend
# ---------------------------------------------------------------------------


def test_jamba_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    backend = JambaBackend()
    assert backend.name == "jamba"
    assert backend.model == "jamba-1.5-mini"
    assert backend.transport == "llama_cpp_server"


def test_diffusion_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    backend = DiffusionBackend()
    assert backend.name == "diffusion"
    assert backend.model == "elyza-llm-diffusion"
    assert backend.transport == "openai_compatible"


# ---------------------------------------------------------------------------
# StageBackendRouter
# ---------------------------------------------------------------------------


def test_stage_router_empty_mapping_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_openai(monkeypatch)
    router = StageBackendRouter()
    backend = router.for_stage("salience")
    assert backend.name == "mock"  # default fallback in isolated env


def test_stage_router_explicit_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    router = StageBackendRouter({"salience": "rwkv", "monologue": "mamba"})
    assert router.for_stage("salience").name == "rwkv"
    assert router.for_stage("monologue").name == "mamba"
    # unknown stage → default
    assert router.for_stage("nonexistent").name == "mock"


def test_stage_router_caches_per_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    router = StageBackendRouter({"salience": "rwkv", "scorer": "rwkv"})
    a = router.for_stage("salience")
    b = router.for_stage("scorer")
    assert a is b  # shared cache for same backend name


def test_stage_router_loads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    monkeypatch.setenv(
        "LLIVE_LLM_BACKEND_BY_STAGE",
        '{"salience":"rwkv","action_plan":"jamba"}',
    )
    router = StageBackendRouter()
    assert router.mapping == {"salience": "rwkv", "action_plan": "jamba"}
    assert router.for_stage("salience").name == "rwkv"
    assert router.for_stage("action_plan").name == "jamba"


def test_stage_router_invalid_json_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openai(monkeypatch)
    monkeypatch.setenv("LLIVE_LLM_BACKEND_BY_STAGE", "not json")
    router = StageBackendRouter()
    assert router.mapping == {}


def test_stage_router_stage_name_canonical_set() -> None:
    assert set(STAGE_NAMES) == {
        "salience",
        "curiosity",
        "monologue",
        "scorer",
        "action_plan",
        "finalise",
    }


def test_default_router_is_singleton() -> None:
    a = get_default_router()
    b = get_default_router()
    assert a is b
    reset_default_router()
    c = get_default_router()
    assert c is not a


# ---------------------------------------------------------------------------
# ThoughtFactorDeltaHook
# ---------------------------------------------------------------------------


def test_factor_names_count_is_ten() -> None:
    assert len(FACTOR_NAMES) == 10


def test_factor_snapshot_clamps_to_unit_interval() -> None:
    snap = FactorSnapshot(values={"uncertainty": -5.0, "integrate": 99.0})
    assert snap.get("uncertainty") == 0.0
    assert snap.get("integrate") == 1.0
    # missing factors default to 0.5 (neutral)
    assert snap.get("structurize") == 0.5


def test_factor_snapshot_vector_in_canonical_order() -> None:
    snap = FactorSnapshot(values={"uncertainty": 0.9, "integrate": 0.1})
    vec = snap.vector()
    assert len(vec) == 10
    assert vec[FACTOR_NAMES.index("uncertainty")] == 0.9
    assert vec[FACTOR_NAMES.index("integrate")] == 0.1


def test_noop_hook_always_returns_one() -> None:
    hook = NoopFactorHook()
    assert hook.delta_for(FactorSnapshot()) == 1.0
    assert hook.delta_for(FactorSnapshot(values={"uncertainty": 1.0})) == 1.0


def test_heuristic_hook_responds_to_uncertainty() -> None:
    hook = HeuristicFactorHook()
    high_unc = FactorSnapshot(values={"uncertainty": 1.0, "integrate": 0.0})
    low_unc = FactorSnapshot(values={"uncertainty": 0.0, "integrate": 1.0, "structurize": 1.0})
    # High uncertainty → smaller delta; high integration → larger delta
    assert hook.delta_for(high_unc) < 1.0
    assert hook.delta_for(low_unc) > 1.0


def test_heuristic_hook_clamps_to_range() -> None:
    hook = HeuristicFactorHook(sensitivity=100.0)  # force extreme signal
    saturated = FactorSnapshot(values={"integrate": 1.0, "structurize": 1.0, "exploration": 1.0})
    delta = hook.delta_for(saturated)
    assert 0.25 <= delta <= 4.0  # hard clamp per impl


def test_default_hook_is_noop_initially() -> None:
    hook = get_default_hook()
    assert isinstance(hook, NoopFactorHook)
    assert hook.delta_for(FactorSnapshot()) == 1.0


def test_set_default_hook_overrides_singleton() -> None:
    set_default_hook(HeuristicFactorHook())
    assert isinstance(get_default_hook(), HeuristicFactorHook)
    reset_default_hook()
    assert isinstance(get_default_hook(), NoopFactorHook)


def test_factor_hook_protocol_runtime_check() -> None:
    """NoopFactorHook / HeuristicFactorHook satisfy the Protocol."""
    assert isinstance(NoopFactorHook(), ThoughtFactorDeltaHook)
    assert isinstance(HeuristicFactorHook(), ThoughtFactorDeltaHook)
