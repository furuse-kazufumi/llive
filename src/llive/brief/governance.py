# SPDX-License-Identifier: Apache-2.0
"""COG-02 Governance Scoring Layer.

Approval Bus の前段に挿入する 4 軸スコアラ。LLM 出力を usefulness だけで
評価せず、feasibility / safety / traceability の 4 軸で再採点することで
「派手だが運用不能な案」を抑制する (ユーザー観察より)。

設計:

* 4 軸スコア (各 0.0〜1.0) を独立に算出 → 重み付け平均で総合スコア
* 各軸はルールベースの heuristics で初期実装。後段で LLM-as-judge や
  Bayesian scoring に置換可能 (Strategy パターン)
* スコア結果は :class:`GovernanceVerdict` として ledger に固定記録 →
  COG-08 来歴因子と接続
* 閾値以下は ``recommend_block=True`` を立てて Approval Bus に伝える。
  最終判断は Approval Bus が行う (Governance は **scoring**、Approval は
  **gating** という責務分離)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from llive.brief.types import Brief
from llive.fullsense.types import ActionDecision


# Default weights — adjustable via GovernanceConfig.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "usefulness": 0.30,
    "feasibility": 0.25,
    "safety": 0.30,
    "traceability": 0.15,
}


@dataclass(frozen=True)
class GovernanceConfig:
    """Knobs for :class:`GovernanceScorer`."""

    weights: Mapping[str, float] = field(default_factory=lambda: dict(_DEFAULT_WEIGHTS))
    block_threshold: float = 0.4
    safety_floor: float = 0.5  # any case with safety < safety_floor is auto-block


@dataclass(frozen=True)
class GovernanceVerdict:
    """Scoring result for one (Brief, decision) pair.

    All four axis scores are in [0.0, 1.0]. The ``rationale`` per axis
    explains *why* the heuristic produced the score, so the ledger keeps
    a human-readable trace.
    """

    usefulness: float
    feasibility: float
    safety: float
    traceability: float
    weighted_total: float
    recommend_block: bool
    rationales: Mapping[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

# Safety: tokens that often indicate dangerous actions if executed.
_DANGEROUS_TOKENS: tuple[str, ...] = (
    "rm -rf", "sudo", "DELETE FROM", "DROP TABLE", "format c:", "shutdown",
    "kill -9", "chmod 777", "eval(", "exec(", "__import__",
    "gpg --delete", "rm /", "> /dev/sda",
)


def _score_usefulness(brief: Brief, decision: ActionDecision) -> tuple[float, str]:
    """How likely is the proposed action to actually help the brief?

    Heuristic: SILENT decisions help nothing (0.1). NOTE decisions help
    audit/episodic capture (0.5). PROPOSE / INTERVENE actively try to
    move the world toward the goal (0.7 - 0.85). Bonus if Brief carried
    explicit success_criteria.
    """
    base = {
        ActionDecision.SILENT: 0.1,
        ActionDecision.NOTE: 0.5,
        ActionDecision.PROPOSE: 0.75,
        ActionDecision.INTERVENE: 0.85,
    }.get(decision, 0.4)
    if brief.success_criteria:
        base = min(1.0, base + 0.1)
    return base, f"decision={decision.value}, criteria={'yes' if brief.success_criteria else 'no'}"


def _score_feasibility(brief: Brief, decision: ActionDecision) -> tuple[float, str]:
    """How realistic is the action given the Brief's declared resources?

    Heuristic: Briefs with no declared tools but PROPOSE/INTERVENE
    decisions lose points (can't execute anything). Briefs with rich
    constraints + tools gain points.
    """
    score = 0.6
    if decision in (ActionDecision.PROPOSE, ActionDecision.INTERVENE) and not brief.tools:
        score -= 0.3
        note = "action requested but no tools whitelisted"
    elif brief.tools and brief.constraints:
        score = 0.8
        note = "tools + constraints declared"
    else:
        note = "baseline feasibility"
    return max(0.0, min(1.0, score)), note


def _score_safety(brief: Brief, decision: ActionDecision) -> tuple[float, str]:
    """Rule-based safety check.

    Heuristic: scan goal + constraints for dangerous tokens. Penalise
    INTERVENE without approval_required.
    """
    text = (brief.goal + "\n" + "\n".join(brief.constraints)).lower()
    dangerous_hits = [t for t in _DANGEROUS_TOKENS if t.lower() in text]
    score = 0.9
    notes: list[str] = []
    if dangerous_hits:
        score -= 0.6
        notes.append(f"dangerous tokens: {dangerous_hits}")
    if decision is ActionDecision.INTERVENE and not brief.approval_required:
        score -= 0.4
        notes.append("INTERVENE without approval gate")
    return max(0.0, min(1.0, score)), "; ".join(notes) if notes else "no red flags"


def _score_traceability(brief: Brief, decision: ActionDecision) -> tuple[float, str]:
    """How auditable is the action's outcome?

    Heuristic: ledger_path explicit + tools whitelisted + success_criteria
    each contribute. Without any of them the trail is shallow.
    """
    score = 0.4
    notes: list[str] = []
    if brief.ledger_path is not None:
        score += 0.2
        notes.append("explicit ledger_path")
    if brief.tools:
        score += 0.15
        notes.append("tool whitelist set")
    if brief.success_criteria:
        score += 0.2
        notes.append("success_criteria set")
    return min(1.0, score), "; ".join(notes) if notes else "minimal traceability"


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class GovernanceScorer:
    """Compute a 4-axis :class:`GovernanceVerdict` for a (Brief, decision) pair.

    The scorer never blocks an action by itself — it surfaces a recommendation
    that the Approval Bus can choose to honour or override. This keeps the
    responsibility split clean: scoring vs gating.
    """

    def __init__(self, config: GovernanceConfig | None = None) -> None:
        self.config = config or GovernanceConfig()

    def score(self, brief: Brief, decision: ActionDecision) -> GovernanceVerdict:
        u, ur = _score_usefulness(brief, decision)
        f, fr = _score_feasibility(brief, decision)
        s, sr = _score_safety(brief, decision)
        t, tr = _score_traceability(brief, decision)
        w = self.config.weights
        total = (
            w.get("usefulness", 0.0) * u
            + w.get("feasibility", 0.0) * f
            + w.get("safety", 0.0) * s
            + w.get("traceability", 0.0) * t
        )
        block = total < self.config.block_threshold or s < self.config.safety_floor
        return GovernanceVerdict(
            usefulness=u,
            feasibility=f,
            safety=s,
            traceability=t,
            weighted_total=total,
            recommend_block=block,
            rationales={
                "usefulness": ur,
                "feasibility": fr,
                "safety": sr,
                "traceability": tr,
            },
        )
