# SPDX-License-Identifier: Apache-2.0
"""M8.1 Timeline bridge skeleton テスト —
cognitive_mesh 3 種 emit → Timeline event dict."""

from __future__ import annotations

from datetime import datetime

import pytest

from llive.cognitive_mesh.proactive import ProactiveUtterance
from llive.cognitive_mesh.quarantined_memory import QuarantineEntry
from llive.brief.types import BriefResult, BriefStatus
from llive.cognitive_mesh.timeline_emitter import (
    CognitiveMeshTimelineEmitter,
    InMemoryTimelineSink,
    brief_result_to_event,
    proactive_to_event,
    quarantine_to_event,
    risk_to_event,
)
from llive.cognitive_mesh.tonic_risk import RiskAlert


def _utterance() -> ProactiveUtterance:
    return ProactiveUtterance(
        content="build done",
        mode="timer",
        timestamp=datetime(2026, 5, 19, 10, 0, 0),
        gift_value=0.72,
    )


def _alert() -> RiskAlert:
    return RiskAlert(
        model_name="critical_logs",
        score=0.85,
        timestamp=datetime(2026, 5, 19, 10, 0, 0),
        state_snapshot={"cpu": 0.5},
    )


def _entry_active() -> QuarantineEntry:
    return QuarantineEntry(
        event_id="qmem-000001",
        payload="ok",
        signer_id="trusted-rss",
        quarantined_at=datetime(2026, 5, 19, 10, 0, 0),
        promoted_at=datetime(2026, 5, 19, 10, 0, 1),
        verified=True,
    )


def _entry_pending() -> QuarantineEntry:
    return QuarantineEntry(
        event_id="qmem-000002",
        payload="raw",
        signer_id=None,
        quarantined_at=datetime(2026, 5, 19, 10, 0, 0),
        verified=False,
    )


# ---------------------------------------------------------------------------
# pure converters
# ---------------------------------------------------------------------------


def test_proactive_to_event_shape() -> None:
    ev = proactive_to_event(_utterance(), task_id="t1", node_id="n1")
    assert ev["event_type"] == "cog_proactive_utterance"
    assert ev["task_id"] == "t1"
    assert ev["node_id"] == "n1"
    assert ev["timestamp_utc"] == "2026-05-19T10:00:00"
    assert ev["metadata"]["content"] == "build done"
    assert ev["metadata"]["mode"] == "timer"
    assert ev["metadata"]["gift_value"] == pytest.approx(0.72)
    assert isinstance(ev["event_id"], str) and len(ev["event_id"]) > 8


def test_risk_to_event_shape() -> None:
    ev = risk_to_event(_alert())
    assert ev["event_type"] == "cog_risk_alert"
    assert ev["metadata"]["model_name"] == "critical_logs"
    assert ev["metadata"]["score"] == pytest.approx(0.85)
    assert ev["metadata"]["state_snapshot"] == {"cpu": 0.5}


def test_quarantine_to_event_active() -> None:
    ev = quarantine_to_event(_entry_active())
    assert ev["event_type"] == "cog_quarantine_pending"
    assert ev["metadata"]["signer_id"] == "trusted-rss"
    assert ev["metadata"]["verified"] is True
    assert "active" in ev["metadata"]["summary"]


def test_quarantine_to_event_pending() -> None:
    ev = quarantine_to_event(_entry_pending())
    assert ev["metadata"]["verified"] is False
    assert ev["metadata"]["signer_id"] is None
    assert "pending" in ev["metadata"]["summary"]


# ---------------------------------------------------------------------------
# CognitiveMeshTimelineEmitter
# ---------------------------------------------------------------------------


def test_emitter_buffers_without_sink() -> None:
    em = CognitiveMeshTimelineEmitter()
    em.emit_proactive(_utterance())
    em.emit_risk(_alert())
    em.emit_quarantine(_entry_active())
    assert len(em.buffer) == 3
    kinds = [e["event_type"] for e in em.buffer]
    assert kinds == [
        "cog_proactive_utterance",
        "cog_risk_alert",
        "cog_quarantine_pending",
    ]


def test_emitter_pushes_to_sink() -> None:
    sink = InMemoryTimelineSink()
    em = CognitiveMeshTimelineEmitter(sink=sink, task_id="t1", node_id="n1")
    em.emit_proactive(_utterance())
    em.emit_risk(_alert())
    assert len(sink.received) == 2
    assert sink.received[0]["task_id"] == "t1"
    assert sink.received[0]["node_id"] == "n1"


def test_emitter_sink_exception_does_not_break_buffer() -> None:
    class _BadSink:
        def push(self, event):  # noqa: ANN001
            raise RuntimeError("boom")

    em = CognitiveMeshTimelineEmitter(sink=_BadSink())  # type: ignore[arg-type]
    em.emit_proactive(_utterance())
    # buffer には残るが sink は失敗
    assert len(em.buffer) == 1


def test_emitter_latest_and_clear() -> None:
    em = CognitiveMeshTimelineEmitter()
    em.emit_proactive(_utterance())
    em.emit_risk(_alert())
    em.emit_quarantine(_entry_active())
    assert len(em.latest(2)) == 2
    em.clear()
    assert em.buffer == []


def test_emitter_event_ids_are_unique() -> None:
    em = CognitiveMeshTimelineEmitter()
    em.emit_proactive(_utterance())
    em.emit_proactive(_utterance())
    ids = [e["event_id"] for e in em.buffer]
    assert len(set(ids)) == 2  # 同じ utterance でも event_id は毎回新規


def test_brief_result_to_event_shape() -> None:
    result = BriefResult(
        brief_id="b-001",
        status=BriefStatus.COMPLETED,
        rationale="done",
        confidence=0.8,
        ledger_entries=5,
    )
    ev = brief_result_to_event(
        result, task_id="t1", node_id="n1",
        timestamp_iso="2026-05-19T10:00:00+09:00",
    )
    assert ev["event_type"] == "cog_brief_result"
    assert ev["task_id"] == "t1"
    assert ev["timestamp_utc"] == "2026-05-19T10:00:00+09:00"
    assert ev["metadata"]["brief_id"] == "b-001"
    assert ev["metadata"]["status"] == "completed"
    assert ev["metadata"]["rationale"] == "done"
    assert ev["metadata"]["confidence"] == pytest.approx(0.8)
    assert ev["metadata"]["ledger_entries"] == 5


def test_emit_brief_result_buffers_and_sinks() -> None:
    sink = InMemoryTimelineSink()
    em = CognitiveMeshTimelineEmitter(sink=sink)
    result = BriefResult(
        brief_id="b-002", status=BriefStatus.COMPLETED, rationale="ok",
    )
    out = em.emit_brief_result(result)
    assert out["event_type"] == "cog_brief_result"
    assert sink.received[-1]["metadata"]["brief_id"] == "b-002"


def test_emitter_schema_matches_llove_panel_expectations() -> None:
    """llove CogEntry.from_event() が読む 3 種 event_type を網羅."""
    em = CognitiveMeshTimelineEmitter()
    em.emit_proactive(_utterance())
    em.emit_risk(_alert())
    em.emit_quarantine(_entry_active())
    event_types = {e["event_type"] for e in em.buffer}
    assert event_types == {
        "cog_proactive_utterance",
        "cog_risk_alert",
        "cog_quarantine_pending",
    }
    # llove 側で読む metadata key が揃っているか
    for ev in em.buffer:
        md = ev["metadata"]
        if ev["event_type"] == "cog_proactive_utterance":
            assert {"content", "mode", "gift_value"} <= set(md.keys())
        elif ev["event_type"] == "cog_risk_alert":
            assert {"model_name", "score"} <= set(md.keys())
        else:
            assert {"signer_id", "verified", "summary"} <= set(md.keys())
