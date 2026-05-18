# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-03 完成配線 — TonicRiskMonitor ↔ ApprovalBus.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-03 で予告した
「閾値超のとき HITL 介入を要求する経路」を ApprovalBus と接続するための
adapter。

設計:
- ApprovalBus に `intervene` メソッドは存在しない (汎用 `request` のみ)。
- そこで RiskAlert を「介入承認 request」に変換する callable を提供する。
- TonicRiskMonitor の `on_alert` に直接渡せる callable (``__call__``)。
- emit した ApprovalRequest を `latest_request()` で取得可能 (テスト用)。

設計上の選択:
- request の action 名は ``"risk:intervene"`` で固定。policy 側で AllowList
  / DenyList を組む際の grep キー。
- principal は既定 ``"tonic_risk"``、運用で別エージェント名にも差し替え可能。
- timeout は短め (既定 5s)。intervention は 5s 以内に人手 / policy で
  返答が欲しいケースを想定。沈黙は §AB4 で DENIED 扱いになる。
- adapter は ledger / policy を持たない (ApprovalBus 側の責務)。

これにより `TonicRiskMonitor(on_alert=RiskInterventionAdapter(bus))` で
配線が完成し、COG-MESH-03 のループは threading + 介入要求まで本実装になる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llive.approval.bus import ApprovalBus, ApprovalRequest
    from llive.cognitive_mesh.tonic_risk import RiskAlert


@dataclass
class RiskInterventionAdapter:
    """RiskAlert を ApprovalBus への介入要求に変換する callable.

    Attributes:
        bus: 介入要求を投げる ApprovalBus.
        principal: request の principal フィールド (既定 ``"tonic_risk"``).
        action: request の action フィールド (既定 ``"risk:intervene"``).
        timeout_s: request の timeout (既定 5.0 秒).
    """

    bus: ApprovalBus
    principal: str = "tonic_risk"
    action: str = "risk:intervene"
    timeout_s: float = 5.0
    _requests: list[ApprovalRequest] = field(default_factory=list, init=False, repr=False)

    def __call__(self, alert: RiskAlert) -> ApprovalRequest:
        """RiskAlert を受け取り、ApprovalBus.request() を発行する.

        ``payload`` には ``model_name`` / ``score`` / ``timestamp`` /
        ``state_snapshot`` を構造化して載せる (policy が判定に使える形)。
        """
        payload: dict[str, object] = {
            "model_name": alert.model_name,
            "score": alert.score,
            "timestamp": alert.timestamp.isoformat(),
            "state_snapshot": dict(alert.state_snapshot),
        }
        request = self.bus.request(
            action=self.action,
            payload=payload,
            principal=self.principal,
            timeout_s=self.timeout_s,
        )
        self._requests.append(request)
        return request

    def latest_request(self) -> ApprovalRequest | None:
        """直近 emit した ApprovalRequest を返す (テスト / 監査用)."""
        return self._requests[-1] if self._requests else None

    def all_requests(self) -> list[ApprovalRequest]:
        """これまで emit した全 ApprovalRequest を返す (監査用)."""
        return list(self._requests)


__all__ = ["RiskInterventionAdapter"]
