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
