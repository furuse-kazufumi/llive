"""BC-05: nested_container execution + safety guards."""

from __future__ import annotations

import pytest

from llive.container.executor import BlockContainerExecutor, BlockState, NestedContainerError
from llive.schema.models import ContainerSpec, NestedContainer, SubBlockRef


def _spec(cid: str, blocks: list[str], nested: list[tuple[str, str]] | None = None) -> ContainerSpec:
    return ContainerSpec(
        schema_version=1,
        container_id=cid,
        subblocks=[SubBlockRef(type="pre_norm", name=b) for b in blocks],
        nested_containers=[NestedContainer(target=t, container_ref=ref) for t, ref in (nested or [])],
    )


def test_simple_nested_expand():
    inner = _spec("inner_v1", ["i1"])
    outer = _spec("outer_v1", ["o1", "o2"], nested=[("o1", "inner_v1")])
    exe = BlockContainerExecutor(outer, container_resolver={"inner_v1": inner}.get)
    state = exe.execute(BlockState(prompt="x"))
    types = [t.type for t in state.trace]
    assert "nested_container" in types
    assert types.count("pre_norm") == 3  # outer o1 + nested i1 + outer o2


def test_missing_resolver_raises():
    outer = _spec("o", ["a"], nested=[("a", "missing_ref")])
    exe = BlockContainerExecutor(outer)
    with pytest.raises(NestedContainerError):
        exe.execute(BlockState(prompt="x"))


def test_circular_reference_rejected():
    a = _spec("a", ["x"], nested=[("x", "b")])
    b = _spec("b", ["y"], nested=[("y", "a")])
    exe = BlockContainerExecutor(a, container_resolver={"a": a, "b": b}.get)
    with pytest.raises(NestedContainerError) as ei:
        exe.execute(BlockState(prompt="x"))
    assert "circular" in str(ei.value).lower()


def test_max_depth_enforced():
    a = _spec("a", ["x"], nested=[("x", "b")])
    b = _spec("b", ["y"], nested=[("y", "c")])
    c = _spec("c", ["z"], nested=[("z", "d")])
    d = _spec("d", ["w"])
    exe = BlockContainerExecutor(a, container_resolver={"a": a, "b": b, "c": c, "d": d}.get, max_nest_depth=2)
    with pytest.raises(NestedContainerError) as ei:
        exe.execute(BlockState(prompt="x"))
    assert "max_nest_depth" in str(ei.value)


def test_nested_inherits_max_depth():
    a = _spec("a", ["x"], nested=[("x", "b")])
    b = _spec("b", ["y"])
    exe = BlockContainerExecutor(a, container_resolver={"a": a, "b": b}.get, max_nest_depth=5)
    state = exe.execute(BlockState(prompt="x"))
    assert "nested_container" in [t.type for t in state.trace]
