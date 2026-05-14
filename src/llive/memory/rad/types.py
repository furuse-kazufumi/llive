"""Type definitions for the RAD knowledge base."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DomainInfo:
    """Metadata for a single corpus domain (e.g. ``security_corpus_v2``)."""

    name: str
    path: Path
    file_count: int = 0
    bytes: int = 0
    is_learned: bool = False
    """``True`` if this is the ``_learned/<name>/`` write layer instead of a Raptor mirror."""
    imported_at: str = ""


@dataclass
class RadHit:
    """A query result entry pointing to one document inside RAD."""

    domain: str
    doc_path: Path
    score: float
    excerpt: str = ""
    matched_terms: list[str] = field(default_factory=list)


@dataclass
class LearnedEntry:
    """A document written by llive into the ``_learned/`` write layer."""

    domain: str
    doc_id: str
    doc_path: Path
    provenance_path: Path
