"""Pydantic v2 models for ContainerSpec / SubBlockSpec / CandidateDiff.

source of truth は specs/schemas/*.json (JSON Schema Draft 2020-12).
このモジュールは Python 内部表現を提供し、ChangeOp は discriminated union として扱う。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Condition specs
# ---------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SurpriseGtCondition(_Strict):
    surprise_gt: float


class TaskTagCondition(_Strict):
    task_tag: str


class RouteDepthLtCondition(_Strict):
    route_depth_lt: int


class AllOfCondition(_Strict):
    all_of: list[ConditionSpec]


class AnyOfCondition(_Strict):
    any_of: list[ConditionSpec]


ConditionSpec = Union[
    SurpriseGtCondition,
    TaskTagCondition,
    RouteDepthLtCondition,
    AllOfCondition,
    AnyOfCondition,
]


# ---------------------------------------------------------------------------
# Container / SubBlock
# ---------------------------------------------------------------------------


class SubBlockRef(_Strict):
    """A reference to a sub-block instance inside a container."""

    type: str
    name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    condition: ConditionSpec | None = None


class NestedContainer(_Strict):
    target: str
    container_ref: str
    condition: ConditionSpec | None = None


class CostProfile(_Strict):
    latency: Literal["low", "medium", "high"] | None = None
    vram: Literal["low", "medium", "high"] | None = None
    est_flops_per_token: int | None = None


class ContainerSpec(_Strict):
    schema_version: Literal[1]
    container_id: str
    routing_tags: list[str] = Field(default_factory=list)
    cost_profile: CostProfile | None = None
    subblocks: list[SubBlockRef]
    nested_containers: list[NestedContainer] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# SubBlockSpec (plugin registration)
# ---------------------------------------------------------------------------


class IoEnd(_Strict):
    hidden_dim: int | None = None
    seq_dim: bool | None = None
    extras: list[str] = Field(default_factory=list)


class IoContract(_Strict):
    input: IoEnd
    output: IoEnd


class SubBlockSpec(_Strict):
    schema_version: Literal[1]
    name: str
    version: str
    io_contract: IoContract
    plugin_module: str
    trainable: bool | None = None
    supports_streaming: bool | None = None
    latency_cost_per_token_ms: float | None = None
    vram_cost_mb: float | None = None
    config_schema: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# CandidateDiff / ChangeOp (discriminated by `action`)
# ---------------------------------------------------------------------------


class _ChangeBase(_Strict):
    pass


class InsertSubblockModel(_ChangeBase):
    action: Literal["insert_subblock"]
    target_container: str
    after: str
    spec: SubBlockRef


class RemoveSubblockModel(_ChangeBase):
    action: Literal["remove_subblock"]
    target_container: str
    target_subblock: str


class ReplaceSubblockModel(_ChangeBase):
    action: Literal["replace_subblock"]
    target_container: str
    # `from` is a Python keyword; alias it
    from_: str = Field(alias="from")
    to: SubBlockRef

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ReorderSubblocksModel(_ChangeBase):
    action: Literal["reorder_subblocks"]
    target_container: str
    new_order: list[str]


class AddRoutingTagModel(_ChangeBase):
    action: Literal["add_routing_tag"]
    target_container: str
    tag: str


class SetAdapterModel(_ChangeBase):
    action: Literal["set_adapter"]
    target_subblock: str
    adapter_id: str


class SetMemoryPolicyModel(_ChangeBase):
    action: Literal["set_memory_policy"]
    memory_type: Literal["semantic", "episodic", "structural", "parameter"]
    policy: dict[str, Any]


ChangeOpModel = Annotated[
    InsertSubblockModel | RemoveSubblockModel | ReplaceSubblockModel | ReorderSubblocksModel | AddRoutingTagModel | SetAdapterModel | SetMemoryPolicyModel,
    Field(discriminator="action"),
]


class CandidateDiff(_Strict):
    schema_version: Literal[1]
    candidate_id: str
    base_candidate: str
    rationale: list[str] = Field(default_factory=list)
    changes: list[ChangeOpModel] = Field(min_length=1)


# Resolve forward refs for the condition union members
SurpriseGtCondition.model_rebuild()
TaskTagCondition.model_rebuild()
RouteDepthLtCondition.model_rebuild()
AllOfCondition.model_rebuild()
AnyOfCondition.model_rebuild()
