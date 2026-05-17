# SPDX-License-Identifier: Apache-2.0
"""COG-04 + CREAT-04 — Role-based & Six-Hats multi-track perspectives.

llive の思考層に「同じ Brief を複数の視点から並列に観察する」層を追加する。
COG-04 が role 軸 (architect / critic / executor / auditor)、
CREAT-04 が hat 軸 (white / red / black / yellow / green / blue) を担う。
両者は直交軸として独立に評価し、最終的に 1 つの multi-track 観察として
集約する。

設計責務:

* 各 lens は **scoring に専念し、blocking は行わない** (Governance と同じ責務分離)。
  recommend は Approval Bus / Governance がまとめて gating を担当する。
* 初期実装は deterministic な heuristic。後段で LLM-as-judge / sub-Brief 並列発行に
  Strategy で差し替え可能。
* 出力は :class:`PerspectiveNote` の tuple として ledger / BriefResult に固定記録。
  ledger は append-only JSONL なので、後から perspective を追加しても過去 ledger と
  互換性を保てる。
* tuple の順序は (roles 4 件 → hats 6 件) で固定 = replay determinism。

なぜ「役割 + 帽子」両方を持つか:

* role 軸 = どんな職能で見るか (architect: 構造、critic: リスク、executor: 実行可能性、
  auditor: 来歴・整合)
* hat 軸 = どんな思考モードで見るか (white: 事実、red: 直感、black: 否定、
  yellow: 肯定、green: 創造、blue: meta)
* 2 軸の交差で重複が出ても OK — それぞれ別 ledger entry なので audit 追跡が独立。

将来 LLM へ差し替えるとき:

* :class:`PerspectiveLens` を Protocol 化してあるので、各 lens を 1 つの sub-Brief
  プロンプトとして実装し、並列 LLM 呼び出しで同じ tuple を返せばよい。
* deterministic lens は CI / 単体テスト / mock 用途として残す。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from llive.brief.types import Brief
from llive.fullsense.types import ActionDecision, ActionPlan


# ---------------------------------------------------------------------------
# Perspective identity
# ---------------------------------------------------------------------------


class RolePerspective(StrEnum):
    """COG-04 — 4 職能 role。

    順序は固定: tuple 出力で先頭 4 件を占める。
    """

    ARCHITECT = "architect"   # 構造 / 分解 / 依存関係
    CRITIC = "critic"         # 反証 / リスク / 反対意見
    EXECUTOR = "executor"     # 実行可能性 / リソース / 期限
    AUDITOR = "auditor"       # 来歴 / 追跡可能性 / governance


class HatPerspective(StrEnum):
    """CREAT-04 — de Bono Six Hats。

    順序は固定: tuple 出力で後続 6 件を占める。
    """

    WHITE = "white"    # 事実・データ
    RED = "red"        # 直感・感情
    BLACK = "black"    # 否定・リスク
    YELLOW = "yellow"  # 肯定・利点
    GREEN = "green"    # 創造・代替案
    BLUE = "blue"      # meta・プロセス管理


PerspectiveId = str
"""Lens identity — ``role.name`` / ``hat.name`` の文字列形。"""


@dataclass(frozen=True)
class PerspectiveNote:
    """ある 1 視点から見た Brief / decision の観察結果。

    * ``score`` — 0.0〜1.0、その視点が「この決定を支持する度合い」。
      black hat / critic は否定的視点なので score が高い = ``concerns`` が深刻、
      とは限らない (詳細は ``concerns``/``observation`` を読むのが正)。
    * ``observation`` — 1 文の人間可読サマリ。
    * ``concerns`` — その視点が surfacing する具体的な懸念点 (tuple of str)。
    """

    perspective_id: PerspectiveId
    axis: str  # "role" or "hat"
    score: float
    observation: str
    concerns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.score) <= 1.0:
            raise ValueError(
                f"PerspectiveNote.score must be in [0,1], got {self.score!r}"
            )
        if self.axis not in {"role", "hat"}:
            raise ValueError(f"axis must be 'role' or 'hat', got {self.axis!r}")


# ---------------------------------------------------------------------------
# Lens protocol + deterministic heuristics
# ---------------------------------------------------------------------------


class PerspectiveLens(Protocol):
    """1 視点を担う observer。

    deterministic lens / LLM lens / human-in-the-loop lens を同じ Protocol で
    扱えるようにしてある。並列実装に差し替えるときは ``observe`` を非同期で
    呼べる lens を追加し、:class:`RoleBasedMultiTrack` 側で gather すれば良い。
    """

    perspective_id: PerspectiveId
    axis: str

    def observe(
        self,
        brief: Brief,
        decision: ActionDecision,
        plan: ActionPlan | None,
    ) -> PerspectiveNote:  # pragma: no cover - Protocol
        ...


# ---- helpers ---------------------------------------------------------------


def _has_dangerous_token(text: str) -> bool:
    """Governance と同じ語彙を流用 — 否定視点 lens が共通利用。"""
    lowered = text.lower()
    return any(t in lowered for t in (
        "rm -rf", "drop table", "format c:", "shutdown", "kill -9", "chmod 777",
    ))


def _brief_text(brief: Brief) -> str:
    return brief.goal + "\n" + "\n".join(brief.constraints)


# ---- 4 role lenses ---------------------------------------------------------


@dataclass(frozen=True)
class ArchitectLens:
    """構造視点 — 制約・分解の有無で評価。"""

    perspective_id: PerspectiveId = RolePerspective.ARCHITECT.value
    axis: str = "role"

    def observe(self, brief: Brief, decision: ActionDecision, plan: ActionPlan | None) -> PerspectiveNote:
        score = 0.5
        concerns: list[str] = []
        if brief.constraints:
            score += 0.2
        else:
            concerns.append("no explicit constraints — structure under-specified")
        if brief.success_criteria:
            score += 0.15
        else:
            concerns.append("no success_criteria — goal boundary unclear")
        if len(brief.goal) < 16:
            score -= 0.15
            concerns.append("goal text too short for structural decomposition")
        score = max(0.0, min(1.0, score))
        return PerspectiveNote(
            perspective_id=self.perspective_id,
            axis=self.axis,
            score=score,
            observation=f"architect score={score:.2f}: constraints/criteria coverage check",
            concerns=tuple(concerns),
        )


@dataclass(frozen=True)
class CriticLens:
    """反証視点 — 危険語・無 approval intervene を厳しく見る。"""

    perspective_id: PerspectiveId = RolePerspective.CRITIC.value
    axis: str = "role"

    def observe(self, brief: Brief, decision: ActionDecision, plan: ActionPlan | None) -> PerspectiveNote:
        concerns: list[str] = []
        support = 0.7  # default: critic tentatively supports unless reason to oppose
        if _has_dangerous_token(_brief_text(brief)):
            support -= 0.5
            concerns.append("dangerous tokens in goal/constraints")
        if decision is ActionDecision.INTERVENE and not brief.approval_required:
            support -= 0.3
            concerns.append("INTERVENE without approval gate")
        if plan is not None and plan.thought is not None and plan.thought.confidence < 0.3:
            support -= 0.2
            concerns.append("loop thought confidence is low")
        support = max(0.0, min(1.0, support))
        return PerspectiveNote(
            perspective_id=self.perspective_id,
            axis=self.axis,
            score=support,
            observation=f"critic support={support:.2f}: reviewing for failure modes",
            concerns=tuple(concerns),
        )


@dataclass(frozen=True)
class ExecutorLens:
    """実行可能性視点 — tools whitelist と decision の整合性。"""

    perspective_id: PerspectiveId = RolePerspective.EXECUTOR.value
    axis: str = "role"

    def observe(self, brief: Brief, decision: ActionDecision, plan: ActionPlan | None) -> PerspectiveNote:
        score = 0.6
        concerns: list[str] = []
        if decision in (ActionDecision.PROPOSE, ActionDecision.INTERVENE) and not brief.tools:
            score -= 0.35
            concerns.append("action decision but no tools whitelisted")
        if brief.tools:
            score += 0.15
        if decision is ActionDecision.SILENT:
            score -= 0.1
            concerns.append("SILENT decision provides nothing to execute")
        score = max(0.0, min(1.0, score))
        return PerspectiveNote(
            perspective_id=self.perspective_id,
            axis=self.axis,
            score=score,
            observation=f"executor feasibility={score:.2f}: tools vs decision check",
            concerns=tuple(concerns),
        )


@dataclass(frozen=True)
class AuditorLens:
    """来歴・追跡可能性視点 — ledger_path / governance hook の有無。"""

    perspective_id: PerspectiveId = RolePerspective.AUDITOR.value
    axis: str = "role"

    def observe(self, brief: Brief, decision: ActionDecision, plan: ActionPlan | None) -> PerspectiveNote:
        score = 0.4
        concerns: list[str] = []
        if brief.ledger_path is not None:
            score += 0.25
        else:
            concerns.append("ledger_path unset — relying on default location")
        if brief.approval_required:
            score += 0.15
        else:
            concerns.append("approval_required=False — no human checkpoint")
        if brief.success_criteria:
            score += 0.15
        score = max(0.0, min(1.0, score))
        return PerspectiveNote(
            perspective_id=self.perspective_id,
            axis=self.axis,
            score=score,
            observation=f"auditor traceability={score:.2f}: ledger/approval/criteria coverage",
            concerns=tuple(concerns),
        )


# ---- 6 hat lenses ---------------------------------------------------------


@dataclass(frozen=True)
class WhiteHatLens:
    """事実視点 — 計測可能な決定条件があるか。"""

    perspective_id: PerspectiveId = HatPerspective.WHITE.value
    axis: str = "hat"

    def observe(self, brief: Brief, decision: ActionDecision, plan: ActionPlan | None) -> PerspectiveNote:
        score = 0.4
        concerns: list[str] = []
        if brief.success_criteria:
            score += 0.3
        else:
            concerns.append("no measurable success_criteria")
        if any(c.startswith(("pass", "fail", "<=", ">=", "=", "<", ">")) for c in brief.constraints):
            score += 0.15
        score = max(0.0, min(1.0, score))
        return PerspectiveNote(
            perspective_id=self.perspective_id,
            axis=self.axis,
            score=score,
            observation=f"white-hat facts={score:.2f}: measurable evidence present?",
            concerns=tuple(concerns),
        )


@dataclass(frozen=True)
class RedHatLens:
    """直感視点 — surprise priority と decision の組合せ。"""

    perspective_id: PerspectiveId = HatPerspective.RED.value
    axis: str = "hat"

    def observe(self, brief: Brief, decision: ActionDecision, plan: ActionPlan | None) -> PerspectiveNote:
        gut = float(brief.priority)
        concerns: list[str] = []
        if gut > 0.85 and decision is ActionDecision.SILENT:
            concerns.append("high gut priority but SILENT decision")
        if gut < 0.2 and decision is ActionDecision.INTERVENE:
            concerns.append("low gut priority but INTERVENE decision")
        return PerspectiveNote(
            perspective_id=self.perspective_id,
            axis=self.axis,
            score=max(0.0, min(1.0, gut)),
            observation=f"red-hat gut={gut:.2f}: prior surprise vs decision",
            concerns=tuple(concerns),
        )


@dataclass(frozen=True)
class BlackHatLens:
    """否定視点 — 危険語と無 approval を最大限警戒。"""

    perspective_id: PerspectiveId = HatPerspective.BLACK.value
    axis: str = "hat"

    def observe(self, brief: Brief, decision: ActionDecision, plan: ActionPlan | None) -> PerspectiveNote:
        concerns: list[str] = []
        # black-hat score is *risk* — higher = more concerns surfaced
        risk = 0.2
        if _has_dangerous_token(_brief_text(brief)):
            risk += 0.6
            concerns.append("dangerous tokens in goal/constraints")
        if decision is ActionDecision.INTERVENE and not brief.approval_required:
            risk += 0.3
            concerns.append("INTERVENE without approval gate")
        if not brief.success_criteria and decision in (
            ActionDecision.PROPOSE, ActionDecision.INTERVENE
        ):
            risk += 0.15
            concerns.append("action without measurable success_criteria")
        risk = max(0.0, min(1.0, risk))
        return PerspectiveNote(
            perspective_id=self.perspective_id,
            axis=self.axis,
            score=risk,
            observation=f"black-hat risk={risk:.2f}: failure / safety scan",
            concerns=tuple(concerns),
        )


@dataclass(frozen=True)
class YellowHatLens:
    """肯定視点 — 良さを surfacing。"""

    perspective_id: PerspectiveId = HatPerspective.YELLOW.value
    axis: str = "hat"

    def observe(self, brief: Brief, decision: ActionDecision, plan: ActionPlan | None) -> PerspectiveNote:
        score = 0.5
        if brief.tools:
            score += 0.1
        if brief.success_criteria:
            score += 0.1
        if plan is not None and plan.thought is not None and plan.thought.confidence >= 0.7:
            score += 0.15
        if decision in (ActionDecision.PROPOSE, ActionDecision.INTERVENE):
            score += 0.05
        score = max(0.0, min(1.0, score))
        return PerspectiveNote(
            perspective_id=self.perspective_id,
            axis=self.axis,
            score=score,
            observation=f"yellow-hat optimism={score:.2f}: benefits inventory",
        )


@dataclass(frozen=True)
class GreenHatLens:
    """創造視点 — 代替案候補があるか。"""

    perspective_id: PerspectiveId = HatPerspective.GREEN.value
    axis: str = "hat"

    def observe(self, brief: Brief, decision: ActionDecision, plan: ActionPlan | None) -> PerspectiveNote:
        score = 0.4
        concerns: list[str] = []
        if plan is not None and plan.thought is not None:
            principles = list(plan.thought.triz_principles or [])
            if principles:
                score += min(0.3, 0.05 * len(principles))
            else:
                concerns.append("no TRIZ principles surfaced — limited alternatives")
        else:
            concerns.append("plan/thought missing — cannot assess alternatives")
        if brief.tools and len(brief.tools) >= 2:
            score += 0.15  # multiple tools suggests choice
        score = max(0.0, min(1.0, score))
        return PerspectiveNote(
            perspective_id=self.perspective_id,
            axis=self.axis,
            score=score,
            observation=f"green-hat creativity={score:.2f}: alternative-paths check",
            concerns=tuple(concerns),
        )


@dataclass(frozen=True)
class BlueHatLens:
    """meta 視点 — プロセス自体の健全性。"""

    perspective_id: PerspectiveId = HatPerspective.BLUE.value
    axis: str = "hat"

    def observe(self, brief: Brief, decision: ActionDecision, plan: ActionPlan | None) -> PerspectiveNote:
        score = 0.5
        concerns: list[str] = []
        if not brief.approval_required and decision is ActionDecision.INTERVENE:
            score -= 0.3
            concerns.append("process bypasses human approval")
        if brief.approval_required:
            score += 0.15
        if plan is not None and plan.rationale and len(plan.rationale) >= 16:
            score += 0.15
        else:
            concerns.append("decision rationale too short or missing")
        score = max(0.0, min(1.0, score))
        return PerspectiveNote(
            perspective_id=self.perspective_id,
            axis=self.axis,
            score=score,
            observation=f"blue-hat meta={score:.2f}: process integrity check",
            concerns=tuple(concerns),
        )


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


def _default_lenses() -> tuple[PerspectiveLens, ...]:
    """Order is part of the contract — see :class:`RoleBasedMultiTrack`."""
    return (
        ArchitectLens(),
        CriticLens(),
        ExecutorLens(),
        AuditorLens(),
        WhiteHatLens(),
        RedHatLens(),
        BlackHatLens(),
        YellowHatLens(),
        GreenHatLens(),
        BlueHatLens(),
    )


@dataclass(frozen=True)
class MultiTrackSummary:
    """:meth:`RoleBasedMultiTrack.observe` の集約結果。

    * ``support_score`` — 肯定軸 (yellow + executor + architect + auditor) の重み付け平均
    * ``risk_score`` — 否定軸 (black + critic) の重み付け平均
    * ``divergence`` — support と risk の差 (positive = 推進寄り、negative = 抑制寄り)
    * ``critical_concerns`` — risk axis lens が surfacing した具体的懸念の flatten 列
    """

    notes: tuple[PerspectiveNote, ...]
    support_score: float
    risk_score: float
    divergence: float
    critical_concerns: tuple[str, ...]

    @property
    def consensus_recommendation(self) -> str:
        """``proceed`` / ``review`` / ``hold`` — UI / 監査向けの短いラベル。"""
        if self.risk_score >= 0.6 and self.divergence < 0.0:
            return "hold"
        if self.divergence < 0.15 or self.risk_score >= 0.4:
            return "review"
        return "proceed"


class RoleBasedMultiTrack:
    """4 roles + 6 hats を並列に観察し、:class:`MultiTrackSummary` を返す。

    * 初期実装は deterministic — 10 個の lens を直列に呼ぶだけ。Brief / decision
      が同じなら結果は完全に同じ。
    * Strategy で lens を差し替え可能。例えば LLM 駆動 sub-Brief 並列発行に
      切り替えるなら、各 lens を async 化して ``observe_async`` を別途追加すれば良い。
    * Approval は **行わない** — Governance と同様 scoring に専念。
    """

    def __init__(self, lenses: tuple[PerspectiveLens, ...] | None = None) -> None:
        self._lenses: tuple[PerspectiveLens, ...] = lenses or _default_lenses()

    @property
    def lenses(self) -> tuple[PerspectiveLens, ...]:
        return self._lenses

    def observe(
        self,
        brief: Brief,
        decision: ActionDecision,
        plan: ActionPlan | None = None,
    ) -> MultiTrackSummary:
        notes: list[PerspectiveNote] = []
        for lens in self._lenses:
            note = lens.observe(brief, decision, plan)
            notes.append(note)

        # Support = yellow + executor + architect + auditor (建設的軸)
        support_ids = {
            HatPerspective.YELLOW.value,
            RolePerspective.EXECUTOR.value,
            RolePerspective.ARCHITECT.value,
            RolePerspective.AUDITOR.value,
        }
        # Risk = black + critic (警戒軸)
        risk_ids = {
            HatPerspective.BLACK.value,
            RolePerspective.CRITIC.value,
        }
        support_vals = [n.score for n in notes if n.perspective_id in support_ids]
        risk_vals = [n.score for n in notes if n.perspective_id in risk_ids]
        # critic.score is *support* (high = supports), so invert it to risk
        critic_risks = [
            1.0 - n.score for n in notes if n.perspective_id == RolePerspective.CRITIC.value
        ]
        black_risks = [
            n.score for n in notes if n.perspective_id == HatPerspective.BLACK.value
        ]
        risk_total = critic_risks + black_risks
        support = sum(support_vals) / len(support_vals) if support_vals else 0.0
        risk = sum(risk_total) / len(risk_total) if risk_total else 0.0
        divergence = support - risk

        critical_concerns: list[str] = []
        for n in notes:
            if n.perspective_id in {HatPerspective.BLACK.value, RolePerspective.CRITIC.value}:
                critical_concerns.extend(n.concerns)

        return MultiTrackSummary(
            notes=tuple(notes),
            support_score=max(0.0, min(1.0, support)),
            risk_score=max(0.0, min(1.0, risk)),
            divergence=divergence,
            critical_concerns=tuple(critical_concerns),
        )


__all__ = [
    "ArchitectLens",
    "AuditorLens",
    "BlackHatLens",
    "BlueHatLens",
    "CriticLens",
    "ExecutorLens",
    "GreenHatLens",
    "HatPerspective",
    "MultiTrackSummary",
    "PerspectiveLens",
    "PerspectiveNote",
    "RedHatLens",
    "RoleBasedMultiTrack",
    "RolePerspective",
    "WhiteHatLens",
    "YellowHatLens",
]
