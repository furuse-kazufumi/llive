"""Detect and parse corpus2skill hierarchical skill output.

Raptor's ``corpus2skill`` builds a navigable hierarchy under
``.claude/skills/corpus/<name>/`` containing:

* ``INDEX.md``       — TF-IDF + k-means cluster index with skill names per level
* ``metadata.json``  — build config and stats

When a domain has a corpus2skill output co-located inside it (e.g. the corpus
was copied along with its skill hierarchy), we prefer that for hint extraction
over raw filename scans. This module gives a thin reader for both files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

INDEX_MD = "INDEX.md"
METADATA_JSON = "metadata.json"


@dataclass
class SkillIndex:
    """Parsed corpus2skill output for a single domain."""

    domain: str
    index_path: Path
    metadata: dict = field(default_factory=dict)
    sections: list[str] = field(default_factory=list)
    """Top-level Markdown ``## `` headings extracted from INDEX.md."""


def detect_skill_index(domain_path: Path, domain_name: str) -> SkillIndex | None:
    """Return a ``SkillIndex`` if corpus2skill files are present under ``domain_path``.

    Searches at the domain root and one level down.
    """
    candidates = [domain_path / INDEX_MD]
    candidates.extend(p for p in domain_path.glob(f"**/{INDEX_MD}"))
    for idx_path in candidates:
        if not idx_path.is_file():
            continue
        meta_path = idx_path.parent / METADATA_JSON
        metadata: dict = {}
        if meta_path.is_file():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = {}
        sections = _extract_section_headings(idx_path)
        return SkillIndex(
            domain=domain_name,
            index_path=idx_path,
            metadata=metadata,
            sections=sections,
        )
    return None


def _extract_section_headings(idx_path: Path) -> list[str]:
    out: list[str] = []
    try:
        text = idx_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            out.append(s[3:].strip())
    return out
