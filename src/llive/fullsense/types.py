# SPDX-License-Identifier: Apache-2.0
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


class EpistemicType(StrEnum):
    """Stimulus の真理タイプ — Multi-track Filter Architecture (A-1.5).

    Spec §F* 章の MAY-clause 「Implementations MAY add filters between
    named ones」を実装した拡張軸。track ごとに異なる filter chain を選ぶ
    ことで、結論不変な FACTUAL と perspective-dependent な INTERPRETIVE を
    crude に混ぜずに済む。

    RESERVED_1..5 は将来拡張用予備層 (§5 拡張余地)。MUST NOT remove or
    reorder named ones の縛りを侵さずに新 track を追加できる。
    """

    FACTUAL = "factual"            # 結論不変 (consistency-first)
    EMPIRICAL = "empirical"        # 科学的事実 (evidence weighting)
    NORMATIVE = "normative"        # 倫理判断 (§F5 ethical 優先)
    INTERPRETIVE = "interpretive"  # 歴史認識など perspective-dependent
    PRAGMATIC = "pragmatic"        # 建前 / 社交 (audience-aware framing)
    RESERVED_1 = "reserved_1"
    RESERVED_2 = "reserved_2"
    RESERVED_3 = "reserved_3"
    RESERVED_4 = "reserved_4"
    RESERVED_5 = "reserved_5"


@dataclass
class Stimulus:
    """外乱 / 内乱 / 退屈タイマー由来の刺激。

    ``surprise`` が ``None`` なら Salience Gate 内で算出される。
    ``epistemic_type`` を指定すると Multi-track Filter Architecture で
    track 別の filter chain が選ばれる (未指定 = default track = 既存挙動)。
    """

    content: str
    source: str = "manual"  # "sensor" / "user" / "idle" / "internal" / "manual"
    surprise: float | None = None
    timestamp: float = field(default_factory=time.time)
    stim_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    epistemic_type: EpistemicType | None = None


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
