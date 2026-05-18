# SPDX-License-Identifier: Apache-2.0
"""COG-MESH E2E integration test — M8.1〜M8.9 chain.

10 系統を 1 シナリオで連鎖させ、Timeline event dict が
llove CogEntry 互換 schema で出ることを確認.

Scenario:
1. MultiBriefCoherenceManager に 2 つの Brief を register (M8.8)
2. centrality_scores で支配的 brief を特定
3. BriefDequeRunnerBridge で Brief を fake runner に submit (M8.3)
4. BriefResult を Timeline emit (M8.1 拡張)
5. TitleRecallPlanner に foreshadow setup + similarity_fn 注入 (M8.4)
6. QuarantinedMemory に signed/unsigned 各 1 件 quarantine (M8.2)
7. TonicRiskMonitor 発火 → RiskInterventionAdapter → ApprovalBus pending (M8.5)
8. Risk alert を Timeline emit
9. Mesh5W1HAnnotator で text → annotation channel に emit (M8.6)
10. ProactiveLoop event mode で 1 件発話 → Timeline emit (M8.7)
11. GrammarLayer propose → InMemoryGrammarChangeSink 観測 (M8.9)

最後に InMemoryTimelineSink に積まれた event 列を verify.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from llive.approval.bus import ApprovalBus
from llive.brief.types import Brief, BriefResult, BriefStatus
from llive.cognitive_mesh.brief_runner_bridge import BriefDequeRunnerBridge
from llive.cognitive_mesh.embedding_similarity import default_embedding_similarity
from llive.cognitive_mesh.grammar_layer import (
    InMemoryGrammarChangeSink,
    MultilingualGrammar,
    UsageEvidence,
)
from llive.cognitive_mesh.intervention import RiskInterventionAdapter
from llive.cognitive_mesh.mesh_annotator import Mesh5W1HAnnotator
from llive.cognitive_mesh.multi_brief import MultiBriefCoherenceManager
from llive.cognitive_mesh.proactive import ProactiveEvent, ProactiveLoop
from llive.cognitive_mesh.quarantined_memory import (
    Ed25519Verifier,
    QuarantinedMemory,
    SignedPayload,
)
from llive.cognitive_mesh.quiet_hours import QuietHoursGuard
from llive.cognitive_mesh.timeline_emitter import (
    CognitiveMeshTimelineEmitter,
    InMemoryTimelineSink,
)
from llive.cognitive_mesh.title_recall import TitleRecallPlanner
from llive.cognitive_mesh.tonic_risk import RiskModel, TonicRiskMonitor


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def submit(self, brief: Brief) -> BriefResult:
        self.calls.append(brief.brief_id)
        return BriefResult(
            brief_id=brief.brief_id, status=BriefStatus.COMPLETED,
            rationale=f"processed {brief.goal}", confidence=0.85,
        )


def _active_guard(monkeypatch: pytest.MonkeyPatch) -> QuietHoursGuard:
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    return QuietHoursGuard()


def test_cognitive_mesh_full_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """1 シナリオで M8.1〜M8.9 が全部チェインすることを verify."""
    sink = InMemoryTimelineSink()
    emitter = CognitiveMeshTimelineEmitter(
        sink=sink, task_id="e2e", node_id="local",
    )

    # ---- 1. MultiBriefCoherenceManager + 実 Brief 統合 (M8.8) ----
    mgr = MultiBriefCoherenceManager()
    b1 = Brief(brief_id="e2e-001", goal="nightly bench")
    b2 = Brief(brief_id="e2e-002", goal="rotate keys")
    mgr.register_brief(b1)
    mgr.register_brief(b2)
    mgr.record_impact(b1.brief_id, b2.brief_id, 2.0)
    top = mgr.top_central_briefs(k=1)
    assert top[0][0] == b1.brief_id  # b1 が centrality 上位

    # ---- 2. BriefDeque ↔ BriefRunner bridge (M8.3) ----
    runner = _FakeRunner()
    bridge = BriefDequeRunnerBridge(runner=runner)
    bridge.enqueue(b1)
    bridge.enqueue(b2)
    results = bridge.submit_all()
    assert [r.brief_id for r in results] == [b1.brief_id, b2.brief_id]
    # BriefResult を Timeline emit
    for r in results:
        emitter.emit_brief_result(r)

    # ---- 3. TitleRecall + embedding factory (M8.4) ----
    sim = default_embedding_similarity()
    planner = TitleRecallPlanner(similarity_fn=sim)
    planner.setup("bench done", tag="bench")
    planner.setup("keys rotated", tag="keys")
    report = planner.evaluate("nightly bench done, keys rotated")
    assert report.recall_rate > 0.5  # 両 foreshadow 回収

    # ---- 4. Quarantined Memory (M8.2) ----
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, PublicFormat,
    )
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        encoding=Encoding.Raw, format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw,
    )
    verifier = Ed25519Verifier()
    verifier.register("trusted-rss", pub_raw)
    qmem = QuarantinedMemory(verifier=verifier)
    sig = priv.sign(b"news payload")
    signed = SignedPayload(payload="news payload", signer_id="trusted-rss", signature=sig)
    qmem.quarantine(signed)
    qmem.quarantine("untrusted blob")
    assert len(qmem.active_items()) == 1
    assert len(qmem.pending()) == 1
    for entry in qmem.iter_all():
        emitter.emit_quarantine(entry)

    # ---- 5. TonicRisk → ApprovalBus.intervene (M8.5) ----
    bus = ApprovalBus()
    adapter = RiskInterventionAdapter(bus=bus)
    monitor = TonicRiskMonitor(interrupt_threshold=0.5, on_alert=adapter)
    monitor.register(RiskModel(name="m", score_fn=lambda s: float(s.get("d", 0))))
    alert = monitor.tick(state={"d": 0.9}, now=datetime(2026, 5, 19, 10))
    assert alert is not None
    assert len(bus.pending()) == 1
    emitter.emit_risk(alert)

    # ---- 6. Mesh5W1H Annotator (M8.6) ----
    annotator = Mesh5W1HAnnotator()
    annotator.emit_from_text("Why did this happen because of the alert?")
    bundle = annotator.freeze()
    assert any(a.namespace == "mesh.why" for a in bundle.items)

    # ---- 7. ProactiveLoop event mode (M8.7) ----
    loop = ProactiveLoop(quiet_hours=_active_guard(monkeypatch), mode="event")
    event = ProactiveEvent(topic="halt", note="risk-triggered halt", severity=0.9)
    listener = {
        "current_topic": "halt",
        "risk_score": 0.8,
        "focus_level": 0.3,
        "in_quiet_hours": False,
    }
    utt = loop.tick_event(
        event=event, now=datetime(2026, 5, 19, 10), listener_state=listener
    )
    assert utt is not None
    emitter.emit_proactive(utt)

    # ---- 8. GrammarLayer M8.9 ----
    gsink = InMemoryGrammarChangeSink()
    mg = MultilingualGrammar(change_sink=gsink)
    proposal = mg.propose(
        "ja", pattern="risk-触り",
        evidence=UsageEvidence(pattern="リスク発火", samples=["alert", "halt"]),
    )
    snap = mg.promote(proposal, new_version="v_1")
    assert gsink.proposes == [proposal]
    assert gsink.promotes == [(proposal, snap)]

    # ---- 9. Sink 全件 verify — schema が llove CogEntry 互換 ----
    valid_event_types = {
        "cog_proactive_utterance",
        "cog_risk_alert",
        "cog_quarantine_pending",
        "cog_brief_result",
    }
    for ev in sink.received:
        assert ev["event_type"] in valid_event_types
        assert isinstance(ev["metadata"], dict)
        assert ev["task_id"] == "e2e"
        assert ev["node_id"] == "local"

    # 内訳: brief_result=2, quarantine=2, risk=1, proactive=1 = 6
    et_counts: dict[str, int] = {}
    for ev in sink.received:
        et_counts[ev["event_type"]] = et_counts.get(ev["event_type"], 0) + 1
    assert et_counts == {
        "cog_brief_result": 2,
        "cog_quarantine_pending": 2,
        "cog_risk_alert": 1,
        "cog_proactive_utterance": 1,
    }
    assert len(sink.received) == 6
