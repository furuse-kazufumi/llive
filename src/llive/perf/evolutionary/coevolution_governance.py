# SPDX-License-Identifier: Apache-2.0
"""E.4 governance interface skeleton — CollusionDetector × Approval Bus × TonicRisk.

ユーザー指示 (2026-05-21):
    「集団内政治と共謀を CE-06/07/08 で抑えるには既存 approval/ + COG-MESH-03
     TonicRisk + Quarantine と peer_evaluation の collusion 指標を繋げる必要が
     ある。まずは skeleton で interface を確立する」

E.4 = CE-06 + CE-07 + CE-08:

- **CE-06 CollusionDetector** — PeerEvaluationMatrix.is_suspected_collusion を
  thresholds 付きでラップ. variance / symmetry / concentration の 3 指標を
  まとめて `check()` で返す.
- **CE-07 Approval Bus 連携** — 共謀疑い時に
  ApprovalBus.request("coevolution.suspected_collusion", payload) を発行.
  人間 or policy が APPROVED/DENIED を返すまで pending.
- **CE-08 TonicRisk 連携** — 世代単位の collusion_score を state にして
  TonicRiskMonitor.tick() に注入. interrupt_threshold 超過で RiskAlert.

本 module は **skeleton**: バインディング interface を確立し既存 component
と接続する. Quarantined Memory (COG-MESH-05) への隔離は alert callback 経由
で行うが、本 module は callback を発火するだけで Quarantine 機構そのものは
含まない (別 module 委譲).

設計:
- ApprovalBus / TonicRiskMonitor は **両方とも optional**. 片方欠けても skeleton
  は機能する (例: monitor 無しで approval だけ走らせる, 逆も可).
- TonicRiskMonitor への RiskModel 登録は `auto_register_risk_model=True` で
  自動. ユーザーが事前に登録済みなら skip.
- score_fn は別 module で再利用できるよう module-level に export.

要件根拠:
- ``docs/requirements_v0.E_competitive_coevolution.md`` 0.4 節 + 0.5 節 + 0.6 節
  + CE-06/07/08, Phase E.4.
- [[project_cog_mesh_implementation_2026_05_19]] COG-MESH-03 TonicRiskMonitor.
- [[project_llive_v0E_coevolution]] memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from llive.approval.bus import ApprovalBus, ApprovalRequest
from llive.cognitive_mesh.tonic_risk import RiskAlert, RiskModel, TonicRiskMonitor
from llive.perf.evolutionary.peer_evaluation import PeerEvaluationMatrix

# ---------------------------------------------------------------------------
# CE-06 — CollusionDetector
# ---------------------------------------------------------------------------


@dataclass
class CollusionDetector:
    """共謀疑い 3 指標を集計し suspected/clear を返す.

    PeerEvaluationMatrix の native API ``collusion_score()`` /
    ``is_suspected_collusion()`` を threshold dataclass で wrap. threshold を
    1 か所で集中管理し A/B 比較や config 注入を容易にする.

    Attributes
    ----------
    variance_threshold : float
        off-diagonal score variance がこれ未満なら risk (default 1e-3).
    symmetry_threshold : float
        symmetry (corr(M, M.T)) がこれ超過なら risk (default 0.8).
    concentration_floor : float
        column_mean top1/mean がこれ未満なら risk (default 1.05).
    """

    variance_threshold: float = 1e-3
    symmetry_threshold: float = 0.8
    concentration_floor: float = 1.05

    def __post_init__(self) -> None:
        if self.variance_threshold < 0:
            raise ValueError("variance_threshold must be >= 0")
        if not (-1.0 <= self.symmetry_threshold <= 1.0):
            raise ValueError("symmetry_threshold must be in [-1, 1]")
        if self.concentration_floor < 1.0:
            raise ValueError("concentration_floor must be >= 1.0")

    def check(
        self, peer_matrix: PeerEvaluationMatrix
    ) -> tuple[bool, dict[str, float]]:
        """1 世代の peer matrix を評価し (is_suspected, score_dict) を返す.

        score_dict は ``score_variance`` / ``symmetry`` / ``concentration``.
        """
        score = peer_matrix.collusion_score()
        suspected = peer_matrix.is_suspected_collusion(
            variance_threshold=self.variance_threshold,
            symmetry_threshold=self.symmetry_threshold,
            concentration_floor=self.concentration_floor,
        )
        return bool(suspected), dict(score)


# ---------------------------------------------------------------------------
# Risk score function (module-level, reusable for TonicRiskMonitor.register)
# ---------------------------------------------------------------------------


def collusion_risk_score(state: dict[str, Any]) -> float:
    """state["collusion_score"] / state["is_suspected_collusion"] から
    [0, 1] の risk score を計算する.

    3 指標を独立に「悪さ」に正規化 → max を取る + suspected フラグで +0.1
    ボーナス. RiskModel.score_fn として TonicRiskMonitor に注入できる.

    Normalization (heuristic, [0, 1] にクランプ):

    - variance: 0 → risk 1, >= 0.5 → risk 0 (linear).
    - symmetry: そのまま clip (>0 のとき risk).
    - concentration: 1.0 → risk 1, >= 3.0 → risk 0 (linear).
    - is_suspected: True で +0.1 bonus.
    """
    s = state.get("collusion_score") or {}
    if not s:
        # データ無し = リスク評価不能 = 0. is_suspected フラグ単独でも昇格させない.
        return 0.0
    var_v = float(s.get("score_variance", 0.0))
    sym_v = float(s.get("symmetry", 0.0))
    conc_v = float(s.get("concentration", 0.0))

    var_risk = max(0.0, 1.0 - var_v / 0.5)
    sym_risk = max(0.0, min(1.0, sym_v))
    if conc_v <= 1.0:
        conc_risk = 1.0
    elif conc_v >= 3.0:
        conc_risk = 0.0
    else:
        conc_risk = (3.0 - conc_v) / 2.0

    bonus = 0.1 if state.get("is_suspected_collusion") else 0.0
    return float(min(1.0, max(var_risk, sym_risk, conc_risk) + bonus))


# ---------------------------------------------------------------------------
# GovernanceReport — 1 世代の評価結果
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernanceReport:
    """1 世代の governance 評価結果 (CE-06/07/08 統合 view)."""

    generation: int
    is_suspected_collusion: bool
    collusion_score: dict[str, float]
    approval_request: ApprovalRequest | None = None
    risk_alert: RiskAlert | None = None

    @property
    def approval_request_id(self) -> str | None:
        return None if self.approval_request is None else self.approval_request.request_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": int(self.generation),
            "is_suspected_collusion": bool(self.is_suspected_collusion),
            "collusion_score": dict(self.collusion_score),
            "approval_request_id": self.approval_request_id,
            "risk_alert": {
                "model_name": self.risk_alert.model_name,
                "score": self.risk_alert.score,
                "timestamp": self.risk_alert.timestamp.isoformat(),
            }
            if self.risk_alert is not None
            else None,
        }


# ---------------------------------------------------------------------------
# CoevolutionGovernance — skeleton wiring
# ---------------------------------------------------------------------------


DEFAULT_RISK_MODEL_NAME = "coevolution.collusion"
DEFAULT_APPROVAL_ACTION = "coevolution.suspected_collusion"


@dataclass
class CoevolutionGovernance:
    """CollusionDetector → Approval Bus + TonicRiskMonitor の skeleton.

    Usage::

        bus = ApprovalBus()
        monitor = TonicRiskMonitor(interrupt_threshold=0.7)
        gov = CoevolutionGovernance(
            approval_bus=bus,
            tonic_monitor=monitor,
        )
        report = gov.evaluate_generation(peer_matrix, generation=42)
        if report.is_suspected_collusion:
            ... # bus に approval request が出ている

    Attributes
    ----------
    approval_bus : ApprovalBus | None
        共謀疑い時の approval 発行先. None なら approval は出さない.
    tonic_monitor : TonicRiskMonitor | None
        世代単位 risk tick の投入先. None なら risk tick はスキップ.
    detector : CollusionDetector
        共謀検出器. デフォルトの thresholds で初期化される.
    risk_model_name : str
        TonicRiskMonitor に register する RiskModel 名.
    auto_register_risk_model : bool
        tonic_monitor 設定時に RiskModel(collusion_risk_score) を自動 register.
    approval_action : str
        共謀疑い時に ApprovalBus.request(action=...) で使う action 名.
    approval_principal : str
        ApprovalBus.request(principal=...).
    """

    approval_bus: ApprovalBus | None = None
    tonic_monitor: TonicRiskMonitor | None = None
    detector: CollusionDetector = field(default_factory=CollusionDetector)
    risk_model_name: str = DEFAULT_RISK_MODEL_NAME
    auto_register_risk_model: bool = True
    approval_action: str = DEFAULT_APPROVAL_ACTION
    approval_principal: str = "llive.coevolution"

    def __post_init__(self) -> None:
        if self.auto_register_risk_model and self.tonic_monitor is not None:
            existing = {m.name for m in self.tonic_monitor.models()}
            if self.risk_model_name not in existing:
                self.tonic_monitor.register(
                    RiskModel(
                        name=self.risk_model_name,
                        score_fn=collusion_risk_score,
                        weight=1.0,
                    )
                )

    def evaluate_generation(
        self,
        peer_matrix: PeerEvaluationMatrix,
        *,
        generation: int,
        approval_payload_extra: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> GovernanceReport:
        """1 世代の peer matrix を評価し governance アクションを発火する.

        Returns
        -------
        GovernanceReport
            検査結果 + approval / risk の発火痕跡.
        """
        suspected, score = self.detector.check(peer_matrix)

        approval_request: ApprovalRequest | None = None
        if suspected and self.approval_bus is not None:
            payload: dict[str, object] = {
                "generation": int(generation),
                "collusion_score": dict(score),
                "n_agents": len(peer_matrix.agent_ids),
            }
            if approval_payload_extra:
                payload.update(approval_payload_extra)
            approval_request = self.approval_bus.request(
                action=self.approval_action,
                payload=payload,
                principal=self.approval_principal,
            )

        risk_alert: RiskAlert | None = None
        if self.tonic_monitor is not None:
            state = {
                "generation": int(generation),
                "collusion_score": dict(score),
                "is_suspected_collusion": bool(suspected),
            }
            risk_alert = self.tonic_monitor.tick(state, now=now)

        return GovernanceReport(
            generation=int(generation),
            is_suspected_collusion=bool(suspected),
            collusion_score=dict(score),
            approval_request=approval_request,
            risk_alert=risk_alert,
        )


__all__ = [
    "DEFAULT_APPROVAL_ACTION",
    "DEFAULT_RISK_MODEL_NAME",
    "CoevolutionGovernance",
    "CollusionDetector",
    "GovernanceReport",
    "collusion_risk_score",
]
