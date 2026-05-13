"""Cover the remaining condition + nested branches of BlockContainerExecutor."""

from __future__ import annotations

import pytest

from llive.container.executor import (
    BlockContainerExecutor,
    BlockState,
    NestedContainerError,
    _eval_condition,
)
from llive.schema.models import (
    AllOfCondition,
    AnyOfCondition,
    ContainerSpec,
    RouteDepthLtCondition,
    SubBlockRef,
    SurpriseGtCondition,
    TaskTagCondition,
)


def _state(**kw):
    return BlockState(prompt="x", **kw)


def test_eval_condition_none_always_true():
    assert _eval_condition(None, _state()) is True


def test_eval_condition_surprise_gt_false():
    assert _eval_condition(SurpriseGtCondition(surprise_gt=0.5), _state(surprise=0.3)) is False


def test_eval_condition_surprise_gt_true():
    assert _eval_condition(SurpriseGtCondition(surprise_gt=0.5), _state(surprise=0.7)) is True


def test_eval_condition_task_tag_matches():
    s = _state()
    s.meta["task_tag"] = "math"
    assert _eval_condition(TaskTagCondition(task_tag="math"), s) is True
    assert _eval_condition(TaskTagCondition(task_tag="code"), s) is False


def test_eval_condition_route_depth_lt():
    s = _state()
    s.meta["route_depth"] = 2
    assert _eval_condition(RouteDepthLtCondition(route_depth_lt=3), s) is True
    assert _eval_condition(RouteDepthLtCondition(route_depth_lt=2), s) is False


def test_eval_condition_all_of():
    s = _state(surprise=0.7)
    s.meta["task_tag"] = "math"
    cond = AllOfCondition(
        all_of=[SurpriseGtCondition(surprise_gt=0.5), TaskTagCondition(task_tag="math")]
    )
    assert _eval_condition(cond, s) is True
    s2 = _state(surprise=0.7)
    s2.meta["task_tag"] = "code"
    assert _eval_condition(cond, s2) is False


def test_eval_condition_any_of():
    s = _state(surprise=0.7)
    s.meta["task_tag"] = "other"
    cond = AnyOfCondition(
        any_of=[SurpriseGtCondition(surprise_gt=0.5), TaskTagCondition(task_tag="math")]
    )
    assert _eval_condition(cond, s) is True


def test_executor_unknown_subblock_raises():
    spec = ContainerSpec(
        schema_version=1,
        container_id="x_v1",
        subblocks=[SubBlockRef(type="totally_unknown")],
    )
    with pytest.raises(KeyError):
        BlockContainerExecutor(spec)


def test_executor_records_skipped_condition():
    spec = ContainerSpec(
        schema_version=1,
        container_id="cond_v1",
        subblocks=[
            SubBlockRef(
                type="pre_norm",
                name="gated",
                condition=SurpriseGtCondition(surprise_gt=0.9),
            ),
            SubBlockRef(type="pre_norm", name="always"),
        ],
    )
    exe = BlockContainerExecutor(spec)
    state = exe.execute(BlockState(prompt="x", surprise=0.1))
    notes = {t.name: t.note for t in state.trace}
    assert notes["gated"] == "skipped_condition"
    assert notes["always"] == ""


def test_executor_raises_inside_subblock():
    """An exception inside a sub-block should propagate after writing trace."""

    class _BoomBlock:
        name = "boom"
        type = "boom"

        def __call__(self, state):  # noqa: ANN001
            raise RuntimeError("kaboom")

    from llive.container.registry import SubBlockRegistry

    reg = SubBlockRegistry()
    reg.register("boom", lambda config: _BoomBlock())
    spec = ContainerSpec(
        schema_version=1, container_id="err_v1", subblocks=[SubBlockRef(type="boom")]
    )
    exe = BlockContainerExecutor(spec, registry=reg)
    with pytest.raises(RuntimeError):
        exe.execute(BlockState(prompt="x"))
