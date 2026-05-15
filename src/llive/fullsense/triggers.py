"""Stimulus sources — 外乱 / 内乱 / 退屈タイマー."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

from llive.fullsense.types import Stimulus


class StimulusSource(Protocol):
    """Anything that produces ``Stimulus`` objects."""

    def poll(self) -> Stimulus | None:
        """Return a new stimulus if available, else ``None``."""
        ...


@dataclass
class IdleTrigger:
    """退屈タイマー: ``poll()`` が連続 N 回 ``None`` を返したら自発的に
    "what should I think about?" の internal stimulus を発火する。

    Sandbox での「外乱がない時に自分で考え始める」を実現する基本ピース。
    """

    threshold_seconds: float = 30.0
    payload: str = "(idle) no external stimulus recently — consider what to explore"
    last_active: float = field(default_factory=time.time)
    _fired_at: float = 0.0

    def mark_active(self) -> None:
        self.last_active = time.time()
        self._fired_at = 0.0

    def poll(self) -> Stimulus | None:
        now = time.time()
        if now - self.last_active < self.threshold_seconds:
            return None
        # debounce: don't refire within the threshold window
        if self._fired_at and now - self._fired_at < self.threshold_seconds:
            return None
        self._fired_at = now
        return Stimulus(content=self.payload, source="idle", surprise=0.5)


@dataclass
class QueuedStimulusSource:
    """Test/demo helper: a fixed list of stimuli, dequeued one at a time."""

    queue: list[Stimulus] = field(default_factory=list)

    def add(self, s: Stimulus) -> None:
        self.queue.append(s)

    def poll(self) -> Stimulus | None:
        if not self.queue:
            return None
        return self.queue.pop(0)


def drain(source: StimulusSource, *, max_items: int = 100) -> Iterator[Stimulus]:
    """Iterate stimuli from ``source`` until it returns ``None`` or limit hit."""
    for _ in range(max_items):
        s = source.poll()
        if s is None:
            return
        yield s
