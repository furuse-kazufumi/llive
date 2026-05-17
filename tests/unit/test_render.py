# SPDX-License-Identifier: Apache-2.0
"""VRB-06 — DualSpecWriter tests."""

from __future__ import annotations

import pytest

from llive.brief import (
    Brief,
    DualSpecWriter,
    EvalSpec,
    Metric,
    RenderMode,
    StopCondition,
)


def _brief() -> Brief:
    return Brief(
        brief_id="r1",
        goal="ingest 10k events/s on a single node",
        constraints=("p99 < 100ms", "memory <= 2GB"),
        tools=("echo",),
        success_criteria=("zero data loss",),
    )


def test_render_human_brief_contains_sections() -> None:
    out = DualSpecWriter().render(_brief(), RenderMode.HUMAN_BRIEF)
    assert out.mode is RenderMode.HUMAN_BRIEF
    assert "# Brief: r1" in out.body
    assert "**Goal**" in out.body
    assert "## Constraints" in out.body
    assert "## Success criteria" in out.body


def test_render_model_contract_includes_tools_and_constraints() -> None:
    out = DualSpecWriter().render(_brief(), RenderMode.MODEL_CONTRACT)
    assert "<<<MODEL CONTRACT>>>" in out.body
    assert "GOAL:" in out.body
    assert "TOOLS ALLOWED" in out.body
    assert "echo" in out.body
    assert "MUST: p99 < 100ms" in out.body


def test_render_eval_contract_with_spec() -> None:
    spec = EvalSpec(
        brief_id="r1",
        metrics=(Metric(name="latency", unit="ms", threshold=100, lower_is_better=True),),
        stop_conditions=(StopCondition(condition_id="cost", metric_name="cost_usd", operator=">", value=5),),
    )
    out = DualSpecWriter().render(_brief(), RenderMode.EVAL_CONTRACT, eval_spec=spec)
    assert "## Metrics" in out.body
    assert "latency" in out.body
    assert "## Stop conditions" in out.body
    assert "cost" in out.body


def test_render_eval_contract_without_spec_falls_back_to_criteria() -> None:
    out = DualSpecWriter().render(_brief(), RenderMode.EVAL_CONTRACT)
    assert "Success criteria" in out.body
    assert "zero data loss" in out.body


def test_render_execution_manifest_yaml_like() -> None:
    out = DualSpecWriter().render(_brief(), RenderMode.EXECUTION_MANIFEST)
    assert "manifest_version: 1" in out.body
    assert "brief_id: r1" in out.body
    assert "tools_whitelist:" in out.body


def test_render_research_note_no_internal_jargon() -> None:
    out = DualSpecWriter().render(_brief(), RenderMode.RESEARCH_NOTE)
    # natural-language sentences only, no Brief id ledger jargon at the top
    assert "Brief `r1`" in out.body
    assert "manifest_version" not in out.body


def test_render_all_returns_all_modes() -> None:
    bundle = DualSpecWriter().render_all(_brief())
    assert set(bundle.keys()) == set(RenderMode)
    for mode, rendered in bundle.items():
        assert rendered.mode is mode
        assert rendered.body
