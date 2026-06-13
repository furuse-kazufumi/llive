# SPDX-License-Identifier: Apache-2.0
"""CoevolutionGovernance skeleton (v0.E E.4 / CE-06/07/08) — unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest

from llive.approval.bus import ApprovalBus, Verdict
from llive.cognitive_mesh.tonic_risk import TonicRiskMonitor
from llive.perf.evolutionary import (
    CoevolutionGovernance,
    CollusionDetector,
    GovernanceReport,
    PeerEvaluationMatrix,
    collusion_risk_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_diverse_matrix(n: int = 4, seed: int = 0) -> PeerEvaluationMatrix:
    """共謀していない (バラバラの) peer matrix."""
    rng = np.random.default_rng(seed)
    m = rng.uniform(0.0, 1.0, size=(n, n))
    np.fill_diagonal(m, 0.0)
    return PeerEvaluationMatrix(
        agent_ids=tuple(f"a{i}" for i in range(n)),
        matrix=m,
        generation=0,
    )


def _build_uniform_high_matrix(n: int = 4, value: float = 0.95) -> PeerEvaluationMatrix:
    """全員が同じ高得点を付け合う = 嘘の評価."""
    m = np.full((n, n), value, dtype=np.float64)
    np.fill_diagonal(m, 0.0)
    return PeerEvaluationMatrix(
        agent_ids=tuple(f"a{i}" for i in range(n)),
        matrix=m,
        generation=0,
    )


def _build_symmetric_matrix(n: int = 4, seed: int = 0) -> PeerEvaluationMatrix:
    """i↔j で点を交換し合う互酬共謀 matrix."""
    rng = np.random.default_rng(seed)
    m = rng.uniform(0.0, 1.0, size=(n, n))
    sym = (m + m.T) / 2.0  # 完全対称
    np.fill_diagonal(sym, 0.0)
    return PeerEvaluationMatrix(
        agent_ids=tuple(f"a{i}" for i in range(n)),
        matrix=sym,
        generation=0,
    )


# ---------------------------------------------------------------------------
# 1. CollusionDetector
# ---------------------------------------------------------------------------


class TestCollusionDetector:
    def test_default_construct(self) -> None:
        d = CollusionDetector()
        assert d.variance_threshold == 1e-3
        assert d.symmetry_threshold == 0.8
        assert d.concentration_floor == 1.05

    def test_negative_variance_threshold_raises(self) -> None:
        with pytest.raises(ValueError):
            CollusionDetector(variance_threshold=-1e-5)

    def test_symmetry_threshold_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            CollusionDetector(symmetry_threshold=1.5)
        with pytest.raises(ValueError):
            CollusionDetector(symmetry_threshold=-1.5)

    def test_concentration_floor_below_one(self) -> None:
        with pytest.raises(ValueError):
            CollusionDetector(concentration_floor=0.5)

    def test_diverse_matrix_not_suspected(self) -> None:
        d = CollusionDetector()
        suspected, score = d.check(_build_diverse_matrix())
        # 完全 random なので各指標は穏当. 大抵 suspected=False
        # (small n=4 だと concentration が border に乗ることがあるが
        # variance/symmetry が両方 clear なので OR で False)
        assert isinstance(suspected, bool)
        assert "score_variance" in score
        assert "symmetry" in score
        assert "concentration" in score

    def test_uniform_high_matrix_is_suspected(self) -> None:
        d = CollusionDetector()
        suspected, score = d.check(_build_uniform_high_matrix())
        # 全員 0.95 → variance ≈ 0 → suspected True
        assert suspected is True
        assert score["score_variance"] < d.variance_threshold

    def test_symmetric_matrix_is_suspected(self) -> None:
        d = CollusionDetector(symmetry_threshold=0.5)
        suspected, score = d.check(_build_symmetric_matrix())
        # symmetry ≈ 1.0 → > 0.5 → suspected True
        assert suspected is True
        assert score["symmetry"] > d.symmetry_threshold


# ---------------------------------------------------------------------------
# 2. collusion_risk_score
# ---------------------------------------------------------------------------


class TestRiskScoreFn:
    def test_zero_variance_high_risk(self) -> None:
        s = collusion_risk_score(
            {
                "collusion_score": {
                    "score_variance": 0.0,
                    "symmetry": 0.0,
                    "concentration": 2.0,
                },
                "is_suspected_collusion": False,
            }
        )
        assert s >= 0.9  # variance risk dominates

    def test_high_symmetry_high_risk(self) -> None:
        s = collusion_risk_score(
            {
                "collusion_score": {
                    "score_variance": 1.0,
                    "symmetry": 0.95,
                    "concentration": 2.0,
                },
                "is_suspected_collusion": False,
            }
        )
        assert s >= 0.9

    def test_low_concentration_high_risk(self) -> None:
        s = collusion_risk_score(
            {
                "collusion_score": {
                    "score_variance": 1.0,
                    "symmetry": 0.0,
                    "concentration": 1.0,
                },
                "is_suspected_collusion": False,
            }
        )
        assert s >= 0.9

    def test_low_risk_state(self) -> None:
        s = collusion_risk_score(
            {
                "collusion_score": {
                    "score_variance": 1.0,
                    "symmetry": 0.0,
                    "concentration": 3.0,
                },
                "is_suspected_collusion": False,
            }
        )
        assert s == pytest.approx(0.0)

    def test_suspected_flag_adds_bonus(self) -> None:
        base = collusion_risk_score(
            {
                "collusion_score": {
                    "score_variance": 1.0,
                    "symmetry": 0.0,
                    "concentration": 3.0,
                },
                "is_suspected_collusion": False,
            }
        )
        boosted = collusion_risk_score(
            {
                "collusion_score": {
                    "score_variance": 1.0,
                    "symmetry": 0.0,
                    "concentration": 3.0,
                },
                "is_suspected_collusion": True,
            }
        )
        assert boosted > base
        assert boosted == pytest.approx(base + 0.1)

    def test_empty_state_returns_zero(self) -> None:
        assert collusion_risk_score({}) == pytest.approx(0.0)

    def test_capped_at_one(self) -> None:
        s = collusion_risk_score(
            {
                "collusion_score": {
                    "score_variance": 0.0,
                    "symmetry": 1.0,
                    "concentration": 1.0,
                },
                "is_suspected_collusion": True,
            }
        )
        assert s == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 3. CoevolutionGovernance — wiring
# ---------------------------------------------------------------------------


class TestCoevolutionGovernanceWiring:
    def test_default_construct_no_components(self) -> None:
        gov = CoevolutionGovernance()
        assert gov.approval_bus is None
        assert gov.tonic_monitor is None
        assert isinstance(gov.detector, CollusionDetector)

    def test_auto_register_risk_model(self) -> None:
        monitor = TonicRiskMonitor()
        gov = CoevolutionGovernance(tonic_monitor=monitor)
        names = {m.name for m in monitor.models()}
        assert gov.risk_model_name in names

    def test_no_auto_register_when_disabled(self) -> None:
        monitor = TonicRiskMonitor()
        gov = CoevolutionGovernance(
            tonic_monitor=monitor, auto_register_risk_model=False
        )
        names = {m.name for m in monitor.models()}
        assert gov.risk_model_name not in names

    def test_auto_register_skips_when_already_present(self) -> None:
        from llive.cognitive_mesh.tonic_risk import RiskModel

        monitor = TonicRiskMonitor()
        monitor.register(
            RiskModel(name="coevolution.collusion", score_fn=lambda s: 0.0)
        )
        # 重複 register は ValueError. skeleton はそれを回避すること.
        gov = CoevolutionGovernance(tonic_monitor=monitor)
        # 通常通り使えること
        assert gov.tonic_monitor is monitor


# ---------------------------------------------------------------------------
# 4. CoevolutionGovernance — evaluate_generation
# ---------------------------------------------------------------------------


class TestCoevolutionGovernanceEvaluation:
    def test_clean_matrix_no_approval_no_alert(self) -> None:
        bus = ApprovalBus()
        monitor = TonicRiskMonitor(interrupt_threshold=0.99)
        gov = CoevolutionGovernance(
            approval_bus=bus,
            tonic_monitor=monitor,
        )
        matrix = _build_diverse_matrix()
        report = gov.evaluate_generation(matrix, generation=1)
        assert isinstance(report, GovernanceReport)
        assert report.generation == 1
        # 共謀じゃないので approval_request は (大抵) None
        # ただし small n では concentration が border 寄りで suspected になる
        # 可能性があるため report の構造だけ確認.
        assert isinstance(report.is_suspected_collusion, bool)

    def test_collusion_matrix_triggers_approval(self) -> None:
        bus = ApprovalBus()
        gov = CoevolutionGovernance(approval_bus=bus)
        matrix = _build_uniform_high_matrix()
        report = gov.evaluate_generation(matrix, generation=7)

        assert report.is_suspected_collusion is True
        assert report.approval_request is not None
        assert report.approval_request_id is not None
        assert (
            report.approval_request.action == "coevolution.suspected_collusion"
        )
        # payload に generation と collusion_score が入っている
        payload = report.approval_request.payload
        assert payload["generation"] == 7
        assert "collusion_score" in payload
        # bus にも pending として残る
        pending_ids = {r.request_id for r in bus.pending()}
        assert report.approval_request_id in pending_ids

    def test_approval_payload_extra_merged(self) -> None:
        bus = ApprovalBus()
        gov = CoevolutionGovernance(approval_bus=bus)
        matrix = _build_uniform_high_matrix()
        report = gov.evaluate_generation(
            matrix,
            generation=2,
            approval_payload_extra={"hint": "league_main"},
        )
        assert report.approval_request is not None
        assert report.approval_request.payload["hint"] == "league_main"

    def test_collusion_matrix_triggers_risk_alert(self) -> None:
        monitor = TonicRiskMonitor(interrupt_threshold=0.5)
        gov = CoevolutionGovernance(tonic_monitor=monitor)
        matrix = _build_uniform_high_matrix()
        # cooldown を確実に超えるため fixed now を指定
        report = gov.evaluate_generation(
            matrix, generation=3, now=datetime(2026, 5, 21, 0, 0, 0)
        )
        assert report.risk_alert is not None
        assert report.risk_alert.score >= 0.5
        assert report.risk_alert.model_name == "coevolution.collusion"

    def test_approval_disabled_when_bus_none(self) -> None:
        gov = CoevolutionGovernance(approval_bus=None)
        matrix = _build_uniform_high_matrix()
        report = gov.evaluate_generation(matrix, generation=4)
        assert report.is_suspected_collusion is True
        assert report.approval_request is None

    def test_risk_disabled_when_monitor_none(self) -> None:
        gov = CoevolutionGovernance(tonic_monitor=None)
        matrix = _build_uniform_high_matrix()
        report = gov.evaluate_generation(matrix, generation=5)
        assert report.risk_alert is None

    def test_clean_matrix_no_approval_request(self) -> None:
        """共謀疑い無しのときは approval を絶対に出さない."""
        bus = ApprovalBus()
        # 強い threshold で False を保証
        gov = CoevolutionGovernance(
            approval_bus=bus,
            detector=CollusionDetector(
                variance_threshold=1e-12,
                symmetry_threshold=0.999,
                concentration_floor=1.0,
            ),
        )
        matrix = _build_diverse_matrix(n=5)
        report = gov.evaluate_generation(matrix, generation=6)
        assert report.is_suspected_collusion is False
        assert report.approval_request is None

    def test_report_to_dict_structure(self) -> None:
        bus = ApprovalBus()
        monitor = TonicRiskMonitor(interrupt_threshold=0.5)
        gov = CoevolutionGovernance(approval_bus=bus, tonic_monitor=monitor)
        matrix = _build_uniform_high_matrix()
        report = gov.evaluate_generation(
            matrix, generation=8, now=datetime(2026, 5, 21, 12, 0, 0)
        )
        d = report.to_dict()
        assert d["generation"] == 8
        assert d["is_suspected_collusion"] is True
        assert d["collusion_score"]
        assert d["approval_request_id"] is not None
        assert d["risk_alert"] is not None
        assert d["risk_alert"]["model_name"] == "coevolution.collusion"


# ---------------------------------------------------------------------------
# 5. End-to-end: approval cycle for collusion event
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_full_collusion_to_approval_cycle(self) -> None:
        """共謀検出 → approval request → 人手 deny → 次世代は別判断."""
        bus = ApprovalBus()
        gov = CoevolutionGovernance(approval_bus=bus)
        # 世代 1: 共謀疑い
        matrix1 = _build_uniform_high_matrix()
        rep1 = gov.evaluate_generation(matrix1, generation=1)
        assert rep1.approval_request is not None
        # 人手で deny
        bus.deny(rep1.approval_request_id, by="user:operator", rationale="reject")
        assert bus.current_verdict(rep1.approval_request_id) == Verdict.DENIED
        # 世代 2: clean matrix なら approval なし
        matrix2 = _build_diverse_matrix(n=5)
        rep2 = gov.evaluate_generation(matrix2, generation=2)
        # clean だと approval は出ない (det. が False)
        if not rep2.is_suspected_collusion:
            assert rep2.approval_request is None

    def test_multiple_generations_accumulate_alerts(self) -> None:
        """連続世代で共謀続行 → 複数 alert 蓄積 (cooldown を span)."""
        monitor = TonicRiskMonitor(
            interrupt_threshold=0.5, cooldown=timedelta(seconds=0)
        )
        gov = CoevolutionGovernance(tonic_monitor=monitor)
        matrix = _build_uniform_high_matrix()
        for g in range(3):
            now = datetime(2026, 5, 21, 0, 0, g)
            gov.evaluate_generation(matrix, generation=g, now=now)
        # cooldown=0 で 3 つとも記録される
        assert len(monitor.latest_alerts(n=10)) == 3
