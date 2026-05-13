"""EVO-04 Static Verifier tests."""

from __future__ import annotations

from llive.evolution.change_op import (
    InsertSubblock,
    RemoveSubblock,
    ReorderSubblocks,
    ReplaceSubblock,
)
from llive.evolution.verifier import Invariants, verify_diff
from llive.schema.models import ContainerSpec, SubBlockRef


def _container(types: list[str], cid: str = "t_v1") -> ContainerSpec:
    return ContainerSpec(
        schema_version=1,
        container_id=cid,
        subblocks=[SubBlockRef(type=t) for t in types],
    )


_MIN = ["pre_norm", "causal_attention", "ffn_swiglu"]


def test_empty_diff_passes_when_baseline_meets_invariants():
    res = verify_diff(_container(_MIN), ops=[])
    assert res.ok
    assert res.reasons == []


def test_insert_preserves_invariants_passes():
    base = _container(_MIN)
    ops = [InsertSubblock(target_container="t_v1", after="head", spec=SubBlockRef(type="memory_read", name="mr"))]
    # memory_read inserted without memory_write -> must fail
    res = verify_diff(base, ops)
    assert not res.ok
    assert any("memory_read present without memory_write" in r for r in res.reasons)


def test_insert_both_memory_passes():
    base = _container(_MIN)
    ops = [
        InsertSubblock(target_container="t_v1", after="head",
                       spec=SubBlockRef(type="memory_read", name="mr")),
        InsertSubblock(target_container="t_v1", after="mr",
                       spec=SubBlockRef(type="memory_write", name="mw")),
    ]
    res = verify_diff(base, ops)
    assert res.ok


def test_remove_essential_block_fails():
    base = _container(_MIN)
    ops = [RemoveSubblock(target_container="t_v1", target_subblock="causal_attention")]
    res = verify_diff(base, ops)
    assert not res.ok
    assert any("essential type 'causal_attention' would be absent" in r for r in res.reasons)


def test_replace_essential_with_other_attention_passes():
    base = _container(_MIN)
    ops = [
        ReplaceSubblock(
            target_container="t_v1",
            from_="causal_attention",
            to=SubBlockRef(type="grouped_query_attention", name="gqa"),
        )
    ]
    res = verify_diff(base, ops)
    # 'causal_attention' essential type missing -> fails structural
    assert not res.ok


def test_reorder_preserves_invariants():
    base = _container(_MIN)
    ops = [ReorderSubblocks(target_container="t_v1",
                            new_order=["ffn_swiglu", "causal_attention", "pre_norm"])]
    res = verify_diff(base, ops)
    assert res.ok


def test_max_blocks_violation_detected():
    base = _container(_MIN)
    inv = Invariants(max_blocks=4, min_blocks=1)
    ops = [
        InsertSubblock(target_container="t_v1", after="head", spec=SubBlockRef(type="memory_read", name="r1")),
        InsertSubblock(target_container="t_v1", after="r1", spec=SubBlockRef(type="memory_write", name="w1")),
    ]
    res = verify_diff(base, ops, invariants=inv)
    assert not res.ok
    assert any("max_blocks=4" in r for r in res.reasons)


def test_min_blocks_violation_detected():
    base = _container(_MIN)
    inv = Invariants(min_blocks=4, essential_types=())
    ops = []
    res = verify_diff(base, ops, invariants=inv)
    assert not res.ok
    assert any("min_blocks=4" in r for r in res.reasons)


def test_smt_used_when_z3_available_and_diff_passes():
    base = _container(_MIN)
    ops = [
        InsertSubblock(target_container="t_v1", after="head",
                       spec=SubBlockRef(type="memory_read", name="r1")),
        InsertSubblock(target_container="t_v1", after="r1",
                       spec=SubBlockRef(type="memory_write", name="w1")),
    ]
    res = verify_diff(base, ops, use_smt=True)
    assert res.ok
    # If z3 is installed, smt_used should flip True
    assert res.smt_used is True


def test_use_smt_false_skips_z3_layer():
    base = _container(_MIN)
    res = verify_diff(base, ops=[], use_smt=False)
    assert res.ok
    assert res.smt_used is False


def test_duplicate_name_detected():
    base = _container(_MIN)
    # forcibly insert a block whose name collides with an existing one
    base.subblocks[0] = SubBlockRef(type="pre_norm", name="dup")
    ops = [
        InsertSubblock(target_container="t_v1", after="head",
                       spec=SubBlockRef(type="memory_read", name="dup")),
        InsertSubblock(target_container="t_v1", after="dup",
                       spec=SubBlockRef(type="memory_write", name="mw")),
    ]
    res = verify_diff(base, ops, use_smt=False)
    assert not res.ok
    assert any("duplicate sub-block name" in r for r in res.reasons)
