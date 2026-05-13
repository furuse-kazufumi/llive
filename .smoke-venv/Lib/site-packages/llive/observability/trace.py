"""Structured route + memory link traces (OBS-01)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _default_trace_path() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "logs" / "trace.jsonl"


class SubblockTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: str
    duration_ms: float
    note: str = ""


class MemoryAccessTrace(BaseModel):
    model_config = ConfigDict(extra="allow")  # hits / op-specific extras
    op: str
    layer: str


class RouteTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = Field(default_factory=_utcnow)
    container: str
    subblocks: list[SubblockTrace] = Field(default_factory=list)
    memory_accesses: list[MemoryAccessTrace] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    extras: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.model_dump_json())


_LOCK = threading.Lock()


def write_trace(trace: RouteTrace, path: Path | str | None = None) -> Path:
    target = Path(path) if path is not None else _default_trace_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = trace.to_dict()
    with _LOCK:
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    return target


def trace_from_state(container: str, state, **metrics: float) -> RouteTrace:
    """Build a `RouteTrace` from a `BlockState` after execution.

    Accepted state attributes: `trace: list[SubblockTraceItem]`, `memory_accesses: list[dict]`.
    """
    subblocks = [
        SubblockTrace(name=t.name, type=t.type, duration_ms=float(t.duration_ms), note=t.note)
        for t in state.trace
    ]
    accesses: list[MemoryAccessTrace] = []
    for a in state.memory_accesses:
        if "op" in a and "layer" in a:
            accesses.append(MemoryAccessTrace(**a))
    return RouteTrace(
        container=container,
        subblocks=subblocks,
        memory_accesses=accesses,
        metrics={k: float(v) for k, v in metrics.items()},
    )
