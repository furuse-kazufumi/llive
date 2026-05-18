# SPDX-License-Identifier: Apache-2.0
"""COG-MESH ↔ Timeline emit bridge — M8.1 skeleton.

cognitive_mesh の 3 種 emit (ProactiveUtterance / RiskAlert /
QuarantineEntry) を llmesh Timeline server (`/timeline/recent` /
`/timeline/task`) の JSON event_type 構造に変換する純粋関数 + sink
Protocol を提供する.

設計:
- **payload 形 = llove `views/llive/cognitive_mesh_panel.py` と対称**
  llove 側で `CogEntry.from_event()` が読む形に合わせ、無駄な変換層を
  挟まない (llive emitter ↔ llove panel を同じ schema で繋ぐ).
- **3 種別 event_type**:
  - `cog_proactive_utterance` (content / mode / gift_value / timestamp)
  - `cog_risk_alert` (model_name / score / timestamp / state_snapshot)
  - `cog_quarantine_pending` (signer_id / verified / event_id /
    quarantined_at / summary)
- **TimelineSink Protocol** — push(event_dict) を持つ任意 sink (HTTP
  クライアント / file / in-memory test fake) を受ける.
- **実 HTTP push は本 module の範囲外** — 次セッションで `llive/clients/
  llmesh_timeline.py` などを別途配備する想定.

本 skeleton で確立する schema が llive ↔ llmesh ↔ llove の 3 者で
固定する契約。Phase 6 の本配線で実 emit を流す.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from llive.brief.types import BriefResult
    from llive.cognitive_mesh.proactive import ProactiveUtterance
    from llive.cognitive_mesh.quarantined_memory import QuarantineEntry
    from llive.cognitive_mesh.tonic_risk import RiskAlert


class TimelineSink(Protocol):
    """1 件の cognitive_mesh event を受け取る sink.

    現実装: 任意の dict (JSON friendly) を push() に渡す callable.
    """

    def push(self, event: dict[str, Any]) -> None: ...


def proactive_to_event(
    utterance: ProactiveUtterance, *, task_id: str = "", node_id: str = ""
) -> dict[str, Any]:
    """ProactiveUtterance → Timeline event dict (cog_proactive_utterance)."""
    return {
        "event_id": uuid.uuid4().hex,
        "task_id": task_id,
        "node_id": node_id,
        "event_type": "cog_proactive_utterance",
        "timestamp_utc": utterance.timestamp.isoformat(),
        "metadata": {
            "content": utterance.content,
            "mode": utterance.mode,
            "gift_value": float(utterance.gift_value),
        },
    }


def risk_to_event(
    alert: RiskAlert, *, task_id: str = "", node_id: str = ""
) -> dict[str, Any]:
    """RiskAlert → Timeline event dict (cog_risk_alert)."""
    return {
        "event_id": uuid.uuid4().hex,
        "task_id": task_id,
        "node_id": node_id,
        "event_type": "cog_risk_alert",
        "timestamp_utc": alert.timestamp.isoformat(),
        "metadata": {
            "model_name": alert.model_name,
            "score": float(alert.score),
            "state_snapshot": dict(alert.state_snapshot),
        },
    }


def brief_result_to_event(
    result: BriefResult,
    *,
    task_id: str = "",
    node_id: str = "",
    timestamp_iso: str | None = None,
) -> dict[str, Any]:
    """BriefResult → Timeline event dict (cog_brief_result).

    Phase 6 で実 BriefRunner.submit() の post-hook から発行する想定。
    本 skeleton では event_type schema を予約する目的のみ.

    Args:
        result: BriefRunner から返った BriefResult.
        timestamp_iso: 既定 (None) は datetime.now().isoformat() を入れる.
    """
    from datetime import datetime as _dt
    if timestamp_iso is None:
        timestamp_iso = _dt.now().isoformat()
    return {
        "event_id": uuid.uuid4().hex,
        "task_id": task_id,
        "node_id": node_id,
        "event_type": "cog_brief_result",
        "timestamp_utc": timestamp_iso,
        "metadata": {
            "brief_id": result.brief_id,
            "status": str(result.status.value if hasattr(result.status, "value") else result.status),
            "rationale": result.rationale,
            "confidence": float(result.confidence),
            "ledger_entries": int(result.ledger_entries),
        },
    }


def quarantine_to_event(
    entry: QuarantineEntry, *, task_id: str = "", node_id: str = ""
) -> dict[str, Any]:
    """QuarantineEntry → Timeline event dict (cog_quarantine_pending).

    Note:
        active も pending も同じ event_type で発行する (verified フラグで
        区別)。llove `CogEntry.from_event()` が active / pending を表示
        分岐するので、ここで分けないほうがシンプル。
    """
    summary = (
        f"{entry.signer_id or 'unsigned'} → "
        f"{'active' if entry.promoted_at else 'pending'}"
    )
    return {
        "event_id": uuid.uuid4().hex,
        "task_id": task_id,
        "node_id": node_id,
        "event_type": "cog_quarantine_pending",
        "timestamp_utc": entry.quarantined_at.isoformat(),
        "metadata": {
            "qmem_id": entry.event_id,
            "signer_id": entry.signer_id,
            "verified": bool(entry.verified),
            "summary": summary,
        },
    }


@dataclass
class CognitiveMeshTimelineEmitter:
    """ProactiveLoop / TonicRiskMonitor / QuarantinedMemory の emit を
    まとめて Timeline sink に流す convenience facade.

    sink を持たない場合は in-memory buffer に貯めるだけ (テスト用)。
    実 HTTP / MCP push は Phase 6 で別 sink を注入。

    Attributes:
        sink: 注入された sink (None なら buffer のみ).
        task_id / node_id: 全 event に付与するタグ (空文字列でも valid).
    """

    sink: TimelineSink | None = None
    task_id: str = ""
    node_id: str = ""
    buffer: list[dict[str, Any]] = field(default_factory=list)

    def _emit(self, event: dict[str, Any]) -> None:
        self.buffer.append(event)
        if self.sink is not None:
            try:
                self.sink.push(event)
            except Exception:  # noqa: BLE001 — sink 失敗で本体を止めない
                pass

    def emit_proactive(self, utterance: ProactiveUtterance) -> dict[str, Any]:
        event = proactive_to_event(
            utterance, task_id=self.task_id, node_id=self.node_id
        )
        self._emit(event)
        return event

    def emit_risk(self, alert: RiskAlert) -> dict[str, Any]:
        event = risk_to_event(alert, task_id=self.task_id, node_id=self.node_id)
        self._emit(event)
        return event

    def emit_quarantine(self, entry: QuarantineEntry) -> dict[str, Any]:
        event = quarantine_to_event(
            entry, task_id=self.task_id, node_id=self.node_id
        )
        self._emit(event)
        return event

    def emit_brief_result(self, result: BriefResult) -> dict[str, Any]:
        """BriefRunner.submit() 完了後に呼ぶ post-hook."""
        event = brief_result_to_event(
            result, task_id=self.task_id, node_id=self.node_id
        )
        self._emit(event)
        return event

    def latest(self, n: int = 10) -> list[dict[str, Any]]:
        return self.buffer[-n:]

    def clear(self) -> None:
        self.buffer.clear()


@dataclass
class InMemoryTimelineSink:
    """テスト / オフラインデモ用の in-memory sink. push を順に観測."""

    received: list[dict[str, Any]] = field(default_factory=list)

    def push(self, event: dict[str, Any]) -> None:
        self.received.append(event)


__all__ = [
    "CognitiveMeshTimelineEmitter",
    "InMemoryTimelineSink",
    "TimelineSink",
    "brief_result_to_event",
    "proactive_to_event",
    "quarantine_to_event",
    "risk_to_event",
]
