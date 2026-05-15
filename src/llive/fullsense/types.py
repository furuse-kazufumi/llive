"""Type definitions for FullSense Loop."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class ActionDecision(StrEnum):
    """Loop の終端で出る 4 種の決定。

    Sandbox では ``PROPOSE`` / ``INTERVENE`` も外向け副作用なしの log で完結する。
    本番ではこれらが TUI alert / MCP push / llove bridge へ流れる。
    """

    SILENT = "silent"        # 何もしない (most common)
    NOTE = "note"            # 内部ノート (episodic に追記)
    PROPOSE = "propose"      # 外向け提案 (sandbox: log only)
    INTERVENE = "intervene"  # 介入 (sandbox: log only、本番でも要 approve)


@dataclass
class Stimulus:
    """外乱 / 内乱 / 退屈タイマー由来の刺激。

    ``surprise`` が ``None`` なら Salience Gate 内で算出される。
    """

    content: str
    source: str = "manual"  # "sensor" / "user" / "idle" / "internal" / "manual"
    surprise: float | None = None
    timestamp: float = field(default_factory=time.time)
    stim_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class Thought:
    """Inner Monologue 出力 — 候補となる思考。"""

    text: str
    triz_principles: list[int] = field(default_factory=list)
    references: list[str] = field(default_factory=list)  # 関連 episodic / RAD path
    confidence: float = 0.5


@dataclass
class ActionPlan:
    """Loop 終端の action plan。"""

    decision: ActionDecision
    rationale: str
    ego_score: float = 0.0
    altruism_score: float = 0.0
    thought: Thought | None = None
