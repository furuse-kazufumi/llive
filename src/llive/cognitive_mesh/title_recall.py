# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-02 TitleRecallPlanner — 起承転結 + 伏線回収採点.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-02 の最小実装。

ユーザ言語化「起承転結 + オチ + ブランチメッシュ + 伏線回収・タイトル回収が
面白い話を成立させる」(user_cognitive_mesh_model §13) を実装に落とす。

仕様:
- 起 (setup) 段で伏線 (Foreshadow) を Annotation Channel に積む
- 結 (closure) 段で recall_rate を採点 (0..1)
- 採点根拠:
  - 伏線 token が最終出力テキストに出現 → 1.0
  - 伏線 ⇔ 最終出力 の semantic 類似度 (本実装では token 含有率) → 0..1
- Annotation namespace: cog.foreshadow_set / cog.foreshadow_recovered
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

# 採点しきい値: similarity ベース。token match のみだったとき 0.5 で運用
# していたので継続する (回帰回避)。
_RECOVERY_THRESHOLD = 0.5


class RecallStatus(StrEnum):
    PENDING = "pending"
    RECOVERED = "recovered"
    MISSED = "missed"


@dataclass
class Foreshadow:
    """起段で立てる伏線."""

    text: str
    tag: str  # 識別用タグ (例: "build-success", "user-name", ...)
    weight: float = 1.0  # 採点時の重み
    status: RecallStatus = RecallStatus.PENDING
    set_at: datetime | None = None
    recovered_at: datetime | None = None


@dataclass
class RecallReport:
    """closure 段で生成する採点レポート."""

    recall_rate: float
    total_weight: float
    recovered_weight: float
    foreshadows: list[Foreshadow] = field(default_factory=list)
    unrecovered: list[Foreshadow] = field(default_factory=list)


@dataclass
class TitleRecallPlanner:
    """起承転結 + 伏線回収を管理する.

    Attributes:
        similarity_fn: 注入可能な (foreshadow_text, final_text) -> float ∈ [0, 1]
            の callable。未指定なら従来の token match のみで採点。指定された
            場合は token match との max を取って採点する (token で確実に
            拾えるケースを潰さない fail-safe 設計)。
    """

    similarity_fn: Callable[[str, str], float] | None = None
    _foreshadows: dict[str, Foreshadow] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 起 — 伏線設置
    # ------------------------------------------------------------------

    def setup(self, text: str, tag: str, weight: float = 1.0, now: datetime | None = None) -> Foreshadow:
        if tag in self._foreshadows:
            raise ValueError(f"foreshadow with tag '{tag}' already set")
        if now is None:
            now = datetime.now()
        fs = Foreshadow(
            text=text,
            tag=tag,
            weight=weight,
            status=RecallStatus.PENDING,
            set_at=now,
        )
        self._foreshadows[tag] = fs
        return fs

    def pending(self) -> list[Foreshadow]:
        return [f for f in self._foreshadows.values() if f.status == RecallStatus.PENDING]

    def all_foreshadows(self) -> list[Foreshadow]:
        return list(self._foreshadows.values())

    # ------------------------------------------------------------------
    # 結 — 採点
    # ------------------------------------------------------------------

    def evaluate(self, final_text: str, now: datetime | None = None) -> RecallReport:
        if now is None:
            now = datetime.now()
        total_weight = 0.0
        recovered_weight = 0.0
        unrecovered: list[Foreshadow] = []
        lower_final = final_text.lower()
        for fs in self._foreshadows.values():
            total_weight += fs.weight
            score = self._token_match_score(fs.text, lower_final)
            if score >= 0.5:
                fs.status = RecallStatus.RECOVERED
                fs.recovered_at = now
                recovered_weight += fs.weight * score
            else:
                fs.status = RecallStatus.MISSED
                unrecovered.append(fs)
        recall_rate = (recovered_weight / total_weight) if total_weight > 0 else 0.0
        return RecallReport(
            recall_rate=min(1.0, recall_rate),
            total_weight=total_weight,
            recovered_weight=recovered_weight,
            foreshadows=list(self._foreshadows.values()),
            unrecovered=unrecovered,
        )

    def unrecovered_foreshadows(self) -> list[Foreshadow]:
        """評価後に残った回収漏れ."""
        return [f for f in self._foreshadows.values() if f.status == RecallStatus.MISSED]

    # ------------------------------------------------------------------
    # 内部: token-based 類似度
    # ------------------------------------------------------------------

    @staticmethod
    def _token_match_score(foreshadow_text: str, lower_final: str) -> float:
        """伏線テキストの token (空白分割) が最終出力にどれだけ含まれるか."""
        tokens = [t.lower() for t in foreshadow_text.split() if t]
        if not tokens:
            return 0.0
        matched = sum(1 for t in tokens if t in lower_final)
        return matched / len(tokens)
