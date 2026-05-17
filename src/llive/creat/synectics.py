# SPDX-License-Identifier: Apache-2.0
"""CREAT-05 — Synectics 類比エンジン (minimal prototype).

異分野の概念を借りてきて Brief の対象を捉え直す類比 (analogy) を生成する。
Gordon (1961) の Synectics 4 mechanism:

1. Direct analogy — 自然界 / 別分野からの直接類比
2. Personal analogy — 対象に自分が成り切る
3. Symbolic analogy — 圧縮表現 / 矛盾語
4. Fantasy analogy — 空想的解決

minimal prototype では deterministic な mock generator で 4 mechanism 各 1 件を
返す。LLM lens に差し替えるときは :class:`AnalogySource` Protocol を実装する。

`bind_ledger()` → `synectics_analogies_generated` event。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger
    from llive.brief.types import Brief


class AnalogyKind(StrEnum):
    DIRECT = "direct"
    PERSONAL = "personal"
    SYMBOLIC = "symbolic"
    FANTASY = "fantasy"


@dataclass(frozen=True)
class Analogy:
    analogy_id: str
    kind: AnalogyKind
    source_domain: str
    description: str
    bridge_terms: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "analogy_id": self.analogy_id,
            "kind": self.kind.value,
            "source_domain": self.source_domain,
            "description": self.description,
            "bridge_terms": list(self.bridge_terms),
        }


@dataclass(frozen=True)
class SynecticsReport:
    brief_id: str
    analogies: tuple[Analogy, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "brief_id": self.brief_id,
            "analogies": [a.to_payload() for a in self.analogies],
        }


class AnalogySource(Protocol):
    """1 つの mechanism について analogy 候補を返す Strategy."""

    kind: AnalogyKind

    def propose(self, target: str, *, brief: "Brief") -> Analogy:  # pragma: no cover
        ...


# Deterministic mock implementations — RAD 異分野コーパスに置き換える前提

_DIRECT_DOMAINS: tuple[tuple[str, str], ...] = (
    ("生物学", "免疫系のように、外乱を識別し選択的に応答する"),
    ("流体力学", "流れの抵抗を最小化するように経路を設計する"),
    ("光学", "焦点を絞ることで分解能を上げる"),
)


@dataclass(frozen=True)
class _DirectMock:
    kind: AnalogyKind = AnalogyKind.DIRECT

    def propose(self, target: str, *, brief: "Brief") -> Analogy:
        domain, desc = _DIRECT_DOMAINS[hash(target) % len(_DIRECT_DOMAINS)]
        return Analogy(
            analogy_id=f"an-direct-{brief.brief_id}",
            kind=self.kind,
            source_domain=domain,
            description=f"{desc} — 対象 ({target}) にも応用",
            bridge_terms=("選択", "識別") if "biolog" in domain.lower() or "生物" in domain else ("最適化",),
        )


@dataclass(frozen=True)
class _PersonalMock:
    kind: AnalogyKind = AnalogyKind.PERSONAL

    def propose(self, target: str, *, brief: "Brief") -> Analogy:
        return Analogy(
            analogy_id=f"an-personal-{brief.brief_id}",
            kind=self.kind,
            source_domain="一人称化",
            description=f"自分が {target} になりきった場合、どこに痛みを感じるか / どこを楽に感じるかを列挙する",
            bridge_terms=("痛点", "快適度"),
        )


@dataclass(frozen=True)
class _SymbolicMock:
    kind: AnalogyKind = AnalogyKind.SYMBOLIC

    def propose(self, target: str, *, brief: "Brief") -> Analogy:
        return Analogy(
            analogy_id=f"an-symbolic-{brief.brief_id}",
            kind=self.kind,
            source_domain="圧縮表現",
            description=f"対象 ({target}) を矛盾語で表すと: 「静かな雷」「重い軽量化」のように両極を 1 語に詰める",
            bridge_terms=("矛盾語", "圧縮"),
        )


@dataclass(frozen=True)
class _FantasyMock:
    kind: AnalogyKind = AnalogyKind.FANTASY

    def propose(self, target: str, *, brief: "Brief") -> Analogy:
        return Analogy(
            analogy_id=f"an-fantasy-{brief.brief_id}",
            kind=self.kind,
            source_domain="空想的解決",
            description=f"魔法が使えるなら {target} をどう解決するか — 物理的制約を外して理想形を描き、後で制約を戻す",
            bridge_terms=("理想形", "制約緩和"),
        )


_DEFAULT_SOURCES: tuple[AnalogySource, ...] = (
    _DirectMock(), _PersonalMock(), _SymbolicMock(), _FantasyMock(),
)


class SynecticsEngine:
    """Brief → 4 mechanism × 1 analogy = 4 件の analogies (deterministic mock)."""

    def __init__(
        self,
        *,
        sources: tuple[AnalogySource, ...] | None = None,
        ledger: "BriefLedger | None" = None,
    ) -> None:
        self._sources = sources or _DEFAULT_SOURCES
        self._ledger = ledger

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        self._ledger = ledger

    def generate(self, brief: "Brief") -> SynecticsReport:
        target = brief.goal
        analogies = tuple(s.propose(target, brief=brief) for s in self._sources)
        report = SynecticsReport(brief_id=brief.brief_id, analogies=analogies)
        if self._ledger is not None:
            self._ledger.append("synectics_analogies_generated", report.to_payload())
        return report


__all__ = [
    "Analogy",
    "AnalogyKind",
    "AnalogySource",
    "SynecticsEngine",
    "SynecticsReport",
]
