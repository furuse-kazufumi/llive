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
from enum import StrEnum
from typing import Any, Protocol


class GrammarChangeSink(Protocol):
    """GrammarLayer の promote/reject イベント通知 sink.

    Phase 7 で EVO-04/06/07 (Self-evolution) との配線用 hook。
    本 sink を `GrammarLayer(change_sink=...)` に注入すると、各操作で
    sink.on_promote(...) / sink.on_reject(...) が呼ばれる.
    """

    def on_propose(self, proposal: "ProposedChange") -> None: ...

    def on_promote(
        self, proposal: "ProposedChange", new_snapshot: "GrammarSnapshot"
    ) -> None: ...

    def on_reject(self, proposal: "ProposedChange") -> None: ...


# 言語別 preset (jp/en/zh/ko) の bootstrap 用キー。Phase 7 で各言語の
# 実用文法を取り込む際の anchor。
DEFAULT_LANGUAGES: tuple[str, ...] = ("ja", "en", "zh", "ko")


class GrammarChangeStatus(StrEnum):
    PROPOSED = "proposed"
    PROMOTED = "promoted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class GrammarSnapshot:
    """ある時点の文法スナップショット (immutable)."""

    language: str
    version: str  # 例: "grammar_v_2026_05"
    rules: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class UsageEvidence:
    """新しい用法の観測証拠 (例: ある単語が動詞として使われ始めた)."""

    pattern: str
    samples: list[str]
    confidence: float = 0.5
    observed_at: datetime | None = None


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

    Attributes:
        change_sink: M8.9 で導入された optional な sink. propose / promote /
            reject の各イベントで通知される (EVO-04/06/07 配線用 hook).
    """

    change_sink: GrammarChangeSink | None = None
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

    def get(self, language: str, version: str) -> GrammarSnapshot | None:
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
        if self.change_sink is not None:
            try:
                self.change_sink.on_propose(proposal)
            except Exception:  # noqa: BLE001 — sink 失敗は本処理を止めない
                pass
        return proposal

    def pending_proposals(self, language: str | None = None) -> list[ProposedChange]:
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
        if self.change_sink is not None:
            try:
                self.change_sink.on_promote(proposal, new_snapshot)
            except Exception:  # noqa: BLE001
                pass
        return new_snapshot

    def reject(self, proposal: ProposedChange) -> None:
        if proposal not in self._proposals:
            raise ValueError("proposal not tracked by this GrammarLayer")
        proposal.status = GrammarChangeStatus.REJECTED
        if self.change_sink is not None:
            try:
                self.change_sink.on_reject(proposal)
            except Exception:  # noqa: BLE001
                pass


@dataclass
class MultilingualGrammar:
    """言語別 (ja/en/zh/ko) preset を bootstrap する GrammarLayer ファサード.

    M8.9 で導入。`DEFAULT_LANGUAGES` 全 4 言語で v0 snapshot を空 rules で
    生成し、GrammarLayer を提供する。
    Phase 7 で各言語の実用文法 (jp 学校文法 / en POS / zh 词法 / ko 형태소)
    を取り込む際の anchor。

    Attributes:
        layer: 内包する GrammarLayer.
        base_version: bootstrap 時の version 文字列 (既定 ``"v_0"``).
        change_sink: GrammarLayer に渡す sink (Phase 7 で EVO 接続).
    """

    layer: GrammarLayer = field(default_factory=GrammarLayer)
    base_version: str = "v_0"
    change_sink: GrammarChangeSink | None = None
    languages: tuple[str, ...] = DEFAULT_LANGUAGES

    def __post_init__(self) -> None:
        if self.change_sink is not None and self.layer.change_sink is None:
            self.layer.change_sink = self.change_sink
        for lang in self.languages:
            if not self.layer.versions(lang):
                self.layer.add_snapshot(
                    GrammarSnapshot(
                        language=lang,
                        version=self.base_version,
                        rules={},
                        created_at=datetime.now(),
                    )
                )

    def propose(
        self, language: str, pattern: str, evidence: UsageEvidence
    ) -> ProposedChange:
        """言語に対する直近 version を base に proposal 作成 (短縮 helper)."""
        if language not in self.languages:
            raise KeyError(
                f"language '{language}' not in bootstrap set {self.languages!r}"
            )
        versions = self.layer.versions(language)
        if not versions:
            raise RuntimeError(f"no snapshot for language '{language}'")
        return self.layer.propose_change(
            language=language,
            base_version=versions[-1],
            pattern=pattern,
            evidence=evidence,
        )

    def promote(self, proposal: ProposedChange, new_version: str) -> GrammarSnapshot:
        return self.layer.promote(proposal, new_version)

    def reject(self, proposal: ProposedChange) -> None:
        self.layer.reject(proposal)

    def latest_version(self, language: str) -> str | None:
        versions = self.layer.versions(language)
        return versions[-1] if versions else None


@dataclass
class InMemoryGrammarChangeSink:
    """テスト / 監査用の in-memory sink. 受け取った event を順番に保持."""

    proposes: list[ProposedChange] = field(default_factory=list)
    promotes: list[tuple[ProposedChange, GrammarSnapshot]] = field(default_factory=list)
    rejects: list[ProposedChange] = field(default_factory=list)

    def on_propose(self, proposal: ProposedChange) -> None:
        self.proposes.append(proposal)

    def on_promote(
        self, proposal: ProposedChange, new_snapshot: GrammarSnapshot
    ) -> None:
        self.promotes.append((proposal, new_snapshot))

    def on_reject(self, proposal: ProposedChange) -> None:
        self.rejects.append(proposal)


__all__ = [
    "DEFAULT_LANGUAGES",
    "GrammarChangeSink",
    "GrammarChangeStatus",
    "GrammarLayer",
    "GrammarSnapshot",
    "InMemoryGrammarChangeSink",
    "MultilingualGrammar",
    "ProposedChange",
    "UsageEvidence",
]
