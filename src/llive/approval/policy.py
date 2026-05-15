# SPDX-License-Identifier: Apache-2.0
"""ApprovalPolicy — Spec §AB の事前 gate 抽象.

Policy が `evaluate(req)` で `Verdict | None` を返す:
- `Verdict.APPROVED` → 自動承認 (e.g. allowlist hit)
- `Verdict.DENIED` → 自動拒否 (e.g. denylist hit)
- `None` → 人手 review に流す
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from llive.approval.bus import ApprovalRequest, Verdict


@runtime_checkable
class ApprovalPolicy(Protocol):
    """approval の事前判定 gate."""

    def evaluate(self, request: ApprovalRequest) -> Verdict | None:
        """request を評価し Verdict を返す. None なら人手 review."""
        ...


@dataclass(frozen=True)
class AllowList:
    """完全一致 / prefix で action を自動承認."""

    actions: frozenset[str]
    prefixes: tuple[str, ...] = ()

    @classmethod
    def of(cls, actions: Iterable[str], *, prefixes: Iterable[str] = ()) -> AllowList:
        return cls(frozenset(actions), tuple(prefixes))

    def evaluate(self, request: ApprovalRequest) -> Verdict | None:
        if request.action in self.actions:
            return Verdict.APPROVED
        for p in self.prefixes:
            if request.action.startswith(p):
                return Verdict.APPROVED
        return None


@dataclass(frozen=True)
class DenyList:
    """完全一致 / prefix で action を自動拒否."""

    actions: frozenset[str]
    prefixes: tuple[str, ...] = ()

    @classmethod
    def of(cls, actions: Iterable[str], *, prefixes: Iterable[str] = ()) -> DenyList:
        return cls(frozenset(actions), tuple(prefixes))

    def evaluate(self, request: ApprovalRequest) -> Verdict | None:
        if request.action in self.actions:
            return Verdict.DENIED
        for p in self.prefixes:
            if request.action.startswith(p):
                return Verdict.DENIED
        return None


@dataclass(frozen=True)
class CompositePolicy:
    """複数 policy を順次評価. 最初に Verdict を返した policy が勝つ.

    deny を先頭に置けば「deny-overrides」、allow を先頭に置けば「allow-overrides」.
    """

    policies: tuple[ApprovalPolicy, ...]

    @classmethod
    def of(cls, *policies: ApprovalPolicy) -> CompositePolicy:
        return cls(tuple(policies))

    def evaluate(self, request: ApprovalRequest) -> Verdict | None:
        for p in self.policies:
            verdict = p.evaluate(request)
            if verdict is not None:
                return verdict
        return None


def deny_overrides(allow: Sequence[str], deny: Sequence[str]) -> CompositePolicy:
    """deny を先に評価する典型構成."""
    return CompositePolicy.of(DenyList.of(deny), AllowList.of(allow))


__all__ = [
    "AllowList",
    "ApprovalPolicy",
    "CompositePolicy",
    "DenyList",
    "deny_overrides",
]
