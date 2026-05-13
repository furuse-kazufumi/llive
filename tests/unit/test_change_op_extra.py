"""Extra coverage for evolution/change_op.py error paths."""

from __future__ import annotations

import pytest

from llive.evolution.change_op import (
    ChangeOpError,
    InsertSubblock,
    RemoveSubblock,
    ReorderSubblocks,
    ReplaceSubblock,
    apply_diff,
    build_change_op,
)
from llive.schema.models import CandidateDiff, ContainerSpec, SubBlockRef
from llive.schema.validator import validate_candidate_diff


def _spec(cid="t_v1"):
    return ContainerSpec(
        schema_version=1,
        container_id=cid,
        subblocks=[
            SubBlockRef(type="pre_norm", name="a"),
            SubBlockRef(type="ffn_swiglu", name="b"),
        ],
    )


def test_apply_wrong_container_id():
    op = InsertSubblock(target_container="other", after="a", spec=SubBlockRef(type="pre_norm"))
    with pytest.raises(ChangeOpError):
        op.apply(_spec("t_v1"))


def test_remove_nonexistent_subblock():
    op = RemoveSubblock(target_container="t_v1", target_subblock="ghost")
    with pytest.raises(ChangeOpError):
        op.apply(_spec())


def test_replace_nonexistent_from():
    op = ReplaceSubblock(target_container="t_v1", from_="ghost", to=SubBlockRef(type="pre_norm"))
    with pytest.raises(ChangeOpError):
        op.apply(_spec())


def test_reorder_wrong_length():
    op = ReorderSubblocks(target_container="t_v1", new_order=["only-one"])
    with pytest.raises(ChangeOpError):
        op.apply(_spec())


def test_reorder_duplicate_or_missing_refs():
    op = ReorderSubblocks(target_container="t_v1", new_order=["a", "a"])
    with pytest.raises(ChangeOpError):
        op.apply(_spec())


def test_apply_diff_runs_in_sequence():
    spec = _spec()
    diff_dict = {
        "schema_version": 1,
        "candidate_id": "cand_20260513_900",
        "base_candidate": "t_v1",
        "changes": [
            {
                "action": "insert_subblock",
                "target_container": "t_v1",
                "after": "a",
                "spec": {"type": "memory_read", "name": "mem"},
            },
            {
                "action": "remove_subblock",
                "target_container": "t_v1",
                "target_subblock": "b",
            },
        ],
    }
    diff = validate_candidate_diff(diff_dict)
    out, ops = apply_diff(spec, diff)
    assert [s.type for s in out.subblocks] == ["pre_norm", "memory_read"]
    assert len(ops) == 2


def test_build_change_op_unknown_action(monkeypatch):
    class _Fake:
        action = "set_memory_policy"  # schema-reserved but not implemented in Phase 1
        memory_type = "semantic"
        policy = {}

    with pytest.raises(ChangeOpError):
        build_change_op(_Fake())


def test_insert_after_head():
    op = InsertSubblock(
        target_container="t_v1", after="head", spec=SubBlockRef(type="memory_read", name="m0")
    )
    new = op.apply(_spec())
    assert new.subblocks[0].name == "m0"
    inv = op.invert(_spec())
    assert isinstance(inv, RemoveSubblock)


def test_remove_invert_preserves_position():
    op = RemoveSubblock(target_container="t_v1", target_subblock="b")
    new = op.apply(_spec())
    assert [s.name for s in new.subblocks] == ["a"]
    inv = op.invert(_spec())
    restored = inv.apply(new)
    assert [s.name for s in restored.subblocks] == ["a", "b"]
