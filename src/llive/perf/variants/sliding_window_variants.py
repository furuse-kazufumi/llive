# SPDX-License-Identifier: Apache-2.0
"""Sliding window container variants.

llive memory tier の "recent N events" 系コンテナで頻出する操作:

    1) 末尾に新規 element を push
    2) サイズが N を超えていたら先頭を pop して維持

この「先頭 pop + 末尾 push」を **N 回連続で行う** hot path の variants を
3 通り提供する:

- ``sliding_list_popzero``    — `list.pop(0)` + `list.append()`. O(N) pop.
- ``sliding_list_slice``      — `lst[1:] + [new]`. O(N) slice.
- ``sliding_deque``           — `collections.deque(maxlen=N).append()`. O(1).

signature: ``(initial: Iterable[int], new_items: Iterable[int], maxlen: int) -> list[int]``

実装ごとの計算量:
    list.pop(0)  : O(N)  (left-shift)
    list[1:]+[]  : O(N)  (copy)
    deque        : O(1)  (linked-list ring)

production hot path には注入しない (demo + benchmark のみ).
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Any, Callable

__all__ = [
    "sliding_list_popzero",
    "sliding_list_slice",
    "sliding_deque",
    "ALL_VARIANTS",
]


def sliding_list_popzero(
    initial: Iterable[int], new_items: Iterable[int], maxlen: int
) -> list[int]:
    window: list[int] = list(initial)[-maxlen:]
    for x in new_items:
        window.append(x)
        if len(window) > maxlen:
            window.pop(0)
    return window


def sliding_list_slice(
    initial: Iterable[int], new_items: Iterable[int], maxlen: int
) -> list[int]:
    window: list[int] = list(initial)[-maxlen:]
    for x in new_items:
        window = window[1:] + [x] if len(window) >= maxlen else window + [x]
    return window


def sliding_deque(
    initial: Iterable[int], new_items: Iterable[int], maxlen: int
) -> list[int]:
    window: deque = deque(initial, maxlen=maxlen)
    for x in new_items:
        window.append(x)
    return list(window)


ALL_VARIANTS: tuple[tuple[str, Callable[..., list[int]]], ...] = (
    ("list_popzero", sliding_list_popzero),
    ("list_slice", sliding_list_slice),
    ("deque", sliding_deque),
)
