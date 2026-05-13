"""Wiki diff as ChangeOp (LLW-05).

Extends EVO-02 with three concept-level operations on the Wiki layer:

* :class:`AddConcept`   — create a new ConceptPage
* :class:`MergeConcept` — merge ``from_ids`` into ``into_id`` (LLW-AC-04 compliant)
* :class:`SplitConcept` — split ``from_id`` into multiple new pages

These do not mutate the structural container; instead they describe an
intended transformation over :class:`ConceptPageRepo` so the wiki diff
can be reviewed as a single artifact, attached to a CandidateDiff, and
rolled back via the same Memento/Saga pattern as block-level changes.

Apply / invert are deterministic: each op records the *post-state* metadata
necessary to derive its inverse against the pre-state.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from llive.memory.concept import ConceptPage
from llive.memory.provenance import Provenance


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WikiChangeOpError(Exception):
    """Raised for impossible wiki change operations."""


class WikiChangeOp(ABC):
    """Abstract base for wiki concept-level operations."""

    @abstractmethod
    def apply(self, pages: dict[str, ConceptPage]) -> dict[str, ConceptPage]: ...

    @abstractmethod
    def invert(self, before: dict[str, ConceptPage]) -> WikiChangeOp: ...


# ---------------------------------------------------------------------------
# add_concept
# ---------------------------------------------------------------------------


@dataclass
class AddConcept(WikiChangeOp):
    page: ConceptPage

    def apply(self, pages: dict[str, ConceptPage]) -> dict[str, ConceptPage]:
        if self.page.page_id in pages:
            raise WikiChangeOpError(f"page already exists: {self.page.page_id!r}")
        new = dict(pages)
        new[self.page.page_id] = deepcopy(self.page)
        return new

    def invert(self, before: dict[str, ConceptPage]) -> WikiChangeOp:
        return RemoveConcept(page_id=self.page.page_id)


@dataclass
class RemoveConcept(WikiChangeOp):
    page_id: str

    def apply(self, pages: dict[str, ConceptPage]) -> dict[str, ConceptPage]:
        if self.page_id not in pages:
            raise WikiChangeOpError(f"page not found: {self.page_id!r}")
        new = dict(pages)
        new.pop(self.page_id)
        return new

    def invert(self, before: dict[str, ConceptPage]) -> WikiChangeOp:
        if self.page_id not in before:
            raise WikiChangeOpError(
                f"cannot invert RemoveConcept: {self.page_id!r} missing from pre-state"
            )
        return AddConcept(page=deepcopy(before[self.page_id]))


# ---------------------------------------------------------------------------
# merge_concept
# ---------------------------------------------------------------------------


@dataclass
class MergeConcept(WikiChangeOp):
    from_ids: list[str]
    into_id: str
    new_title: str | None = None
    new_summary: str | None = None

    def apply(self, pages: dict[str, ConceptPage]) -> dict[str, ConceptPage]:
        if self.into_id not in pages:
            raise WikiChangeOpError(f"target concept not found: {self.into_id!r}")
        for src in self.from_ids:
            if src not in pages:
                raise WikiChangeOpError(f"source concept not found: {src!r}")
            if src == self.into_id:
                raise WikiChangeOpError("cannot merge a concept into itself")
        new_pages = dict(pages)
        target = deepcopy(new_pages[self.into_id])
        derived_sources: list[Any] = list(getattr(target.provenance, "derived_from", []) or [])
        for src in self.from_ids:
            derived_sources.extend(
                list(getattr(new_pages[src].provenance, "derived_from", []) or [])
            )
            del new_pages[src]
        if self.new_title:
            target.title = self.new_title
        if self.new_summary:
            target.summary = self.new_summary
        target.provenance = Provenance(
            source_type=target.provenance.source_type,
            source_id=target.provenance.source_id,
            derived_from=derived_sources,
            confidence=getattr(target.provenance, "confidence", 1.0),
        )
        new_pages[self.into_id] = target
        return new_pages

    def invert(self, before: dict[str, ConceptPage]) -> WikiChangeOp:
        # Inverse re-adds the from_ids and restores the original target.
        if self.into_id not in before:
            raise WikiChangeOpError(
                f"cannot invert MergeConcept: target {self.into_id!r} missing from pre-state"
            )
        missing = [s for s in self.from_ids if s not in before]
        if missing:
            raise WikiChangeOpError(
                f"cannot invert MergeConcept: missing pre-state pages {missing}"
            )
        return _UnmergeConcept(
            from_ids=list(self.from_ids),
            into_id=self.into_id,
            restored_pages=[deepcopy(before[src]) for src in self.from_ids],
            restored_target=deepcopy(before[self.into_id]),
        )


@dataclass
class _UnmergeConcept(WikiChangeOp):
    """Internal: inverse of MergeConcept, restores pre-merge state."""

    from_ids: list[str]
    into_id: str
    restored_pages: list[ConceptPage]
    restored_target: ConceptPage

    def apply(self, pages: dict[str, ConceptPage]) -> dict[str, ConceptPage]:
        if self.into_id not in pages:
            raise WikiChangeOpError(f"unmerge: target {self.into_id!r} missing")
        new_pages = dict(pages)
        for src_page in self.restored_pages:
            new_pages[src_page.page_id] = deepcopy(src_page)
        new_pages[self.into_id] = deepcopy(self.restored_target)
        return new_pages

    def invert(self, before: dict[str, ConceptPage]) -> WikiChangeOp:
        return MergeConcept(from_ids=list(self.from_ids), into_id=self.into_id)


# ---------------------------------------------------------------------------
# split_concept
# ---------------------------------------------------------------------------


@dataclass
class SplitConcept(WikiChangeOp):
    from_id: str
    new_pages: list[ConceptPage] = field(default_factory=list)
    keep_original: bool = False

    def apply(self, pages: dict[str, ConceptPage]) -> dict[str, ConceptPage]:
        if self.from_id not in pages:
            raise WikiChangeOpError(f"source concept not found: {self.from_id!r}")
        if not self.new_pages:
            raise WikiChangeOpError("split requires at least one new page")
        for p in self.new_pages:
            if p.page_id in pages:
                raise WikiChangeOpError(f"split target already exists: {p.page_id!r}")
        new = dict(pages)
        if not self.keep_original:
            del new[self.from_id]
        for p in self.new_pages:
            new[p.page_id] = deepcopy(p)
        return new

    def invert(self, before: dict[str, ConceptPage]) -> WikiChangeOp:
        if self.from_id not in before:
            raise WikiChangeOpError(
                f"cannot invert SplitConcept: source {self.from_id!r} missing from pre-state"
            )
        return _UnsplitConcept(
            restored=deepcopy(before[self.from_id]),
            split_ids=[p.page_id for p in self.new_pages],
            keep_original=self.keep_original,
        )


@dataclass
class _UnsplitConcept(WikiChangeOp):
    restored: ConceptPage
    split_ids: list[str]
    keep_original: bool

    def apply(self, pages: dict[str, ConceptPage]) -> dict[str, ConceptPage]:
        new = dict(pages)
        if self.restored.page_id not in new:
            new[self.restored.page_id] = deepcopy(self.restored)
        for split_id in self.split_ids:
            new.pop(split_id, None)
        return new

    def invert(self, before: dict[str, ConceptPage]) -> WikiChangeOp:
        return SplitConcept(
            from_id=self.restored.page_id,
            new_pages=[deepcopy(before[sid]) for sid in self.split_ids if sid in before],
            keep_original=self.keep_original,
        )


# ---------------------------------------------------------------------------
# diff builder
# ---------------------------------------------------------------------------


@dataclass
class WikiDiff:
    diff_id: str = field(default_factory=lambda: f"wdiff_{uuid.uuid4().hex[:12]}")
    ops: list[WikiChangeOp] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)


def apply_wiki_diff(
    pages: dict[str, ConceptPage], diff: WikiDiff
) -> tuple[dict[str, ConceptPage], list[WikiChangeOp]]:
    """Apply every op in ``diff`` to ``pages`` (in order)."""
    current = pages
    applied: list[WikiChangeOp] = []
    for op in diff.ops:
        current = op.apply(current)
        applied.append(op)
    return current, applied


def invert_wiki_diff(before: dict[str, ConceptPage], diff: WikiDiff) -> WikiDiff:
    """Build the inverse WikiDiff against the pre-state."""
    # Compute snapshots so each invert sees the correct intermediate state.
    snapshots: list[dict[str, ConceptPage]] = [before]
    current = before
    for op in diff.ops:
        current = op.apply(current)
        snapshots.append(current)
    inverse_ops: list[WikiChangeOp] = []
    for i in range(len(diff.ops) - 1, -1, -1):
        inverse_ops.append(diff.ops[i].invert(snapshots[i]))
    return WikiDiff(ops=inverse_ops)


__all__ = [
    "AddConcept",
    "MergeConcept",
    "RemoveConcept",
    "SplitConcept",
    "WikiChangeOp",
    "WikiChangeOpError",
    "WikiDiff",
    "apply_wiki_diff",
    "invert_wiki_diff",
]
