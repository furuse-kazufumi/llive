# SPDX-License-Identifier: Apache-2.0
"""ConceptPage (LLW-01) — first-class concept representation.

ConceptPages are persisted as ``memory_type=concept`` nodes inside the
structural memory layer. They also support Markdown export to
``D:/data/llive/wiki/<concept_id>.md`` for human readability and Git
checkpointing.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from llive.memory.bayesian_surprise import WelfordStats
from llive.memory.provenance import Provenance
from llive.memory.structural import StructuralMemory

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s or "concept"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _default_wiki_dir() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "wiki"


# ---------------------------------------------------------------------------
# Page model
# ---------------------------------------------------------------------------


class ConceptPage(BaseModel):
    """A single Wiki page representing a coherent concept.

    Persisted as a ``memory_type=concept`` MemoryNode (LLW-01).
    """

    model_config = ConfigDict(extra="forbid")

    concept_id: str  # kebab-case slug, unique
    title: str
    summary: str = ""  # LLM-generated, <= 2000 chars in practice
    page_type: str = "domain_concept"
    linked_entry_ids: list[str] = Field(default_factory=list)
    linked_concept_ids: list[str] = Field(default_factory=list)
    structured_fields: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = 1
    provenance: Provenance | None = None
    last_updated_at: datetime = Field(default_factory=_utcnow)
    surprise_stats: dict[str, float] = Field(default_factory=dict)  # WelfordStats.to_dict()

    @classmethod
    def from_title(
        cls,
        title: str,
        summary: str = "",
        page_type: str = "domain_concept",
        provenance: Provenance | None = None,
        **fields: Any,
    ) -> ConceptPage:
        return cls(
            concept_id=_slugify(title),
            title=title,
            summary=summary,
            page_type=page_type,
            provenance=provenance,
            structured_fields=fields,
        )

    def with_summary(self, summary: str) -> ConceptPage:
        return self.model_copy(update={"summary": summary, "last_updated_at": _utcnow()})

    def add_linked_entry(self, entry_id: str) -> ConceptPage:
        if entry_id in self.linked_entry_ids:
            return self
        return self.model_copy(
            update={
                "linked_entry_ids": [*self.linked_entry_ids, entry_id],
                "last_updated_at": _utcnow(),
            }
        )

    def add_linked_concept(self, concept_id: str) -> ConceptPage:
        if concept_id in self.linked_concept_ids:
            return self
        return self.model_copy(
            update={
                "linked_concept_ids": [*self.linked_concept_ids, concept_id],
                "last_updated_at": _utcnow(),
            }
        )

    def update_surprise(self, value: float) -> ConceptPage:
        stats = WelfordStats.from_dict(self.surprise_stats) if self.surprise_stats else WelfordStats()
        stats.update(value)
        return self.model_copy(update={"surprise_stats": stats.to_dict(), "last_updated_at": _utcnow()})

    # -- markdown export --------------------------------------------------

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", ""]
        if self.summary:
            lines.append(self.summary)
            lines.append("")
        lines.append(f"**Type:** {self.page_type}")
        lines.append(f"**Last updated:** {self.last_updated_at.isoformat()}")
        if self.provenance is not None:
            lines.append(
                f"**Source:** {self.provenance.source_type} / {self.provenance.source_id} "
                f"(confidence: {self.provenance.confidence})"
            )
        lines.append("")
        if self.linked_concept_ids:
            lines.append("## Linked Concepts")
            for slug in self.linked_concept_ids:
                lines.append(f"- [[{slug}]]")
            lines.append("")
        if self.linked_entry_ids:
            lines.append(f"## Evidence ({len(self.linked_entry_ids)} entries)")
            for eid in self.linked_entry_ids:
                lines.append(f"- `{eid}`")
            lines.append("")
        if self.structured_fields:  # pragma: no cover - cosmetic markdown render
            lines.append("## Structured Fields")
            for k, v in self.structured_fields.items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")
        if self.surprise_stats:  # pragma: no cover - cosmetic markdown render
            n = self.surprise_stats.get("n", 0)
            mean = self.surprise_stats.get("mean", 0.0)
            lines.append(f"_Surprise stats: n={n}, mean={mean:.4f}_")
        return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Repository: persistence through StructuralMemory + Markdown mirror
# ---------------------------------------------------------------------------


@dataclass
class ConceptPageRepo:
    """Persistence layer for ConceptPages."""

    structural: StructuralMemory
    wiki_dir: Path | None = None

    def __post_init__(self) -> None:
        self.wiki_dir = Path(self.wiki_dir) if self.wiki_dir else _default_wiki_dir()
        self.wiki_dir.mkdir(parents=True, exist_ok=True)

    # -- core operations --------------------------------------------------

    def upsert(self, page: ConceptPage, export_markdown: bool = True) -> ConceptPage:
        payload = page.model_dump(mode="json")
        existing = self.get(page.concept_id)
        if existing is None:
            self.structural.add_node(
                memory_type="concept",
                payload=payload,
                provenance=page.provenance,
                node_id=page.concept_id,
            )
        else:
            # Kùzu lacks a single-call MERGE in our wrapper; do delete + add to keep idempotent
            self.structural.delete_node(page.concept_id)
            self.structural.add_node(
                memory_type="concept",
                payload=payload,
                provenance=page.provenance,
                node_id=page.concept_id,
            )
        if export_markdown:
            self._export_markdown(page)
        return page

    def get(self, concept_id: str) -> ConceptPage | None:
        node = self.structural.get_node(concept_id)
        if node is None or node.memory_type != "concept":
            return None
        return ConceptPage.model_validate(node.payload)

    def list_all(self, limit: int = 100) -> list[ConceptPage]:
        nodes = self.structural.list_nodes(memory_type="concept", limit=limit)
        return [ConceptPage.model_validate(n.payload) for n in nodes if n.memory_type == "concept"]

    def link_concept(self, src_id: str, dst_id: str, weight: float = 1.0) -> None:
        self.structural.add_edge(src_id, dst_id, "linked_concept", weight=weight)

    def link_entry(self, concept_id: str, entry_id: str) -> None:
        # entries live in semantic memory, not this graph; the link is stored on the page
        page = self.get(concept_id)
        if page is None:
            raise KeyError(f"concept {concept_id!r} not found")
        self.upsert(page.add_linked_entry(entry_id))

    # -- export -----------------------------------------------------------

    def _export_markdown(self, page: ConceptPage) -> Path:
        target = (self.wiki_dir / f"{page.concept_id}.md")
        target.write_text(page.to_markdown(), encoding="utf-8")
        return target
