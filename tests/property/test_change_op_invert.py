"""EVO-02 property tests: apply ∘ invert is identity for the 4 Phase 1 ChangeOps."""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from llive.evolution.change_op import (
    InsertSubblock,
    RemoveSubblock,
    ReorderSubblocks,
    ReplaceSubblock,
)
from llive.schema.models import ContainerSpec, SubBlockRef

SUBBLOCK_TYPES = ["pre_norm", "causal_attention", "ffn_swiglu", "memory_read", "memory_write"]


def _make_container(types: list[str], names: list[str | None]) -> ContainerSpec:
    refs = [SubBlockRef(type=t, name=n) for t, n in zip(types, names)]
    return ContainerSpec(schema_version=1, container_id="adaptive_reasoning_v1", subblocks=refs)


def _normalize(spec: ContainerSpec) -> list[tuple[str, str | None]]:
    return [(r.type, r.name) for r in spec.subblocks]


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
@given(
    types=st.lists(st.sampled_from(SUBBLOCK_TYPES), min_size=2, max_size=6),
    insert_type=st.sampled_from(SUBBLOCK_TYPES),
    insert_name=st.text(alphabet="abcdef", min_size=3, max_size=5).map(lambda s: f"new_{s}"),
)
def test_insert_invert_is_identity(types, insert_type, insert_name):
    names = [f"sb_{i}" for i in range(len(types))]
    spec = _make_container(types, names)
    op = InsertSubblock(
        target_container="adaptive_reasoning_v1",
        after=names[0],
        spec=SubBlockRef(type=insert_type, name=insert_name),
    )
    applied = op.apply(spec)
    restored = op.invert(spec).apply(applied)
    assert _normalize(restored) == _normalize(spec)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
@given(types=st.lists(st.sampled_from(SUBBLOCK_TYPES), min_size=2, max_size=6))
def test_remove_invert_is_identity(types):
    names = [f"sb_{i}" for i in range(len(types))]
    spec = _make_container(types, names)
    op = RemoveSubblock(target_container="adaptive_reasoning_v1", target_subblock=names[-1])
    applied = op.apply(spec)
    restored = op.invert(spec).apply(applied)
    assert _normalize(restored) == _normalize(spec)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
@given(
    types=st.lists(st.sampled_from(SUBBLOCK_TYPES), min_size=2, max_size=6),
    new_type=st.sampled_from(SUBBLOCK_TYPES),
    new_name=st.text(alphabet="xyz", min_size=2, max_size=4).map(lambda s: f"rep_{s}"),
)
def test_replace_invert_is_identity(types, new_type, new_name):
    names = [f"sb_{i}" for i in range(len(types))]
    spec = _make_container(types, names)
    op = ReplaceSubblock(
        target_container="adaptive_reasoning_v1",
        from_=names[0],
        to=SubBlockRef(type=new_type, name=new_name),
    )
    applied = op.apply(spec)
    restored = op.invert(spec).apply(applied)
    assert _normalize(restored) == _normalize(spec)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
@given(types=st.lists(st.sampled_from(SUBBLOCK_TYPES), min_size=2, max_size=6))
def test_reorder_invert_is_identity(types):
    names = [f"sb_{i}" for i in range(len(types))]
    spec = _make_container(types, names)
    # reverse order
    op = ReorderSubblocks(target_container="adaptive_reasoning_v1", new_order=list(reversed(names)))
    applied = op.apply(spec)
    restored = op.invert(spec).apply(applied)
    assert _normalize(restored) == _normalize(spec)
