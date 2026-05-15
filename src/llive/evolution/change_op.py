# SPDX-License-Identifier: Apache-2.0
"""ChangeOp apply / invert (EVO-02).

Phase 1 で実装する 4 種：
- insert_subblock
- remove_subblock
- replace_subblock
- reorder_subblocks

それぞれ `apply(container) -> container'` と `invert() -> ChangeOp` を提供する。
`add_routing_tag` / `set_adapter` / `set_memory_policy` は schema 予約のみ（Phase 2+）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from llive.schema.models import (
    CandidateDiff,
    ContainerSpec,
    SubBlockRef,
)


class ChangeOpError(Exception):
    """Raised for impossible / inconsistent change operations."""


def _to_ref(spec: SubBlockRef | dict[str, Any]) -> SubBlockRef:
    return spec if isinstance(spec, SubBlockRef) else SubBlockRef.model_validate(spec)


def _find_index(refs: list[SubBlockRef], identifier: str) -> int:
    # exact name first
    for idx, ref in enumerate(refs):
        if ref.name == identifier:
            return idx
    # then synthesized name "type#idx"
    for idx, ref in enumerate(refs):
        if _resolved_name(ref, idx) == identifier:
            return idx
    # finally a bare type match when the ref is anonymous
    for idx, ref in enumerate(refs):
        if ref.type == identifier and ref.name is None:
            return idx
    raise ChangeOpError(f"sub-block not found: {identifier!r}")


def _resolved_name(ref: SubBlockRef, idx: int) -> str:
    return ref.name or f"{ref.type}#{idx}"


class ChangeOp(ABC):
    """Abstract base for all Phase 1 change operations."""

    target_container: str

    @abstractmethod
    def apply(self, container: ContainerSpec) -> ContainerSpec: ...

    @abstractmethod
    def invert(self, container_before: ContainerSpec) -> ChangeOp: ...


# ---------------------------------------------------------------------------
# insert_subblock
# ---------------------------------------------------------------------------


@dataclass
class InsertSubblock(ChangeOp):
    target_container: str
    after: str  # subblock name/type or "head"
    spec: SubBlockRef = field()

    def apply(self, container: ContainerSpec) -> ContainerSpec:
        if container.container_id != self.target_container:
            raise ChangeOpError(
                f"container mismatch: op targets {self.target_container!r}, got {container.container_id!r}"
            )
        new = deepcopy(container)
        new_spec = _to_ref(self.spec)
        if self.after == "head":
            new.subblocks.insert(0, new_spec)
        else:
            idx = _find_index(new.subblocks, self.after)
            new.subblocks.insert(idx + 1, new_spec)
        return new

    def invert(self, container_before: ContainerSpec) -> RemoveSubblock:
        # After `apply`, the inserted sub-block will be identified by `spec.name or spec.type`.
        new_spec = _to_ref(self.spec)
        ident = new_spec.name or new_spec.type
        return RemoveSubblock(target_container=self.target_container, target_subblock=ident)


# ---------------------------------------------------------------------------
# remove_subblock
# ---------------------------------------------------------------------------


@dataclass
class RemoveSubblock(ChangeOp):
    target_container: str
    target_subblock: str

    def apply(self, container: ContainerSpec) -> ContainerSpec:
        if container.container_id != self.target_container:
            raise ChangeOpError(
                f"container mismatch: op targets {self.target_container!r}, got {container.container_id!r}"
            )
        new = deepcopy(container)
        idx = _find_index(new.subblocks, self.target_subblock)
        del new.subblocks[idx]
        return new

    def invert(self, container_before: ContainerSpec) -> InsertSubblock:
        idx = _find_index(container_before.subblocks, self.target_subblock)
        original = deepcopy(container_before.subblocks[idx])
        # `after` references the previous block (or "head" if removing the first)
        after = "head" if idx == 0 else _resolved_name(container_before.subblocks[idx - 1], idx - 1)
        return InsertSubblock(target_container=self.target_container, after=after, spec=original)


# ---------------------------------------------------------------------------
# replace_subblock
# ---------------------------------------------------------------------------


@dataclass
class ReplaceSubblock(ChangeOp):
    target_container: str
    from_: str  # name/type
    to: SubBlockRef

    def apply(self, container: ContainerSpec) -> ContainerSpec:
        if container.container_id != self.target_container:
            raise ChangeOpError(
                f"container mismatch: op targets {self.target_container!r}, got {container.container_id!r}"
            )
        new = deepcopy(container)
        idx = _find_index(new.subblocks, self.from_)
        new.subblocks[idx] = _to_ref(self.to)
        return new

    def invert(self, container_before: ContainerSpec) -> ReplaceSubblock:
        idx = _find_index(container_before.subblocks, self.from_)
        original = deepcopy(container_before.subblocks[idx])
        new_spec = _to_ref(self.to)
        new_ident = new_spec.name or new_spec.type
        return ReplaceSubblock(target_container=self.target_container, from_=new_ident, to=original)


# ---------------------------------------------------------------------------
# reorder_subblocks
# ---------------------------------------------------------------------------


@dataclass
class ReorderSubblocks(ChangeOp):
    target_container: str
    new_order: list[str]

    def apply(self, container: ContainerSpec) -> ContainerSpec:
        if container.container_id != self.target_container:
            raise ChangeOpError(
                f"container mismatch: op targets {self.target_container!r}, got {container.container_id!r}"
            )
        if len(self.new_order) != len(container.subblocks):
            raise ChangeOpError("new_order length differs from current subblocks count")
        new = deepcopy(container)
        idx_map: list[int] = []
        for ident in self.new_order:
            idx_map.append(_find_index(new.subblocks, ident))
        if sorted(idx_map) != list(range(len(new.subblocks))):
            raise ChangeOpError("new_order must reference every existing sub-block exactly once")
        reordered = [new.subblocks[i] for i in idx_map]
        new.subblocks = reordered
        return new

    def invert(self, container_before: ContainerSpec) -> ReorderSubblocks:
        # Apply ourselves once to obtain the post-state's identifier space; then
        # express the original order in those identifiers.
        post = self.apply(container_before)
        inverse_order: list[str] = []
        used: set[int] = set()
        for orig_ref in container_before.subblocks:
            orig_ident = orig_ref.name or orig_ref.type
            found: int | None = None
            for j, post_ref in enumerate(post.subblocks):
                if j in used:
                    continue
                post_ident = post_ref.name or post_ref.type
                if post_ident == orig_ident:
                    found = j
                    break
            if found is None:
                raise ChangeOpError("reorder invert: cannot match original sub-block in post state")
            used.add(found)
            inverse_order.append(_resolved_name(post.subblocks[found], found))
        return ReorderSubblocks(target_container=self.target_container, new_order=inverse_order)


# ---------------------------------------------------------------------------
# CandidateDiff -> sequence of ChangeOp
# ---------------------------------------------------------------------------


def build_change_op(model) -> ChangeOp:
    """Translate a pydantic ChangeOpModel into a concrete ChangeOp."""
    action = model.action
    if action == "insert_subblock":
        return InsertSubblock(
            target_container=model.target_container, after=model.after, spec=model.spec
        )
    if action == "remove_subblock":
        return RemoveSubblock(
            target_container=model.target_container, target_subblock=model.target_subblock
        )
    if action == "replace_subblock":
        return ReplaceSubblock(
            target_container=model.target_container, from_=model.from_, to=model.to
        )
    if action == "reorder_subblocks":
        return ReorderSubblocks(
            target_container=model.target_container, new_order=list(model.new_order)
        )
    raise ChangeOpError(f"Phase 1 does not implement ChangeOp action {action!r}")


def apply_diff(container: ContainerSpec, diff: CandidateDiff) -> tuple[ContainerSpec, list[ChangeOp]]:
    """Apply every change in `diff` to `container` (in order); also return the operations used.

    Returns the post-diff container plus the materialised ChangeOp instances (useful for
    generating a full inverse diff for rollback).
    """
    ops: list[ChangeOp] = [build_change_op(c) for c in diff.changes]
    current = container
    for op in ops:
        current = op.apply(current)
    return current, ops
