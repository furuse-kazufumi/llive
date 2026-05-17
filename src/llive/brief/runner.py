# SPDX-License-Identifier: Apache-2.0
"""BriefRunner — single-shot driver that wraps :class:`FullSenseLoop` for Briefs.

Pipeline ( ``submit(brief)`` ):

1. Translate :class:`Brief` → :class:`Stimulus` (content = goal + constraints).
2. Append ``brief_submitted`` ledger record (SIL axis).
3. Drive :meth:`FullSenseLoop.process` and record per-stage diagnostics.
4. If the resulting :class:`ActionPlan` is ``PROPOSE`` / ``INTERVENE`` *and*
   ``brief.approval_required`` is set, gate through the
   :class:`~llive.approval.bus.ApprovalBus` (Step 4 — wired in this module).
5. Execute whitelisted tool calls (Step 5 — see ``execute_tools=``).
6. Append ``outcome`` ledger record.
7. Return :class:`BriefResult`.

The runner deliberately keeps approval and tool execution **opt-in**: a
caller that just wants to feed a Brief into the loop (e.g. for benchmark
runs that compare loop quality across LLM backends) can omit them and get
deterministic behaviour without an ApprovalBus dependency.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Mapping

from llive.approval.bus import ApprovalBus, Verdict
from llive.brief.governance import GovernanceScorer, GovernanceVerdict
from llive.brief.grounding import BriefGrounder, GroundedBrief
from llive.brief.ledger import BriefLedger, default_ledger_path
from llive.brief.roles import MultiTrackSummary, RoleBasedMultiTrack
from llive.brief.types import Brief, BriefResult, BriefStatus, brief_to_dict
from llive.math.verifier import MathVerifier
from llive.fullsense.loop import FullSenseLoop, FullSenseResult
from llive.fullsense.types import ActionDecision, Stimulus

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]
"""A tool handler takes a JSON-shaped arg dict and returns a JSON-shaped result."""


def _stages_to_jsonable(stages: Mapping[str, Any]) -> dict[str, Any]:
    """Best-effort coerce FullSenseLoop stage dict into JSON-friendly form."""
    out: dict[str, Any] = {}
    for k, v in stages.items():
        if is_dataclass(v):
            out[k] = asdict(v)
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, Mapping):
            out[k] = {str(kk): _coerce_value(vv) for kk, vv in v.items()}
        elif isinstance(v, (list, tuple)):
            out[k] = [_coerce_value(item) for item in v]
        else:
            out[k] = str(v)
    return out


def _coerce_value(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, Mapping):
        return {str(kk): _coerce_value(vv) for kk, vv in v.items()}
    if isinstance(v, (list, tuple)):
        return [_coerce_value(item) for item in v]
    if is_dataclass(v):
        return asdict(v)
    return str(v)


def _brief_to_stimulus(brief: Brief, *, goal_override: str | None = None) -> Stimulus:
    """Encode the Brief as a Stimulus suitable for FullSenseLoop.

    Constraints are appended to the goal as a constraints block so they
    inform _inner_monologue without changing the Stimulus shape.
    ``goal_override`` lets the grounder substitute an augmented goal while
    leaving the original Brief object frozen and unmodified.
    """
    goal = goal_override if goal_override is not None else brief.goal
    if brief.constraints:
        constraints = "\n".join(f"- {c}" for c in brief.constraints)
        content = f"Goal:\n{goal}\n\nConstraints:\n{constraints}"
    else:
        content = f"Goal:\n{goal}"
    return Stimulus(
        content=content,
        source=brief.source,
        surprise=float(brief.priority),
        epistemic_type=brief.epistemic_type,
    )


def _decision_requires_approval(decision: ActionDecision) -> bool:
    return decision in (ActionDecision.PROPOSE, ActionDecision.INTERVENE)


class BriefRunner:
    """Single-shot driver — submit one Brief, get one :class:`BriefResult`.

    The runner does not own the loop or the approval bus; both are
    injected so tests can swap in fakes. Each call to :meth:`submit`
    opens (or reuses) a per-Brief ledger file.
    """

    def __init__(
        self,
        *,
        loop: FullSenseLoop,
        approval_bus: ApprovalBus | None = None,
        tools: Mapping[str, ToolHandler] | None = None,
        approver: str = "agent",
        grounder: BriefGrounder | None = None,
        governance_scorer: GovernanceScorer | None = None,
        perspectives: RoleBasedMultiTrack | None = None,
        math_verifier: MathVerifier | None = None,
    ) -> None:
        self._loop = loop
        self._approval_bus = approval_bus
        self._tools: dict[str, ToolHandler] = dict(tools or {})
        self._approver = approver
        # L1 grounding (TRIZ × RAD) is opt-in — leaves bench-only Brief flows
        # deterministic. When attached, every Brief is augmented before the
        # Stimulus is built and the citations are recorded in the ledger.
        self._grounder = grounder
        # COG-02 governance — also opt-in. When attached, every (Brief,
        # decision) pair is scored on 4 axes before the Approval Bus runs.
        # The scorer never blocks by itself; it surfaces recommend_block
        # which Approval Bus policy is free to honour or override.
        self._governance_scorer = governance_scorer
        # COG-04 + CREAT-04 multi-track perspectives — opt-in. When attached,
        # every (Brief, decision, plan) triple is observed through 10 lenses
        # (4 roles + 6 hats). Like governance, perspectives never block —
        # the summary is surfaced for downstream operators / UI.
        self._perspectives = perspectives
        # MATH-02 — shared MathVerifier whose ledger is rebound per-Brief in
        # submit() so every math_verified event lands in the Brief's own
        # audit trail. Callers reach the verifier via the ``math_verifier``
        # property after constructing the runner; they invoke check_* directly
        # (typically inside tool handlers or grounder extensions).
        self._math_verifier = math_verifier

    # -- public --------------------------------------------------------------

    def submit(self, brief: Brief) -> BriefResult:
        ledger = self._open_ledger(brief)

        ledger.append("brief_submitted", {"brief": brief_to_dict(brief)})

        grounded: GroundedBrief | None = None
        if self._grounder is not None:
            grounded = self._grounder.ground(brief)
            ledger.append(
                "grounding_applied",
                {
                    "triz": [
                        {
                            "principle_id": c.principle_id,
                            "name": c.name,
                            "trigger": c.trigger,
                        }
                        for c in grounded.triz
                    ],
                    "rad": [
                        {
                            "domain": r.domain,
                            "doc_path": r.doc_path,
                            "score": r.score,
                            "matched_terms": list(r.matched_terms),
                        }
                        for r in grounded.rad
                    ],
                    "augmented_goal_chars": len(grounded.augmented_goal),
                },
            )

        stim = _brief_to_stimulus(
            brief,
            goal_override=grounded.augmented_goal if grounded is not None else None,
        )
        ledger.append(
            "stimulus_built",
            {
                "stim_id": stim.stim_id,
                "source": stim.source,
                "surprise": stim.surprise,
                "epistemic_type": stim.epistemic_type.value
                if stim.epistemic_type is not None
                else None,
                "content_chars": len(stim.content),
                "grounded": grounded is not None,
            },
        )

        try:
            result: FullSenseResult = self._loop.process(stim)
        except Exception as exc:  # surface loop errors as terminal Brief state
            ledger.append("error", {"phase": "loop.process", "error": repr(exc)})
            return BriefResult(
                brief_id=brief.brief_id,
                status=BriefStatus.ERROR,
                rationale="loop.process raised",
                ledger_entries=ledger.entries_written,
                error=repr(exc),
            )

        ledger.append("loop_completed", {"stages": _stages_to_jsonable(result.stages)})
        ledger.append(
            "decision",
            {
                "decision": result.plan.decision.value,
                "rationale": result.plan.rationale,
                "ego_score": result.plan.ego_score,
                "altruism_score": result.plan.altruism_score,
            },
        )

        # COG-02 Governance scoring — runs *before* Approval Bus so the
        # Bus's policy can consult the scorer's recommend_block when
        # making its verdict.
        governance_verdict: GovernanceVerdict | None = None
        if self._governance_scorer is not None:
            governance_verdict = self._governance_scorer.score(brief, result.plan.decision)
            ledger.append(
                "governance_scored",
                {
                    "usefulness": governance_verdict.usefulness,
                    "feasibility": governance_verdict.feasibility,
                    "safety": governance_verdict.safety,
                    "traceability": governance_verdict.traceability,
                    "weighted_total": governance_verdict.weighted_total,
                    "recommend_block": governance_verdict.recommend_block,
                    "rationales": dict(governance_verdict.rationales),
                },
            )

        # COG-04 + CREAT-04 — multi-track perspectives. Runs after governance
        # so it can see the same plan/decision but does not gate the flow.
        perspective_summary: MultiTrackSummary | None = None
        perspectives_payload: list[dict[str, Any]] = []
        if self._perspectives is not None:
            perspective_summary = self._perspectives.observe(
                brief, result.plan.decision, result.plan
            )
            perspectives_payload = [
                {
                    "perspective_id": n.perspective_id,
                    "axis": n.axis,
                    "score": n.score,
                    "observation": n.observation,
                    "concerns": list(n.concerns),
                }
                for n in perspective_summary.notes
            ]
            ledger.append(
                "perspectives_observed",
                {
                    "notes": perspectives_payload,
                    "support_score": perspective_summary.support_score,
                    "risk_score": perspective_summary.risk_score,
                    "divergence": perspective_summary.divergence,
                    "critical_concerns": list(perspective_summary.critical_concerns),
                    "consensus_recommendation": perspective_summary.consensus_recommendation,
                },
            )

        # Step 4 — Approval Bus gate
        if (
            brief.approval_required
            and _decision_requires_approval(result.plan.decision)
        ):
            gated = self._gate_approval(brief, result, ledger, governance_verdict)
            if gated is not None:
                return gated

        # Step 5 — tool execution (whitelist enforced)
        tool_outputs: list[Mapping[str, Any]] = []
        artifacts: list[str] = []
        planned_tools = self._extract_planned_tools(result)
        if planned_tools:
            whitelist = set(brief.tools)
            for call in planned_tools:
                name = call.get("name", "")
                args = call.get("args", {}) if isinstance(call.get("args"), Mapping) else {}
                if name not in whitelist:
                    ledger.append(
                        "tool_rejected",
                        {"name": name, "reason": "not in brief.tools whitelist"},
                    )
                    continue
                if name not in self._tools:
                    ledger.append(
                        "tool_rejected",
                        {"name": name, "reason": "no handler registered"},
                    )
                    continue
                try:
                    output = self._tools[name](dict(args))
                except Exception as exc:
                    ledger.append(
                        "tool_failed",
                        {"name": name, "error": repr(exc)},
                    )
                    continue
                ledger.append(
                    "tool_invoked",
                    {"name": name, "args": dict(args), "output": _coerce_value(output)},
                )
                tool_outputs.append({"name": name, "output": output})
                if isinstance(output, Mapping):
                    arti = output.get("artifact")
                    if isinstance(arti, str):
                        artifacts.append(arti)

        status = (
            BriefStatus.SILENT
            if result.plan.decision is ActionDecision.SILENT
            else BriefStatus.COMPLETED
        )

        # COG-01 — derive (confidence, assumptions, missing_evidence) triple
        thought_conf = 0.5
        thought = result.plan.thought
        if thought is not None:
            try:
                thought_conf = float(thought.confidence)
            except (TypeError, ValueError):
                thought_conf = 0.5
        tool_call_count = sum(1 for _ in planned_tools) if planned_tools else 0
        tool_success_count = len(tool_outputs)
        tool_ratio = (
            tool_success_count / tool_call_count if tool_call_count > 0 else 1.0
        )
        # Combine thought confidence with tool success ratio. If no tools were
        # planned, confidence rests entirely on the loop's thought score.
        confidence = max(0.0, min(1.0, 0.5 * thought_conf + 0.5 * tool_ratio))

        assumptions_list: list[str] = []
        missing_list: list[str] = []
        if grounded is None:
            assumptions_list.append("no grounding applied (TRIZ/RAD citations absent)")
        else:
            if not grounded.triz:
                missing_list.append("no TRIZ principles surfaced by Brief text")
            if not grounded.rad:
                missing_list.append("no RAD corpus hits for Brief keywords")
        if tool_call_count > 0 and tool_success_count < tool_call_count:
            missing_list.append(
                f"{tool_call_count - tool_success_count} of {tool_call_count} tool calls failed"
            )
        if not brief.success_criteria:
            assumptions_list.append("no explicit success_criteria — judgement deferred to caller")

        perspective_summary_payload: dict[str, Any] | None = None
        if perspective_summary is not None:
            perspective_summary_payload = {
                "support_score": perspective_summary.support_score,
                "risk_score": perspective_summary.risk_score,
                "divergence": perspective_summary.divergence,
                "critical_concerns": list(perspective_summary.critical_concerns),
                "consensus_recommendation": perspective_summary.consensus_recommendation,
            }

        outcome = BriefResult(
            brief_id=brief.brief_id,
            status=status,
            rationale=result.plan.rationale,
            artifacts=tuple(artifacts),
            tool_outputs=tuple(tool_outputs),
            ledger_entries=ledger.entries_written + 1,  # +1 for the outcome row
            confidence=confidence,
            assumptions=tuple(assumptions_list),
            missing_evidence=tuple(missing_list),
            perspectives=tuple(perspectives_payload),
            perspective_summary=perspective_summary_payload,
        )
        ledger.append(
            "outcome",
            {
                "brief_id": outcome.brief_id,
                "status": outcome.status.value,
                "rationale": outcome.rationale,
                "artifacts": list(outcome.artifacts),
                "tool_outputs": [
                    {"name": t["name"], "output": _coerce_value(t["output"])}
                    for t in outcome.tool_outputs
                ],
                # COG-01 — uncertainty triple in the audit trail
                "confidence": outcome.confidence,
                "assumptions": list(outcome.assumptions),
                "missing_evidence": list(outcome.missing_evidence),
                # COG-04 + CREAT-04 — perspectives reproduced in outcome row
                "perspectives": list(outcome.perspectives),
                "perspective_summary": dict(outcome.perspective_summary)
                if outcome.perspective_summary is not None
                else None,
            },
        )
        return outcome

    # -- internals -----------------------------------------------------------

    def _open_ledger(self, brief: Brief) -> BriefLedger:
        path = brief.ledger_path or default_ledger_path(brief.brief_id)
        return BriefLedger(path)

    def _gate_approval(
        self,
        brief: Brief,
        result: FullSenseResult,
        ledger: BriefLedger,
        governance_verdict: GovernanceVerdict | None = None,
    ) -> BriefResult | None:
        """Returns a terminal BriefResult if the gate blocks; ``None`` to proceed.

        With no ApprovalBus configured, ``approval_required=True`` Briefs
        cannot proceed past PROPOSE / INTERVENE — they end as
        AWAITING_APPROVAL so the operator can wire a bus and resume.

        COG-02: when a Governance scorer recommends a block, the Approval
        request payload includes the scoring rationale so the Bus's policy
        can honour it.
        """
        if self._approval_bus is None:
            ledger.append(
                "approval_required_no_bus",
                {"decision": result.plan.decision.value},
            )
            return BriefResult(
                brief_id=brief.brief_id,
                status=BriefStatus.AWAITING_APPROVAL,
                rationale=(
                    "decision requires approval but no ApprovalBus configured"
                ),
                ledger_entries=ledger.entries_written + 1,
            )

        payload: dict[str, object] = {
            "brief_id": brief.brief_id,
            "goal": brief.goal,
            "rationale": result.plan.rationale,
        }
        if governance_verdict is not None:
            payload["governance_total"] = governance_verdict.weighted_total
            payload["governance_recommend_block"] = governance_verdict.recommend_block
            payload["governance_safety"] = governance_verdict.safety
        req = self._approval_bus.request(
            action=f"brief:{result.plan.decision.value}",
            payload=payload,
            principal=self._approver,
        )
        ledger.append(
            "approval_requested",
            {"request_id": req.request_id, "action": req.action},
        )
        verdict = self._approval_bus.current_verdict(req.request_id)
        ledger.append(
            "approval_resolved",
            {"request_id": req.request_id, "verdict": verdict.value},
        )
        if verdict is Verdict.APPROVED:
            return None  # proceed to tool execution
        # DENIED / REVOKED — both terminate the Brief without tool execution.
        return BriefResult(
            brief_id=brief.brief_id,
            status=BriefStatus.REJECTED,
            rationale=f"approval verdict: {verdict.value}",
            ledger_entries=ledger.entries_written + 1,
        )

    @staticmethod
    def _extract_planned_tools(result: FullSenseResult) -> list[dict[str, Any]]:
        """Pull a tool-call list from the loop result, if the plan provided one.

        The MVP loop doesn't emit tool calls yet; the runner accepts them
        either through ``result.stages['tools']`` (where downstream loop
        variants attach LLM-generated calls) or through a future
        ``ActionPlan.tools`` attribute. Empty list = nothing to execute.
        """
        plan = result.plan
        tools_attr = getattr(plan, "tools", None)
        if isinstance(tools_attr, (list, tuple)):
            return [t for t in tools_attr if isinstance(t, Mapping)]
        stage_tools = result.stages.get("tools") if isinstance(result.stages, Mapping) else None
        if isinstance(stage_tools, (list, tuple)):
            return [t for t in stage_tools if isinstance(t, Mapping)]
        return []
