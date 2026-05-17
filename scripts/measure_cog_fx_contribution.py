#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""COG-FX 9 因子の寄与率測定 (ablation study).

各因子を ON/OFF で切り替えて 1 つの Brief を走らせ、ledger event の出現有無と
outcome 値の差分を測ることで「どの因子がどれだけ outcome に効いているか」を
数値化する。結果は JSON + Markdown 両方で出力する。

設計:

* mock loop と auto-approve policy を使い、決定論的に 1 Brief を完走させる
* baseline = 9 因子全部 ON
* 各 ablation = 1 因子を OFF にして残り 8 因子を ON
* 比較項目:
    - 該当因子の代表 event (e.g. governance_scored, perspectives_observed) が
      消えること = 因子が確かに切れた証拠
    - outcome 値 (confidence, perspective_summary.support_score 等) の差分

Usage:

    py -3.11 scripts/measure_cog_fx_contribution.py
    # → docs/benchmarks/2026-05-17-cog-fx-contribution.{json,md}

CI ではなく開発者が手動で走らせる「動作確認 + ablation harness」位置づけ。
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Disable RAD bootstrap for measurement determinism — TRIZ-only grounding is enough.
os.environ.setdefault("LLIVE_DISABLE_RAD_GROUNDING", "1")

from llive.approval.bus import ApprovalBus, ApprovalRequest, Verdict
from llive.brief import (
    Brief,
    BriefGrounder,
    BriefLedger,
    BriefRunner,
    BriefStatus,
    GovernanceScorer,
    GroundingConfig,
    RoleBasedMultiTrack,
)
from llive.fullsense.loop import FullSenseResult
from llive.fullsense.types import ActionDecision, ActionPlan, Stimulus, Thought


# ---- Mocks (mirror tests/component/test_cog_fx_e2e.py) -------------------


class _AutoApprovePolicy:
    def evaluate(self, request: ApprovalRequest) -> Verdict | None:
        return Verdict.APPROVED


class _MockLoop:
    def process(self, stim: Stimulus) -> FullSenseResult:
        plan = ActionPlan(
            decision=ActionDecision.PROPOSE,
            rationale="propose a deterministic action with triz principles for the ablation matrix",
            thought=Thought(text="t", confidence=0.85, triz_principles=[1, 15, 35]),
        )
        return FullSenseResult(
            stim=stim,
            plan=plan,
            stages={"tools": [{"name": "echo", "args": {"x": 1}}]},
        )


class _StubPrinciple:
    def __init__(self, pid: int, name: str) -> None:
        self.id = pid
        self.name = name
        self.description = ""
        self.examples: list[str] = []


def _echo_tool(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "args": args, "artifact": "ablation-artifact"}


# ---- Factor matrix --------------------------------------------------------


@dataclass(frozen=True)
class FactorConfig:
    """One row in the ablation matrix.

    Each factor is a switch toggled ON/OFF. The 9 factors map to runner
    components and Brief fields per the COG-FX taxonomy.
    """

    structure: bool = True       # 1: constraints in Brief
    recomposition: bool = True   # 2: grounder (TRIZ + RAD-disabled here)
    closed_loop: bool = True     # 3: always on (cannot ablate — loop is mandatory)
    self_extension: bool = True  # 4: tools + tool handlers attached
    uncertainty: bool = True     # 5: COG-01 derives triple automatically — always on
    exploration: bool = True     # 6: TRIZ principles in mock loop's Thought
    alignment: bool = True       # 7: governance + approval_bus
    provenance: bool = True      # 8: ledger always on — always
    multi_perspective: bool = True  # 9: RoleBasedMultiTrack

    def name(self) -> str:
        if all(getattr(self, f.name) for f in self.__dataclass_fields__.values()):
            return "baseline (all-on)"
        off = [f.name for f in self.__dataclass_fields__.values() if not getattr(self, f.name)]
        return f"off:{','.join(off)}"


@dataclass
class FactorOutcome:
    """Recorded outcome of one ablation run."""

    config_name: str
    status: str
    confidence: float
    perspective_consensus: str | None = None
    perspective_support: float | None = None
    perspective_risk: float | None = None
    governance_total: float | None = None
    event_counts: dict[str, int] = field(default_factory=dict)
    factor_event_present: dict[str, bool] = field(default_factory=dict)


# Map factor name → list of ledger events that *should* appear when that
# factor is ON. Used to verify ablation actually severs the factor.
_FACTOR_EVENTS: dict[str, tuple[str, ...]] = {
    "structure": ("stimulus_built",),  # always present, but content_chars changes
    "recomposition": ("grounding_applied",),
    "closed_loop": ("loop_completed", "decision", "outcome"),
    "self_extension": ("tool_invoked",),
    "uncertainty": ("outcome",),  # triple always inside outcome
    "exploration": ("perspectives_observed",),  # green-hat reads TRIZ from Thought
    "alignment": ("governance_scored", "approval_resolved"),
    "provenance": ("outcome",),  # ledger entries always written
    "multi_perspective": ("perspectives_observed",),
}


def _build_runner(cfg: FactorConfig) -> BriefRunner:
    principles = {
        1: _StubPrinciple(1, "Segmentation"),
        15: _StubPrinciple(15, "Dynamics"),
        35: _StubPrinciple(35, "Parameter changes"),
    }
    grounder = BriefGrounder(principles=principles, config=GroundingConfig(max_triz=3)) \
        if cfg.recomposition else None
    governance = GovernanceScorer() if cfg.alignment else None
    perspectives = RoleBasedMultiTrack() if cfg.multi_perspective else None
    bus = ApprovalBus(policy=_AutoApprovePolicy()) if cfg.alignment else None
    tools = {"echo": _echo_tool} if cfg.self_extension else {}
    return BriefRunner(
        loop=_MockLoop(),  # type: ignore[arg-type]
        approval_bus=bus,
        tools=tools,
        grounder=grounder,
        governance_scorer=governance,
        perspectives=perspectives,
    )


def _build_brief(cfg: FactorConfig, brief_id: str, ledger_path: Path) -> Brief:
    constraints = ("preserve at-least-once semantics", "p99 < 100ms") if cfg.structure else ()
    tools = ("echo",) if cfg.self_extension else ()
    return Brief(
        brief_id=brief_id,
        goal="trade-off between static and dynamic structures via segmentation",
        constraints=constraints,
        tools=tools,
        success_criteria=("ledger contains all factor events",),
        approval_required=cfg.alignment,
        ledger_path=ledger_path,
    )


def _run_one(cfg: FactorConfig, brief_id: str, tmpdir: Path) -> FactorOutcome:
    ledger_path = tmpdir / f"{brief_id}.jsonl"
    runner = _build_runner(cfg)
    brief = _build_brief(cfg, brief_id, ledger_path)
    result = runner.submit(brief)

    events = list(BriefLedger(ledger_path).read())
    event_counts: dict[str, int] = {}
    for e in events:
        event_counts[e.event] = event_counts.get(e.event, 0) + 1

    factor_event_present: dict[str, bool] = {}
    for factor, evts in _FACTOR_EVENTS.items():
        factor_event_present[factor] = all(ev in event_counts for ev in evts)

    persp_support = persp_risk = None
    persp_consensus = None
    if result.perspective_summary is not None:
        persp_support = result.perspective_summary.get("support_score")
        persp_risk = result.perspective_summary.get("risk_score")
        persp_consensus = result.perspective_summary.get("consensus_recommendation")

    governance_total = None
    for e in events:
        if e.event == "governance_scored":
            governance_total = e.payload.get("weighted_total")

    return FactorOutcome(
        config_name=cfg.name(),
        status=result.status.value,
        confidence=result.confidence,
        perspective_consensus=persp_consensus,
        perspective_support=persp_support,
        perspective_risk=persp_risk,
        governance_total=governance_total,
        event_counts=event_counts,
        factor_event_present=factor_event_present,
    )


def _delta_metrics(baseline: FactorOutcome, ablation: FactorOutcome) -> dict[str, Any]:
    def _d(b: float | None, a: float | None) -> float | None:
        if b is None or a is None:
            return None
        return round(a - b, 4)

    return {
        "delta_confidence": _d(baseline.confidence, ablation.confidence),
        "delta_perspective_support": _d(baseline.perspective_support, ablation.perspective_support),
        "delta_perspective_risk": _d(baseline.perspective_risk, ablation.perspective_risk),
        "delta_governance_total": _d(baseline.governance_total, ablation.governance_total),
        "consensus_changed": (
            baseline.perspective_consensus != ablation.perspective_consensus
        ),
        "events_lost": sorted(
            set(baseline.event_counts) - set(ablation.event_counts)
        ),
        "events_gained": sorted(
            set(ablation.event_counts) - set(baseline.event_counts)
        ),
    }


def measure() -> dict[str, Any]:
    """Run the full ablation matrix and return a structured report."""
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        baseline_cfg = FactorConfig()
        baseline = _run_one(baseline_cfg, "ablation-baseline", tmpdir)

        ablations: dict[str, dict[str, Any]] = {}
        # Skip factors that are structurally mandatory (closed_loop / provenance /
        # uncertainty) — they cannot be ablated without breaking the harness.
        ablatable = ["structure", "recomposition", "self_extension", "exploration", "alignment", "multi_perspective"]
        for factor in ablatable:
            kw = {factor: False}
            cfg = FactorConfig(**kw)  # type: ignore[arg-type]
            out = _run_one(cfg, f"ablation-{factor}", tmpdir)
            ablations[factor] = {
                "outcome": out.__dict__,
                "delta_from_baseline": _delta_metrics(baseline, out),
            }

    return {
        "baseline": baseline.__dict__,
        "ablations": ablations,
        "factor_event_map": {k: list(v) for k, v in _FACTOR_EVENTS.items()},
        "notes": (
            "closed_loop / uncertainty / provenance are not ablated — they are "
            "structural invariants of the Brief pipeline. The other 6 factors are "
            "toggled individually and compared against the 9-factor baseline."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    base = report["baseline"]
    lines: list[str] = []
    lines.append("# COG-FX 9 因子 寄与率レポート (ablation)")
    lines.append("")
    lines.append(f"- baseline status: `{base['status']}`")
    lines.append(f"- baseline confidence: **{base['confidence']:.3f}**")
    if base["perspective_support"] is not None:
        lines.append(
            f"- baseline perspectives: support=**{base['perspective_support']:.3f}** "
            f"risk=**{base['perspective_risk']:.3f}** "
            f"consensus=`{base['perspective_consensus']}`"
        )
    if base["governance_total"] is not None:
        lines.append(f"- baseline governance_total: **{base['governance_total']:.3f}**")
    lines.append("")
    lines.append("## Factor presence check (baseline)")
    lines.append("")
    lines.append("| Factor | Required events | Present? |")
    lines.append("|---|---|---|")
    for factor, evts in report["factor_event_map"].items():
        present = base["factor_event_present"].get(factor, False)
        mark = "✓" if present else "✗"
        lines.append(f"| {factor} | `{', '.join(evts)}` | {mark} |")
    lines.append("")
    lines.append("## Ablation deltas (baseline − factor OFF)")
    lines.append("")
    lines.append(
        "| Factor OFF | Δconfidence | Δsupport | Δrisk | Δgovernance | consensus changed | events lost |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for factor, data in report["ablations"].items():
        d = data["delta_from_baseline"]
        events_lost = d["events_lost"]
        evt_str = ", ".join(f"`{e}`" for e in events_lost) if events_lost else "—"
        lines.append(
            f"| `{factor}` | {d['delta_confidence']} | {d['delta_perspective_support']} | "
            f"{d['delta_perspective_risk']} | {d['delta_governance_total']} | "
            f"{'yes' if d['consensus_changed'] else 'no'} | {evt_str} |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(report["notes"])
    return "\n".join(lines) + "\n"


def main() -> None:
    import sys
    # Windows console defaults to cp932 which can't render the ✓ marks in the
    # Markdown summary. Reconfigure to utf-8 if available; harmless on POSIX.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    report = measure()
    out_dir = Path("docs/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "2026-05-17-cog-fx-contribution.json"
    md_path = out_dir / "2026-05-17-cog-fx-contribution.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print("\n--- summary ---")
    try:
        print(render_markdown(report))
    except UnicodeEncodeError:
        # final fallback — strip the check marks
        print(render_markdown(report).encode("ascii", errors="replace").decode("ascii"))


if __name__ == "__main__":
    main()
