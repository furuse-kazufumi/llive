# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-08 完成配線 — BriefDeque ↔ BriefRunner.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-08 で予告した
「実 Brief / BriefRunner との接続」を行う adapter。

設計:
- BriefDeque は軽量 BriefRef (id/topic/payload) を保持する STL コンテナ。
- BriefRunner は重い Brief (goal/tools/ledger) を submit する driver。
- 橋渡し: ``BriefDequeRunnerBridge.enqueue(brief)`` で Brief を BriefRef に
  ラップして deque に積み、``submit_next()`` で先頭を取り出して
  BriefRunner.submit() に流す。
- 既存 BriefDeque を継承せず、composition で薄く包む (テストで mock 化が
  しやすい)。

設計上の選択:
- BriefRef.payload に Brief 本体を入れる (id/topic は brief.brief_id /
  brief.goal を流用)。Brief は frozen dataclass なので参照保持で安全。
- submit_next() は deque が空のとき None。例外は upstream に伝播。
- submit_all() は順序保持で全件処理し、各 BriefResult を順番に返す。途中
  例外発生時は残りを処理しない (fail-fast)。Brief 単位の resilience が
  必要なら caller が try/except を挟む方針。
- BriefRunner duck-typing: ``submit(brief: Brief) -> BriefResult`` を持つ
  任意オブジェクトを受ける (テストで簡易 fake を差し込みやすい)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from llive.cognitive_mesh.brief_containers import BriefDeque, BriefRef

if TYPE_CHECKING:
    from llive.brief.types import Brief, BriefResult


class _BriefRunnerLike(Protocol):
    def submit(self, brief: Brief) -> BriefResult: ...


@dataclass
class BriefDequeRunnerBridge:
    """BriefDeque から取り出した Brief を BriefRunner に流す bridge.

    Attributes:
        runner: ``submit(brief) -> BriefResult`` を持つ任意 driver
            (本物の BriefRunner / テスト用 fake どちらでも可).
        deque: 紐づける BriefDeque. 省略時は新規生成.
    """

    runner: _BriefRunnerLike
    deque: BriefDeque = field(default_factory=BriefDeque)

    def enqueue(self, brief: Brief) -> BriefRef:
        """Brief を BriefRef にラップして deque の末尾に push.

        Returns:
            積まれた BriefRef (id = brief.brief_id, topic = brief.goal).
        """
        ref = BriefRef(id=brief.brief_id, topic=brief.goal, payload=brief)
        self.deque.push_back(ref)
        return ref

    def enqueue_front(self, brief: Brief) -> BriefRef:
        """優先度高め Brief を deque の先頭に push (緊急介入用)."""
        ref = BriefRef(id=brief.brief_id, topic=brief.goal, payload=brief)
        self.deque.push_front(ref)
        return ref

    def submit_next(self) -> BriefResult | None:
        """deque の先頭を pop し、payload の Brief を runner に submit.

        Returns:
            BriefResult (deque 非空時) または None (空時).
        """
        if len(self.deque) == 0:
            return None
        ref = self.deque.pop_front()
        brief = ref.payload
        if brief is None:
            raise ValueError(f"BriefRef {ref.id!r} has no Brief payload")
        return self.runner.submit(brief)

    def submit_all(self) -> list[BriefResult]:
        """deque の全件を順番に submit. fail-fast (途中例外で停止)."""
        results: list[BriefResult] = []
        while len(self.deque) > 0:
            result = self.submit_next()
            if result is None:  # 並行操作で空になった
                break
            results.append(result)
        return results

    def pending_count(self) -> int:
        return len(self.deque)

    def peek_next(self) -> BriefRef | None:
        return self.deque.peek_front()


__all__ = ["BriefDequeRunnerBridge"]
