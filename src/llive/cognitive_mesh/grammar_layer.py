# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-09 GrammarLayer — 継続学習対象としての文法層 (skeleton).

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-09 の Phase 7 skeleton.

ユーザ言語化「世界中の言語に文法があるので、そこをどうモデルに持たせるかが
大事。それも時代によって変化があるので、常に学習だと思います」
(user_cognitive_mesh_model 追記 23:00) を実装に落とす。

仕様:
- GrammarSnapshot: ある言語 × 時点での文法状態 (バージョン付き)
- ProposedChange: 新しい用法観測から提案された文法変更
- GrammarLayer: 言語別 (ja / en / zh / ko) に Snapshot を保持、
  propose / promote (EVO-04/06/07 と接続予定)
- 本実装は API 凍結のみ、内部は dict 簡易管理。形式検証統合は Phase 7。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class GrammarChangeStatus(str, Enum):
    PROPOSED = "proposed"
    PROMOTED = "promoted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class GrammarSnapshot:
    """ある時点の文法スナップショット (immutable)."""

    language: str
    version: str  # 例: "grammar_v_2026_05"
    rules: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass
class UsageEvidence:
    """新しい用法の観測証拠 (例: ある単語が動詞として使われ始めた)."""

    pattern: str
    samples: list[str]
    confidence: float = 0.5
    observed_at: Optional[datetime] = None


@dataclass
class ProposedChange:
    """文法変更の提案."""

    language: str
    base_version: str
    pattern: str
    evidence: UsageEvidence
    status: GrammarChangeStatus = GrammarChangeStatus.PROPOSED


@dataclass
class GrammarLayer:
    """言語別の文法層を管理する skeleton.

    Phase 7 で本実装。本クラスは API を凍結し、内部は dict 簡易管理。
    """

    _versions: dict[str, dict[str, GrammarSnapshot]] = field(default_factory=dict)
    _proposals: list[ProposedChange] = field(default_factory=list)

    # ------------------------------------------------------------------
    # snapshot 管理
    # ------------------------------------------------------------------

    def add_snapshot(self, snapshot: GrammarSnapshot) -> None:
        lang_map = self._versions.setdefault(snapshot.language, {})
        if snapshot.version in lang_map:
            raise ValueError(
                f"Grammar version '{snapshot.version}' already exists for "
                f"language '{snapshot.language}'"
            )
        lang_map[snapshot.version] = snapshot

    def get(self, language: str, version: str) -> Optional[GrammarSnapshot]:
        return self._versions.get(language, {}).get(version)

    def versions(self, language: str) -> list[str]:
        return sorted(self._versions.get(language, {}).keys())

    def languages(self) -> list[str]:
        return sorted(self._versions.keys())

    # ------------------------------------------------------------------
    # 提案 / 昇格
    # ------------------------------------------------------------------

    def propose_change(
        self,
        language: str,
        base_version: str,
        pattern: str,
        evidence: UsageEvidence,
    ) -> ProposedChange:
        if base_version not in self._versions.get(language, {}):
            raise KeyError(
                f"base_version '{base_version}' not found for language '{language}'"
            )
        proposal = ProposedChange(
            language=language,
            base_version=base_version,
            pattern=pattern,
            evidence=evidence,
        )
        self._proposals.append(proposal)
        return proposal

    def pending_proposals(self, language: Optional[str] = None) -> list[ProposedChange]:
        items = [p for p in self._proposals if p.status == GrammarChangeStatus.PROPOSED]
        if language is not None:
            items = [p for p in items if p.language == language]
        return items

    def promote(self, proposal: ProposedChange, new_version: str) -> GrammarSnapshot:
        """提案を新しい GrammarSnapshot に昇格させる.

        Phase 7 で形式検証 (EVO-04) と接続予定。本実装では rules に
        pattern を追加するだけの最小処理。
        """
        if proposal not in self._proposals:
            raise ValueError("proposal not tracked by this GrammarLayer")
        if proposal.status != GrammarChangeStatus.PROPOSED:
            raise ValueError(
                f"proposal status must be PROPOSED, got {proposal.status}"
            )
        base = self.get(proposal.language, proposal.base_version)
        if base is None:
            raise KeyError(f"base snapshot not found: {proposal.base_version}")
        new_rules = dict(base.rules)
        new_rules[proposal.pattern] = {
            "evidence_pattern": proposal.evidence.pattern,
            "samples": list(proposal.evidence.samples),
            "confidence": proposal.evidence.confidence,
        }
        new_snapshot = GrammarSnapshot(
            language=proposal.language,
            version=new_version,
            rules=new_rules,
            created_at=datetime.now(),
        )
        self.add_snapshot(new_snapshot)
        proposal.status = GrammarChangeStatus.PROMOTED
        return new_snapshot

    def reject(self, proposal: ProposedChange) -> None:
        if proposal not in self._proposals:
            raise ValueError("proposal not tracked by this GrammarLayer")
        proposal.status = GrammarChangeStatus.REJECTED
