# SPDX-License-Identifier: Apache-2.0
"""Router decision + explanation log (RTR-02)."""

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


def _default_log_path() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "logs" / "router.jsonl"


class CandidateExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    container: str
    matched: bool
    reason: str = ""


class RouterExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = Field(default_factory=_utcnow)
    selected_container: str
    matched_rule: str
    candidates: list[CandidateExplanation] = Field(default_factory=list)
    prompt_features: dict[str, Any] = Field(default_factory=dict)


class RouterDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    container: str
    explanation: RouterExplanation


_LOG_LOCK = threading.Lock()


def append_explanation(explanation: RouterExplanation, path: Path | str | None = None) -> Path:
    log_path = Path(path) if path is not None else _default_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(explanation.model_dump_json())
    with _LOG_LOCK:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    return log_path
