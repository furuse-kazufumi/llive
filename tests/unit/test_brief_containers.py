# SPDX-License-Identifier: Apache-2.0
"""Tests for COG-MESH-08 BriefDeque / BriefMap / BriefTree.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-08 の API 凍結。
"""

from __future__ import annotations

import pytest

from llive.cognitive_mesh.brief_containers import (
    BriefDeque,
    BriefMap,
    BriefRef,
    BriefTree,
)

# ---------------------------------------------------------------------------
# BriefDeque
# ---------------------------------------------------------------------------


def test_deque_push_front_pop_front() -> None:
    deque = BriefDeque()
    a = BriefRef.new("topic-a")
    b = BriefRef.new("topic-b")
    deque.push_front(a)
    deque.push_front(b)
    # b -> a の順 (front が新しい)
    assert deque.pop_front() == b
    assert deque.pop_front() == a
    assert len(deque) == 0


def test_deque_push_back_pop_back() -> None:
    deque = BriefDeque()
    a = BriefRef.new("topic-a")
    b = BriefRef.new("topic-b")
    deque.push_back(a)
    deque.push_back(b)
    # back が b
    assert deque.pop_back() == b
    assert deque.pop_back() == a


def test_deque_peek_does_not_remove() -> None:
    deque = BriefDeque([BriefRef.new("x"), BriefRef.new("y")])
    front = deque.peek_front()
    back = deque.peek_back()
    assert front is not None and front.topic == "x"
    assert back is not None and back.topic == "y"
    assert len(deque) == 2


def test_deque_contains_brief_and_id() -> None:
    a = BriefRef.new("topic-a")
    deque = BriefDeque([a])
    assert a in deque
    assert a.id in deque
    assert "nonexistent" not in deque


# ---------------------------------------------------------------------------
# BriefMap
# ---------------------------------------------------------------------------


def test_map_add_and_lookup_by_topic() -> None:
    bm = BriefMap()
    a = BriefRef.new("alpha")
    b = BriefRef.new("alpha")
    c = BriefRef.new("beta")
    bm.add(a)
    bm.add(b)
    bm.add(c)
    assert len(bm.by_topic("alpha")) == 2
    assert len(bm.by_topic("beta")) == 1
    assert set(bm.topics()) == {"alpha", "beta"}


def test_map_get_by_id() -> None:
    bm = BriefMap()
    a = BriefRef.new("topic")
    bm.add(a)
    assert bm.get(a.id) == a
    assert bm.get("nonexistent") is None


def test_map_remove() -> None:
    bm = BriefMap()
    a = BriefRef.new("alpha")
    b = BriefRef.new("alpha")
    bm.add(a)
    bm.add(b)
    removed = bm.remove(a.id)
    assert removed == a
    assert len(bm) == 1
    assert a.id not in bm
    assert b.id in bm


def test_map_rejects_duplicate_id() -> None:
    bm = BriefMap()
    a = BriefRef.new("x")
    bm.add(a)
    with pytest.raises(ValueError, match="already"):
        bm.add(a)


def test_map_remove_nonexistent_raises() -> None:
    bm = BriefMap()
    with pytest.raises(KeyError):
        bm.remove("nonexistent")


# ---------------------------------------------------------------------------
# BriefTree
# ---------------------------------------------------------------------------


def test_tree_add_root_and_branch() -> None:
    tree = BriefTree()
    root = BriefRef.new("root")
    child_a = BriefRef.new("child-a")
    child_b = BriefRef.new("child-b")
    tree.add_root(root)
    tree.branch(root.id, child_a)
    tree.branch(root.id, child_b)
    assert len(tree) == 3
    assert len(tree.children_of(root.id)) == 2
    assert tree.roots() == [root]


def test_tree_merge_children_returns_aggregated_brief() -> None:
    tree = BriefTree()
    root = BriefRef.new("root", payload={"data": "root"})
    child_a = BriefRef.new("child", payload={"data": "a"})
    child_b = BriefRef.new("child", payload={"data": "b"})
    tree.add_root(root)
    tree.branch(root.id, child_a)
    tree.branch(root.id, child_b)

    merged = tree.merge([child_a.id, child_b.id])
    assert merged.topic == "child"
    assert merged.payload["merged_from"] == [child_a.id, child_b.id]
    assert merged.payload["parent_id"] == root.id


def test_tree_merge_requires_common_parent() -> None:
    tree = BriefTree()
    root_a = BriefRef.new("root-a")
    root_b = BriefRef.new("root-b")
    tree.add_root(root_a)
    tree.add_root(root_b)
    ca = BriefRef.new("c")
    cb = BriefRef.new("c")
    tree.branch(root_a.id, ca)
    tree.branch(root_b.id, cb)
    with pytest.raises(ValueError, match="common parent"):
        tree.merge([ca.id, cb.id])


def test_tree_branch_from_unknown_parent_raises() -> None:
    tree = BriefTree()
    with pytest.raises(KeyError):
        tree.branch("nonexistent", BriefRef.new("c"))
