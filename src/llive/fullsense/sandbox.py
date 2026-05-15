# SPDX-License-Identifier: Apache-2.0
"""Sandbox Output Bus — log のみ、外向け副作用一切なし.

MVP の安全装置。Sandbox モードで loop を回している間は、いかなる action plan
(PROPOSE / INTERVENE 含む) も **in-memory log と optional file** にしか落ち
ない。MCP push / HTTP fetch / llove bridge は **このバスからは行わない**。

将来 ``ProductionOutputBus`` を作るときは ``@govern(policy)``
(memory:agent-governance) を通して `approve` を必須にする。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from llive.fullsense.types import ActionPlan, Stimulus


@dataclass
class SandboxRecord:
    """One traced loop iteration."""

    stim: Stimulus
    plan: ActionPlan
    stages: dict[str, object] = field(default_factory=dict)
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))


class SandboxOutputBus:
    """Thread-safe append-only log of FullSense decisions.

    Optionally mirrors records to a JSONL file. Never performs external side
    effects beyond writing the configured file.
    """

    def __init__(self, log_path: Path | str | None = None) -> None:
        self.log_path = Path(log_path) if log_path else None
        self._records: list[SandboxRecord] = []
        self._denied_emits: list[dict[str, object]] = []
        self._lock = threading.Lock()

    def record_denied_emit(
        self,
        *,
        action: str,
        payload: dict[str, object],
        request_id: str,
        rationale: str = "",
    ) -> None:
        """ProductionOutputBus が DENIED された emit 試行を観測ログに残す.

        副作用ゼロ (Sandbox の制約を維持). production_bus.denied_records()
        と二重で記録されるが、こちらは log_path にも mirror される.
        """
        entry: dict[str, object] = {
            "kind": "denied_emit",
            "action": action,
            "payload": dict(payload),
            "request_id": request_id,
            "rationale": rationale,
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        with self._lock:
            self._denied_emits.append(entry)
            if self.log_path is not None:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def denied_emits(self) -> list[dict[str, object]]:
        with self._lock:
            return [dict(e) for e in self._denied_emits]

    def emit(self, record: SandboxRecord) -> None:
        with self._lock:
            self._records.append(record)
            if self.log_path is not None:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(_to_jsonable(record), ensure_ascii=False) + "\n")

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[SandboxRecord]:
        with self._lock:
            return iter(list(self._records))

    def records(self) -> list[SandboxRecord]:
        with self._lock:
            return list(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._denied_emits.clear()


def _to_jsonable(record: SandboxRecord) -> dict[str, object]:
    return {
        "recorded_at": record.recorded_at,
        "stim": {
            "stim_id": record.stim.stim_id,
            "content": record.stim.content,
            "source": record.stim.source,
            "surprise": record.stim.surprise,
            "timestamp": record.stim.timestamp,
        },
        "plan": {
            "decision": record.plan.decision.value,
            "rationale": record.plan.rationale,
            "ego_score": record.plan.ego_score,
            "altruism_score": record.plan.altruism_score,
            "thought_text": record.plan.thought.text if record.plan.thought else None,
            "triz_principles": (
                record.plan.thought.triz_principles if record.plan.thought else []
            ),
        },
        "stages": record.stages,
    }
