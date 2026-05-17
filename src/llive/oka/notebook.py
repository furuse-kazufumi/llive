# SPDX-License-Identifier: Apache-2.0
"""OKA-04 — Reflective Notebook Memory.

岡潔「文章を書くことなしには思索を進めることはできない」を実装に置き換えた
研究ノート。中間式 / 失敗試行 / 気づき / 未解決疑問を構造化 JSON で長期保持し、
同系列の問題で再利用できるようにする。

設計:

* :class:`ReflectiveNote` — 1 件のノート (frozen dataclass)
* :class:`ReflectiveNotebook` — JSON Lines への append-only 永続層
* COG-08 来歴と直交した「思索の堆積」を担う — ledger は「決定の audit」、
  notebook は「思索の素材」
* :class:`BriefLedger` への自動連動: ``bind_ledger`` で attach → 各 append で
  ``oka_notebook_appended`` event が ledger にも残る

トレーサビリティの責務分離:

* notebook = 内容 (失敗の本文・気づき・反例)
* ledger = いつ何が追加されたかの index (event + meta)

両者が並行することで、後で「あの Brief の途中で書かれたノート N 件」を高速に
逆引きできる + ノート本文は cross-Brief で蓄積され続ける。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger


# Closed enum of note kinds — keep small so cross-Brief filtering stays clean.
_NOTE_KINDS: tuple[str, ...] = (
    "intermediate",   # 中間式 / 部分結果
    "failed_attempt", # 行き詰まった試み
    "insight",        # 気づき
    "open_question",  # 未解決疑問
    "reframing",      # 視点の変更
)


@dataclass(frozen=True)
class ReflectiveNote:
    """One entry in a :class:`ReflectiveNotebook`."""

    note_id: str
    brief_id: str
    kind: str
    body: str
    tags: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.kind not in _NOTE_KINDS:
            raise ValueError(f"kind must be one of {_NOTE_KINDS}, got {self.kind!r}")
        if not self.body.strip():
            raise ValueError("body must be a non-empty string")

    def to_payload(self) -> dict[str, object]:
        return {
            "note_id": self.note_id,
            "brief_id": self.brief_id,
            "kind": self.kind,
            "body": self.body,
            "tags": list(self.tags),
            "created_at": self.created_at,
        }


class ReflectiveNotebook:
    """Append-only JSONL notebook with optional ledger fan-out.

    The notebook is keyed by a single file path so a project can keep one
    notebook per researcher / per topic. Cross-Brief reuse is the point —
    a Brief that fails for reason X today should be able to surface notes
    from previous Briefs that hit the same wall.
    """

    _ENCODING = "utf-8"

    def __init__(self, path: Path, *, ledger: "BriefLedger | None" = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ledger = ledger

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        """Re-target the audit sink (mirrors MathVerifier / Essence patterns)."""
        self._ledger = ledger

    def append(
        self,
        *,
        brief_id: str,
        kind: str,
        body: str,
        tags: tuple[str, ...] = (),
    ) -> ReflectiveNote:
        note = ReflectiveNote(
            note_id=uuid.uuid4().hex,
            brief_id=brief_id,
            kind=kind,
            body=body,
            tags=tags,
        )
        line = json.dumps(note.to_payload(), ensure_ascii=False, sort_keys=True)
        with self._lock:
            with self.path.open("a", encoding=self._ENCODING) as fh:
                fh.write(line + "\n")
        if self._ledger is not None:
            self._ledger.append("oka_notebook_appended", note.to_payload())
        return note

    def read(self) -> Iterator[ReflectiveNote]:
        if not self.path.is_file():
            return
        with self.path.open("r", encoding=self._ENCODING) as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                obj = json.loads(raw)
                yield ReflectiveNote(
                    note_id=obj["note_id"],
                    brief_id=obj["brief_id"],
                    kind=obj["kind"],
                    body=obj["body"],
                    tags=tuple(obj.get("tags", []) or ()),
                    created_at=float(obj.get("created_at", 0.0)),
                )

    # -- query API ----------------------------------------------------------

    def find(self, *, kind: str | None = None, tag: str | None = None) -> list[ReflectiveNote]:
        """Linear filter — fine for v0.7 size (< 10k notes)."""
        out: list[ReflectiveNote] = []
        for n in self.read():
            if kind is not None and n.kind != kind:
                continue
            if tag is not None and tag not in n.tags:
                continue
            out.append(n)
        return out

    def related_to(self, problem_text: str, *, max_results: int = 5) -> list[ReflectiveNote]:
        """Cross-Brief reuse — naive substring keyword match.

        v0.7 keeps it deterministic; embedding-based retrieval slots in later
        as a Strategy without changing the call signature.
        """
        tokens = [t.lower() for t in problem_text.split() if len(t) >= 3]
        scored: list[tuple[int, ReflectiveNote]] = []
        for n in self.read():
            body_low = n.body.lower()
            score = sum(1 for t in tokens if t in body_low)
            if score > 0:
                scored.append((score, n))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [n for _, n in scored[:max_results]]
