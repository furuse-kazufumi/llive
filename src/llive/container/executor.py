"""Block Container Executor (BC-01) — Pipes & Filters + Chain of Responsibility.

Phase 1 のセマンティクス:

- `BlockState` は「prompt + retrieved_context + meta + surprise + (optional) hidden tensor」を運ぶ。
- 推論本体 (causal_attention / ffn) は HF model に委譲し、container は「メタデータ + memory hooks
  + trace 出力」を司る。pre_norm / causal_attention / ffn_swiglu の built-in 実装は no-op
  (実モデルが内部で行う処理を象徴) として動く。
- `memory_read` は state.retrieved_context にテキストを追加する。
- `memory_write` は state.output (生成テキスト) を surprise gate を通して semantic / episodic に
  書き込む。
- `surprise_gt` 条件は state.surprise を参照して評価される。
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from llive.container.registry import SubBlock, SubBlockRegistry, get_registry
from llive.schema.models import ConditionSpec, ContainerSpec, SubBlockRef
from llive.schema.validator import validate_container_spec


@dataclass
class SubblockTraceItem:
    name: str
    type: str
    duration_ms: float
    note: str = ""


@dataclass
class BlockState:
    """State that flows through a BlockContainer."""

    prompt: str
    retrieved_context: list[str] = field(default_factory=list)
    output: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    surprise: float | None = None
    hidden: Any | None = None
    trace: list[SubblockTraceItem] = field(default_factory=list)
    memory_accesses: list[dict[str, Any]] = field(default_factory=list)

    def with_output(self, output: str) -> "BlockState":
        self.output = output
        return self


@dataclass
class _ResolvedStep:
    ref: SubBlockRef
    block: SubBlock
    name: str


def _eval_condition(cond: ConditionSpec | None, state: BlockState) -> bool:
    if cond is None:
        return True
    # Pydantic v2 union → discriminator by present attribute
    if hasattr(cond, "surprise_gt"):
        threshold = float(getattr(cond, "surprise_gt"))
        return (state.surprise or 0.0) > threshold
    if hasattr(cond, "task_tag"):
        wanted = getattr(cond, "task_tag")
        return state.meta.get("task_tag") == wanted
    if hasattr(cond, "route_depth_lt"):
        threshold = int(getattr(cond, "route_depth_lt"))
        return int(state.meta.get("route_depth", 0)) < threshold
    if hasattr(cond, "all_of"):
        return all(_eval_condition(c, state) for c in getattr(cond, "all_of"))
    if hasattr(cond, "any_of"):
        return any(_eval_condition(c, state) for c in getattr(cond, "any_of"))
    return True


class BlockContainerExecutor:
    """Loads a ContainerSpec and executes its sub-blocks in order."""

    def __init__(
        self,
        spec: ContainerSpec | dict[str, Any] | str,
        registry: SubBlockRegistry | None = None,
        *,
        container_resolver: "ContainerResolver | None" = None,
        max_nest_depth: int = 3,
    ) -> None:
        if isinstance(spec, ContainerSpec):
            self.spec = spec
        else:
            self.spec = validate_container_spec(spec)
        self.registry = registry or get_registry()
        self._steps: list[_ResolvedStep] = self._resolve_steps(self.spec.subblocks)
        self.container_resolver = container_resolver
        self.max_nest_depth = int(max_nest_depth)

    def _resolve_steps(self, refs: Iterable[SubBlockRef]) -> list[_ResolvedStep]:
        resolved: list[_ResolvedStep] = []
        for idx, ref in enumerate(refs):
            if not self.registry.has(ref.type):
                raise KeyError(
                    f"sub-block type {ref.type!r} not registered (container={self.spec.container_id})"
                )
            block = self.registry.create(ref.type, dict(ref.config))
            name = ref.name or f"{ref.type}#{idx}"
            resolved.append(_ResolvedStep(ref=ref, block=block, name=name))
        return resolved

    @property
    def container_id(self) -> str:
        return self.spec.container_id

    @property
    def subblock_types(self) -> list[str]:
        return [s.ref.type for s in self._steps]

    def execute(self, state: BlockState, _visited: tuple[str, ...] = ()) -> BlockState:
        if self.spec.container_id in _visited:
            raise NestedContainerError(
                f"circular nested_container reference: {self.spec.container_id} already in chain {_visited}"
            )
        if len(_visited) >= self.max_nest_depth:
            raise NestedContainerError(
                f"max_nest_depth={self.max_nest_depth} exceeded at container {self.spec.container_id}"
            )
        visited_next = _visited + (self.spec.container_id,)

        for step in self._steps:
            if not _eval_condition(step.ref.condition, state):
                state.trace.append(
                    SubblockTraceItem(
                        name=step.name, type=step.ref.type, duration_ms=0.0, note="skipped_condition"
                    )
                )
                continue
            start = time.perf_counter()
            try:
                state = step.block(state)
            except Exception as exc:
                state.trace.append(
                    SubblockTraceItem(
                        name=step.name,
                        type=step.ref.type,
                        duration_ms=(time.perf_counter() - start) * 1000.0,
                        note=f"error:{type(exc).__name__}",
                    )
                )
                raise
            duration_ms = (time.perf_counter() - start) * 1000.0
            state.trace.append(
                SubblockTraceItem(name=step.name, type=step.ref.type, duration_ms=duration_ms)
            )
            # nested_container: 該当 sub-block の name が nesting target なら展開
            for nested in self.spec.nested_containers:
                if nested.target == step.name and _eval_condition(nested.condition, state):
                    if self.container_resolver is None:
                        raise NestedContainerError(
                            f"nested_container at {step.name} requires container_resolver"
                        )
                    nested_spec = self.container_resolver(nested.container_ref)
                    nested_exec = BlockContainerExecutor(
                        nested_spec,
                        registry=self.registry,
                        container_resolver=self.container_resolver,
                        max_nest_depth=self.max_nest_depth,
                    )
                    state.trace.append(
                        SubblockTraceItem(
                            name=f"nested:{nested.container_ref}",
                            type="nested_container",
                            duration_ms=0.0,
                            note=f"entering depth={len(visited_next)}",
                        )
                    )
                    state = nested_exec.execute(state, _visited=visited_next)
        return state


class NestedContainerError(RuntimeError):
    """Raised on nested_container resolution failure (cycle, depth, missing resolver)."""


ContainerResolver = Callable[[str], ContainerSpec]
