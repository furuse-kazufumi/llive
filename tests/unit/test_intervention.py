# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-03 完成配線テスト — RiskInterventionAdapter ↔ ApprovalBus.

期待する振る舞い:
- TonicRiskMonitor の on_alert に渡せる callable である.
- alert 発火で ApprovalBus.request() が呼ばれ pending に積まれる.
- payload に model_name / score / timestamp / state_snapshot が入る.
- adapter.latest_request() で直近 request を取得できる.
- policy 連携: AllowList/DenyList policy 経由で即決可能.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from llive.approval.bus import ApprovalBus, Verdict
from llive.cognitive_mesh.intervention import RiskInterventionAdapter
from llive.cognitive_mesh.tonic_risk import RiskAlert, RiskModel, TonicRiskMonitor


def _make_alert(score: float = 0.95) -> RiskAlert:
    return RiskAlert(
        model_name="dummy",
        score=score,
        timestamp=datetime(2026, 5, 19, 12, 0, 0),
        state_snapshot={"foo": "bar"},
    )


def test_adapter_emits_approval_request() -> None:
    bus = ApprovalBus()
    adapter = RiskInterventionAdapter(bus=bus)
    req = adapter(_make_alert())

    assert req.action == "risk:intervene"
    assert req.principal == "tonic_risk"
    assert req.payload["model_name"] == "dummy"
    assert req.payload["score"] == pytest.approx(0.95)
    assert req.payload["timestamp"].startswith("2026-05-19T12:00:00")
    assert req.payload["state_snapshot"] == {"foo": "bar"}
    assert bus.pending() == [req]


def test_adapter_latest_and_all_requests() -> None:
    bus = ApprovalBus()
    adapter = RiskInterventionAdapter(bus=bus)
    assert adapter.latest_request() is None
    r1 = adapter(_make_alert(score=0.8))
    r2 = adapter(_make_alert(score=0.9))
    assert adapter.latest_request() == r2
    assert adapter.all_requests() == [r1, r2]


def test_adapter_is_callable_for_tonic_risk_on_alert() -> None:
    """TonicRiskMonitor.on_alert に直接渡せることを確認."""
    bus = ApprovalBus()
    adapter = RiskInterventionAdapter(bus=bus)
    monitor = TonicRiskMonitor(interrupt_threshold=0.5, on_alert=adapter)
    monitor.register(RiskModel(name="m1", score_fn=lambda s: s.get("danger", 0.0)))

    alert = monitor.tick(state={"danger": 0.99})
    assert alert is not None
    assert adapter.latest_request() is not None
    latest = adapter.latest_request()
    assert latest is not None
    assert latest.payload["model_name"] == "m1"
    assert latest.payload["score"] == pytest.approx(0.99)


def test_adapter_with_policy_auto_decides() -> None:
    """policy が verdict を返せば即決され pending から消える (§AB1)."""

    class DenyAllRiskPolicy:
        def evaluate(self, request):  # noqa: ANN001
            if request.action == "risk:intervene":
                return Verdict.DENIED
            return None

    bus = ApprovalBus(policy=DenyAllRiskPolicy())
    adapter = RiskInterventionAdapter(bus=bus)
    req = adapter(_make_alert())

    # policy 即決により pending から消える
    assert bus.pending() == []
    # ledger に DENIED が残る
    assert bus.current_verdict(req.request_id) == Verdict.DENIED


def test_adapter_custom_principal_and_action() -> None:
    bus = ApprovalBus()
    adapter = RiskInterventionAdapter(
        bus=bus, principal="custom_agent", action="risk:halt", timeout_s=1.0
    )
    req = adapter(_make_alert())
    assert req.principal == "custom_agent"
    assert req.action == "risk:halt"
    assert req.timeout_s == 1.0
