# SPDX-License-Identifier: Apache-2.0
"""COG-FX 9-factor end-to-end smoke test.

1 つの Brief を grounder + governance + perspectives + approval bus + tools の
**9 因子全部 enabled** で走らせ、ledger に各因子の証拠が出揃うことを一括検証。
因子 10 (現実接続) は Phase 4 (llmesh sensor bridge) 待ちのため対象外。

回帰検出ハーネス:

* 因子のどれかが ledger に書き込まれなくなった = リグレッション
* perspectives が 10 件揃わない / outcome に triple がない も同様にトリップ
* tool_invoked が消えた = whitelist や mock loop の契約破壊

CI で軽量に回せるよう **mock loop** を使う (実 LLM/Ollama 起動は不要)。
実 LLM での挙動は別途 benchmark スクリプトで確認するもの。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llive.approval.bus import ApprovalBus, ApprovalRequest, Verdict
from llive.brief import (
    Brief,
    BriefGrounder,
    BriefLedger,
    BriefRunner,
    BriefStatus,
    GovernanceScorer,
    GroundingConfig,
    HatPerspective,
    RoleBasedMultiTrack,
    RolePerspective,
)
from llive.fullsense.loop import FullSenseResult
from llive.fullsense.types import ActionDecision, ActionPlan, Stimulus, Thought
from llive.math import MathVerifier
from llive.oka import (
    CoreEssenceExtractor,
    ReflectiveNotebook,
    StrategyFamily,
    StrategyOrchestrator,
)


# ---------------------------------------------------------------------------
# Fixtures: deterministic mocks that exercise every factor
# ---------------------------------------------------------------------------


class _AutoApprovePolicy:
    """approval_bus 用 — 9 因子のうち「整合 (因子 7)」を全自動で走らせる。

    本物の human-in-the-loop は CLI 側で動作確認するため、CI ではこの policy で
    auto-approve することで approval_resolved event を ledger に確実に流す。
    """

    def evaluate(self, request: ApprovalRequest) -> Verdict | None:
        return Verdict.APPROVED


class _MockLoop:
    """全因子をトリップさせるための最小 loop.

    * decision = PROPOSE → approval bus を起動 (因子 7)
    * thought.triz_principles 付き → green-hat lens でも反映 (因子 6 探索)
    * stages['tools'] に 1 件 → tool_invoked が出る (因子 4 自己拡張)
    """

    def process(self, stim: Stimulus) -> FullSenseResult:
        plan = ActionPlan(
            decision=ActionDecision.PROPOSE,
            rationale="propose deterministic e2e action with triz principles for the factor harness",
            thought=Thought(text="t", confidence=0.85, triz_principles=[1, 15, 35]),
        )
        return FullSenseResult(
            stim=stim,
            plan=plan,
            stages={"tools": [{"name": "echo", "args": {"x": 1}}]},
        )


class _StubPrinciple:
    """BriefGrounder 用 — Principle Protocol の最小実装。"""

    def __init__(self, pid: int, name: str, examples: tuple[str, ...] = ()) -> None:
        self.id = pid
        self.name = name
        self.description = ""
        self.examples = list(examples)


# ---------------------------------------------------------------------------
# E2E test — single Brief, all 9 factors
# ---------------------------------------------------------------------------


def test_full_9_factor_brief_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """1 つの Brief 実行で 9 因子全部の証拠が ledger に出ることを確認。"""
    monkeypatch.setenv("LLIVE_DISABLE_RAD_GROUNDING", "1")

    # ---- inject 9-factor wiring ------------------------------------------
    bus = ApprovalBus(policy=_AutoApprovePolicy())
    principles: dict[int, _StubPrinciple] = {
        1: _StubPrinciple(1, "Segmentation", ("分割",)),
        15: _StubPrinciple(15, "Dynamics", ("動的",)),
        35: _StubPrinciple(35, "Parameter changes", ("パラメータ変更",)),
    }
    grounder = BriefGrounder(principles=principles, config=GroundingConfig(max_triz=3))
    governance = GovernanceScorer()
    perspectives = RoleBasedMultiTrack()

    def echo_tool(args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "args": args, "artifact": "e2e-artifact"}

    runner = BriefRunner(
        loop=_MockLoop(),  # type: ignore[arg-type]
        approval_bus=bus,
        tools={"echo": echo_tool},
        grounder=grounder,
        governance_scorer=governance,
        perspectives=perspectives,
    )

    brief = Brief(
        brief_id="cog-fx-e2e",
        goal="trade-off between static and dynamic structures via segmentation",
        constraints=("preserve at-least-once semantics", "p99 < 100ms"),
        tools=("echo",),
        success_criteria=("ledger contains all 9 factor events",),
        approval_required=True,
        ledger_path=tmp_path / "9fac.jsonl",
    )

    result = runner.submit(brief)

    # Brief succeeded end-to-end (didn't get rejected, errored, or pause)
    assert result.status is BriefStatus.COMPLETED, f"got {result.status}, rationale={result.rationale}"

    events = list(BriefLedger(brief.ledger_path).read())  # type: ignore[arg-type]
    event_names = [e.event for e in events]

    # ---- 因子 1 構造化 — constraints が stimulus に反映 -------------------
    stim_evt = next(e for e in events if e.event == "stimulus_built")
    assert stim_evt.payload["content_chars"] > len(brief.goal), (
        "stimulus must include constraints block (factor 1: structure)"
    )

    # ---- 因子 2 再構成 — TRIZ grounding (RAD disabled in this test) -----
    assert "grounding_applied" in event_names, "factor 2 (recomposition) missing"
    grounding_evt = next(e for e in events if e.event == "grounding_applied")
    assert grounding_evt.payload["triz"], "TRIZ citations missing — segmentation/dynamics keywords should match"

    # ---- 因子 3 閉ループ — loop → decision → outcome の順序 --------------
    for required in ("loop_completed", "decision", "outcome"):
        assert required in event_names, f"factor 3 (closed loop) — missing {required}"
    assert event_names.index("loop_completed") < event_names.index("outcome")

    # ---- 因子 4 自己拡張 — tool_invoked --------------------------------
    assert "tool_invoked" in event_names, "factor 4 (self-extension) — tool_invoked missing"
    tool_evt = next(e for e in events if e.event == "tool_invoked")
    assert tool_evt.payload["name"] == "echo"

    # ---- 因子 5 不確実性 — COG-01 triple in outcome ---------------------
    outcome_evt = next(e for e in events if e.event == "outcome")
    payload = outcome_evt.payload
    for key in ("confidence", "assumptions", "missing_evidence"):
        assert key in payload, f"factor 5 (uncertainty) — outcome missing {key}"
    assert 0.0 <= payload["confidence"] <= 1.0

    # ---- 因子 6 探索 — green hat picks up TRIZ principles ---------------
    green = next(
        p for p in payload["perspectives"]
        if p["perspective_id"] == HatPerspective.GREEN.value
    )
    assert green["score"] >= 0.5, "factor 6 (exploration) — green-hat should reward TRIZ principles"

    # ---- 因子 7 整合 — governance + approval cycle ---------------------
    assert "governance_scored" in event_names, "factor 7 (alignment) — governance missing"
    gov_evt = next(e for e in events if e.event == "governance_scored")
    for axis in ("usefulness", "feasibility", "safety", "traceability"):
        assert axis in gov_evt.payload
    assert "approval_requested" in event_names
    assert "approval_resolved" in event_names
    appr_evt = next(e for e in events if e.event == "approval_resolved")
    assert appr_evt.payload["verdict"] == Verdict.APPROVED.value

    # ---- 因子 8 来歴 — TraceGraph 3 layers all populated ---------------
    tg = BriefLedger(brief.ledger_path).trace_graph()  # type: ignore[arg-type]
    assert tg.evidence_chain, "factor 8 (provenance) — evidence chain empty"
    assert tg.tool_chain, "factor 8 — tool chain empty"
    assert tg.decision_chain, "factor 8 — decision chain empty"
    # decision_chain should reference all of: decision / approval / governance / outcome
    decision_events = {d["event"] for d in tg.decision_chain}
    assert {"decision", "approval_resolved", "governance_scored", "outcome"} <= decision_events

    # ---- 因子 9 多視点 — 10 perspectives observed ----------------------
    assert "perspectives_observed" in event_names, "factor 9 (multi-perspective) missing"
    persp_evt = next(e for e in events if e.event == "perspectives_observed")
    assert len(persp_evt.payload["notes"]) == 10
    summary = payload["perspective_summary"]
    assert summary is not None
    assert summary["consensus_recommendation"] in {"proceed", "review", "hold"}

    # ---- BriefResult mirrors the ledger picture ------------------------
    assert result.artifacts == ("e2e-artifact",)
    assert len(result.perspectives) == 10
    assert result.perspective_summary is not None


def test_full_11_factor_brief_with_oka_and_math(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """9 因子 + OKA (essence/notebook/strategy) + MATH-02 verifier = 11 因子 E2E.

    回帰検出ハーネス: COG-FX 9 + OKA-01/02/04 + MATH-02 が同一 Brief 内で
    すべて trip し、ledger に証拠を残すことを確認する。
    """
    monkeypatch.setenv("LLIVE_DISABLE_RAD_GROUNDING", "1")

    bus = ApprovalBus(policy=_AutoApprovePolicy())
    principles = {1: _StubPrinciple(1, "Segmentation", ("分割",))}
    grounder = BriefGrounder(principles=principles, config=GroundingConfig(max_triz=2))
    governance = GovernanceScorer()
    perspectives = RoleBasedMultiTrack()
    extractor = CoreEssenceExtractor()
    notebook = ReflectiveNotebook(tmp_path / "nb.jsonl")
    orch = StrategyOrchestrator()
    orch.register(StrategyFamily(name="symbolic"))
    orch.register(StrategyFamily(name="geometric"))
    orch.activate("symbolic")
    verifier = MathVerifier()

    runner = BriefRunner(
        loop=_MockLoop(),  # type: ignore[arg-type]
        approval_bus=bus,
        tools={"echo": lambda a: {"ok": True, "args": a, "artifact": "11f"}},
        grounder=grounder,
        governance_scorer=governance,
        perspectives=perspectives,
        math_verifier=verifier,
        essence_extractor=extractor,
        notebook=notebook,
        strategy_orchestrator=orch,
    )
    brief = Brief(
        brief_id="cog-fx-11",
        goal="trade-off between static and dynamic structures via segmentation",
        constraints=("p99 < 100ms",),
        tools=("echo",),
        success_criteria=("11-factor ledger coverage",),
        approval_required=True,
        ledger_path=tmp_path / "11.jsonl",
    )
    result = runner.submit(brief)
    # exercise MATH-02 within the Brief (verifier's ledger is auto-bound)
    verifier.check_equivalence("(x+1)**2", "x**2 + 2*x + 1")
    # exercise OKA-04 manually (insight) on top of the Brief
    notebook.append(brief_id=brief.brief_id, kind="insight", body="dynamic vs static is the key tension")
    # exercise OKA-03 — flat progress should make should_switch() true → switch
    for _ in range(5):
        orch.push_progress(0.05)
    orch.switch_to("geometric", reason="symbolic stalled in 11-factor harness")

    assert result.status is BriefStatus.COMPLETED, f"status={result.status} rationale={result.rationale}"
    events = list(BriefLedger(brief.ledger_path).read())  # type: ignore[arg-type]
    names = {e.event for e in events}

    # 9 COG-FX factors (subset checked here; the dedicated 9-factor test
    # remains the authoritative coverage check)
    for needed in (
        "stimulus_built", "grounding_applied", "loop_completed", "decision",
        "tool_invoked", "outcome", "perspectives_observed", "governance_scored",
        "approval_resolved",
    ):
        assert needed in names, f"missing COG-FX event {needed!r}"

    # OKA-01/02 — essence
    assert "oka_essence_extracted" in names
    assert result.essence is not None
    # OKA-04 — notebook
    assert "oka_notebook_appended" in names
    # OKA-03 — strategy switch
    assert "oka_strategy_switched" in names
    # MATH-02 — verifier
    assert "math_verified" in names

    tg = BriefLedger(brief.ledger_path).trace_graph()  # type: ignore[arg-type]
    evidence_kinds = {e.get("kind") for e in tg.evidence_chain}
    assert {"oka_essence", "oka_note", "math"} <= evidence_kinds
    decision_events = {d["event"] for d in tg.decision_chain}
    assert "oka_strategy_switched" in decision_events


def test_full_9_factor_brief_records_role_axis_lenses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity: 4 roles + 6 hats が perspective_id で漏れなく書き出される。"""
    monkeypatch.setenv("LLIVE_DISABLE_RAD_GROUNDING", "1")

    runner = BriefRunner(
        loop=_MockLoop(),  # type: ignore[arg-type]
        approval_bus=ApprovalBus(policy=_AutoApprovePolicy()),
        tools={"echo": lambda a: {"ok": True}},
        grounder=BriefGrounder(principles={1: _StubPrinciple(1, "Segmentation")}),
        governance_scorer=GovernanceScorer(),
        perspectives=RoleBasedMultiTrack(),
    )
    brief = Brief(
        brief_id="cog-fx-roles",
        goal="segmentation analysis",
        constraints=("c1",),
        tools=("echo",),
        success_criteria=("ok",),
        approval_required=True,
        ledger_path=tmp_path / "roles.jsonl",
    )
    result = runner.submit(brief)
    assert result.status is BriefStatus.COMPLETED
    ids = {p["perspective_id"] for p in result.perspectives}
    expected = {r.value for r in RolePerspective} | {h.value for h in HatPerspective}
    assert ids == expected
