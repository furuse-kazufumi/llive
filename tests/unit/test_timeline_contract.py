# SPDX-License-Identifier: Apache-2.0
"""Cross-repo contract test — llive emitter ↔ llove panel schema.

llove `views/llive/cognitive_mesh_panel.CogEntry.from_event()` が読む
field 群を llive emitter 側でも独立に検証する。 llove module は import
せず、合意済 schema (event_type 3 種 + 必須 metadata keys) を本 test に
ハードコードして守る contract.

Phase 6 で実 HTTP push を入れる際、本 test が schema drift を検出する
最後の砦になる。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from llive.cognitive_mesh.proactive import ProactiveUtterance
from llive.cognitive_mesh.quarantined_memory import QuarantineEntry
from llive.cognitive_mesh.timeline_emitter import (
    CognitiveMeshTimelineEmitter,
    proactive_to_event,
    quarantine_to_event,
    risk_to_event,
)
from llive.cognitive_mesh.tonic_risk import RiskAlert

# 合意済 contract — llove CogEntry.from_event() が読む構造
PROACTIVE_REQUIRED_METADATA: set[str] = {"content", "mode"}  # gift_value は optional
RISK_REQUIRED_METADATA: set[str] = {"model_name"}  # score は optional
QUARANTINE_REQUIRED_METADATA: set[str] = {"signer_id", "verified"}  # summary は optional

VALID_EVENT_TYPES: set[str] = {
    "cog_proactive_utterance",
    "cog_risk_alert",
    "cog_quarantine_pending",
}

# 全 event に共通で要求される top-level keys
TOPLEVEL_REQUIRED: set[str] = {
    "event_id",
    "task_id",
    "node_id",
    "event_type",
    "timestamp_utc",
    "metadata",
}


def _assert_toplevel_contract(ev: dict) -> None:
    missing = TOPLEVEL_REQUIRED - set(ev.keys())
    assert not missing, f"missing top-level keys: {missing}"
    assert ev["event_type"] in VALID_EVENT_TYPES, ev["event_type"]
    assert isinstance(ev["metadata"], dict)
    assert isinstance(ev["event_id"], str) and ev["event_id"]
    assert isinstance(ev["timestamp_utc"], str) and ev["timestamp_utc"]


def test_proactive_event_satisfies_contract() -> None:
    u = ProactiveUtterance(
        content="x", mode="timer", timestamp=datetime(2026, 5, 19, 10), gift_value=0.7
    )
    ev = proactive_to_event(u)
    _assert_toplevel_contract(ev)
    missing = PROACTIVE_REQUIRED_METADATA - set(ev["metadata"].keys())
    assert not missing


def test_risk_event_satisfies_contract() -> None:
    a = RiskAlert(
        model_name="m", score=0.9, timestamp=datetime(2026, 5, 19, 10),
    )
    ev = risk_to_event(a)
    _assert_toplevel_contract(ev)
    missing = RISK_REQUIRED_METADATA - set(ev["metadata"].keys())
    assert not missing


def test_quarantine_event_satisfies_contract() -> None:
    e = QuarantineEntry(
        event_id="q-1", payload="ok", signer_id="alice",
        quarantined_at=datetime(2026, 5, 19, 10), verified=True,
        promoted_at=datetime(2026, 5, 19, 10, 0, 1),
    )
    ev = quarantine_to_event(e)
    _assert_toplevel_contract(ev)
    missing = QUARANTINE_REQUIRED_METADATA - set(ev["metadata"].keys())
    assert not missing


def test_quarantine_unsigned_satisfies_contract() -> None:
    """signer_id=None でも contract を満たす (verified=False が伝わる)."""
    e = QuarantineEntry(
        event_id="q-2", payload="raw", signer_id=None,
        quarantined_at=datetime(2026, 5, 19, 10), verified=False,
    )
    ev = quarantine_to_event(e)
    _assert_toplevel_contract(ev)
    assert ev["metadata"]["signer_id"] is None
    assert ev["metadata"]["verified"] is False


def test_emitter_all_events_satisfy_contract() -> None:
    """3 種 emit を全て発火し contract を一括 verification."""
    em = CognitiveMeshTimelineEmitter(task_id="t", node_id="n")
    em.emit_proactive(
        ProactiveUtterance(
            content="hi", mode="event",
            timestamp=datetime(2026, 5, 19, 10), gift_value=0.8,
        )
    )
    em.emit_risk(
        RiskAlert(
            model_name="r", score=0.9, timestamp=datetime(2026, 5, 19, 10),
        )
    )
    em.emit_quarantine(
        QuarantineEntry(
            event_id="q-1", payload="ok", signer_id="alice",
            quarantined_at=datetime(2026, 5, 19, 10), verified=True,
            promoted_at=datetime(2026, 5, 19, 10, 0, 1),
        )
    )
    for ev in em.buffer:
        _assert_toplevel_contract(ev)
        assert ev["task_id"] == "t"
        assert ev["node_id"] == "n"


def test_timestamp_utc_is_iso_format() -> None:
    """llove CogEntry はソートに timestamp_utc 文字列を使うため、
    ISO 8601 format でないと比較が壊れる."""
    u = ProactiveUtterance(
        content="x", mode="timer", timestamp=datetime(2026, 5, 19, 10),
    )
    ev = proactive_to_event(u)
    ts = ev["timestamp_utc"]
    # datetime.fromisoformat で parse できる = ISO format
    parsed = datetime.fromisoformat(ts)
    assert parsed.year == 2026


def test_event_ids_are_unique_across_emit_calls() -> None:
    """同じ payload を 2 回 emit しても event_id が衝突しない (llove dedup 期待)."""
    em = CognitiveMeshTimelineEmitter()
    u = ProactiveUtterance(
        content="x", mode="timer", timestamp=datetime(2026, 5, 19, 10),
    )
    em.emit_proactive(u)
    em.emit_proactive(u)
    ids = [e["event_id"] for e in em.buffer]
    assert len(set(ids)) == 2


def test_score_field_is_numeric_when_present() -> None:
    """llove は score を float() してから format するので numeric であること."""
    a = RiskAlert(
        model_name="m", score=0.85, timestamp=datetime(2026, 5, 19, 10),
    )
    ev = risk_to_event(a)
    s = ev["metadata"]["score"]
    assert isinstance(s, (int, float))
    assert 0.0 <= float(s) <= 1.0


def test_gift_value_field_is_numeric_when_present() -> None:
    u = ProactiveUtterance(
        content="x", mode="timer",
        timestamp=datetime(2026, 5, 19, 10), gift_value=0.7,
    )
    ev = proactive_to_event(u)
    gv = ev["metadata"]["gift_value"]
    assert isinstance(gv, (int, float))


def test_metadata_dict_does_not_leak_unexpected_keys() -> None:
    """各 event の metadata は最小限の key のみ。"future-proof な merge"
    で副次的に増えていないことを 1 度確認 (drift 検出)."""
    a = RiskAlert(
        model_name="m", score=0.9, timestamp=datetime(2026, 5, 19, 10),
        state_snapshot={"k": "v"},
    )
    ev = risk_to_event(a)
    md_keys = set(ev["metadata"].keys())
    # risk は model_name / score / state_snapshot のみ (current schema)
    assert md_keys == {"model_name", "score", "state_snapshot"}
