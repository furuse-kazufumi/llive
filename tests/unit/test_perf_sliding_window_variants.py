# SPDX-License-Identifier: Apache-2.0
"""Parity tests for sliding_window_variants."""
from __future__ import annotations

import pytest

from llive.perf.variants.sliding_window_variants import (
    ALL_VARIANTS,
    sliding_deque,
    sliding_list_popzero,
    sliding_list_slice,
)


@pytest.mark.parametrize(
    "initial,new_items,maxlen,expected",
    [
        ([], [1, 2, 3], 5, [1, 2, 3]),
        ([1, 2, 3], [4, 5], 3, [3, 4, 5]),
        ([1, 2, 3, 4, 5], [6, 7, 8], 3, [6, 7, 8]),
        ([1, 2], [], 5, [1, 2]),
        ([], [], 5, []),
        ([10, 20, 30, 40], [50, 60, 70], 2, [60, 70]),
    ],
)
def test_three_variants_agree(initial, new_items, maxlen, expected):
    r1 = sliding_list_popzero(initial, new_items, maxlen)
    r2 = sliding_list_slice(initial, new_items, maxlen)
    r3 = sliding_deque(initial, new_items, maxlen)
    assert r1 == expected
    assert r2 == expected
    assert r3 == expected


def test_initial_longer_than_maxlen_is_truncated():
    """initial が maxlen より長い場合は末尾 maxlen 件のみ."""
    initial = [1, 2, 3, 4, 5]
    r1 = sliding_list_popzero(initial, [], 3)
    r2 = sliding_list_slice(initial, [], 3)
    r3 = sliding_deque(initial, [], 3)
    assert r1 == [3, 4, 5]
    assert r2 == [3, 4, 5]
    assert r3 == [3, 4, 5]


def test_all_variants_listed():
    names = {name for name, _ in ALL_VARIANTS}
    assert names == {"list_popzero", "list_slice", "deque"}
