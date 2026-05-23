# SPDX-License-Identifier: Apache-2.0
"""Persona Prompt Library loader (v0.F C-prompt chromosome backing store).

Loads markdown files under ``persona_prompts/<field>/<id>.md`` into typed
``PersonaPrompt`` records. Used by the v0.F Genome ``CPromptChromosome`` to
turn a persona bitmask + density into an LLM-injectable prompt block.

See ``docs/requirements_v0F_persona_prompt_resources.md`` for the schema
and ``persona_prompts/_schema.md`` for the file-level convention.

Phase 1 (skeleton): file discovery, frontmatter + body parsing, composition.
Phase 2: persona-aware sampling, lineage graph traversal, validation CLI.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Iterable

try:
    import yaml  # PyYAML is a soft dep here; loader fails gracefully without it.
    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_SECTION_RE = re.compile(r"^## (\d+\. )?(.+?)\n", re.MULTILINE)


class PersonaPromptValidationError(ValueError):
    """Raised when a persona prompt file violates schema requirements."""


@dataclass(frozen=True)
class PersonaPrompt:
    """A single persona prompt — Loader's typed view of one ``<id>.md``."""

    id: str
    display_name: str
    era: str
    fields: tuple[str, ...]
    nationality: str
    style_text: str
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    prompt_text: str
    examples: tuple[str, ...]
    anti_patterns: tuple[str, ...]
    sources: tuple[str, ...]
    license_note: str
    lineage_influenced_by: tuple[str, ...] = dc_field(default_factory=tuple)
    lineage_influences: tuple[str, ...] = dc_field(default_factory=tuple)
    tags: tuple[str, ...] = dc_field(default_factory=tuple)
    last_updated: str = ""
    sources_collected_via: str = "manual"
    primary_field: str = ""

    def __post_init__(self) -> None:
        if not self.primary_field and self.fields:
            object.__setattr__(self, "primary_field", self.fields[0])


def _parse_bullets(text: str) -> list[str]:
    """Extract bullet items (- or *) from a markdown chunk."""
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(("- ", "* ")):
            out.append(s[2:].strip())
    return out


def _parse_blockquote(text: str) -> str:
    """Extract a leading blockquote (> ...) block, joined to a single paragraph."""
    lines: list[str] = []
    in_quote = False
    for line in text.splitlines():
        s = line.rstrip()
        if s.startswith(">"):
            in_quote = True
            lines.append(s.lstrip(">").strip())
        elif in_quote and not s.strip():
            break
        elif in_quote:
            # quote continuation without > prefix is uncommon, but accept once
            lines.append(s.strip())
    return " ".join(lines).strip()


def _split_sections(body: str) -> dict[str, str]:
    """Split markdown body by ``## `` headings (numbered or not).

    Keys are the heading text (without leading ``N.`` and trailing whitespace).
    Values are the chunk between this heading and the next ``## ``.
    """
    sections: dict[str, str] = {}
    pos = 0
    last_key: str | None = None
    last_start = 0
    for m in _SECTION_RE.finditer(body):
        if last_key is not None:
            sections[last_key] = body[last_start:m.start()].strip()
        # group(2) is the heading text after optional "N. "
        last_key = m.group(2).strip()
        last_start = m.end()
        pos = m.end()
    if last_key is not None:
        sections[last_key] = body[last_start:].strip()
    return sections


def _heading_match(sections: dict[str, str], keywords: Iterable[str]) -> str:
    """Find first section whose heading contains any of ``keywords``."""
    kws = [k.lower() for k in keywords]
    for heading, body in sections.items():
        h = heading.lower()
        if any(k in h for k in kws):
            return body
    return ""


def parse_persona_file(path: Path) -> PersonaPrompt:
    """Parse one ``<id>.md`` into a ``PersonaPrompt``."""
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise PersonaPromptValidationError(f"{path}: missing frontmatter")
    fm_text, body = m.group(1), m.group(2)

    if _HAS_YAML:
        fm = yaml.safe_load(fm_text) or {}
    else:
        fm = _minimal_yaml_parse(fm_text)

    required = ("id", "display_name", "era", "fields", "license_note",
                "source_refs", "sources_collected_via", "last_updated")
    for key in required:
        if key not in fm:
            raise PersonaPromptValidationError(
                f"{path}: frontmatter missing required key '{key}'"
            )
    if len(fm.get("source_refs") or []) < 2:
        raise PersonaPromptValidationError(
            f"{path}: source_refs must list at least 2 references"
        )

    sections = _split_sections(body)

    style = _heading_match(sections, ["思考スタイル", "style"])
    strengths_chunk = _heading_match(sections, ["強み", "strengths"])
    weaknesses_chunk = _heading_match(sections, ["弱み", "weaknesses"])
    prompt_chunk = _heading_match(sections, ["使用 prompt", "prompt"])
    examples_chunk = _heading_match(sections, ["思考の例", "worked", "example"])
    anti_chunk = _heading_match(sections, ["禁忌", "anti"])
    sources_chunk = _heading_match(sections, ["出典", "sources"])

    if not (100 <= len(style) <= 5000):
        raise PersonaPromptValidationError(
            f"{path}: style_text length {len(style)} out of [100, 5000]"
        )

    prompt_text = _parse_blockquote(prompt_chunk)
    if not (30 <= len(prompt_text) <= 2000):
        raise PersonaPromptValidationError(
            f"{path}: prompt_text length {len(prompt_text)} out of [30, 2000]"
        )

    # Examples: each '### ' subheading in the section = one worked example
    examples_list = [chunk.strip() for chunk in re.split(r"^### ", examples_chunk,
                                                         flags=re.MULTILINE) if chunk.strip()]

    lineage = fm.get("lineage") or {}

    return PersonaPrompt(
        id=str(fm["id"]),
        display_name=str(fm["display_name"]),
        era=str(fm["era"]),
        fields=tuple(fm.get("fields") or ()),
        nationality=str(fm.get("nationality", "")),
        style_text=style,
        strengths=tuple(_parse_bullets(strengths_chunk)),
        weaknesses=tuple(_parse_bullets(weaknesses_chunk)),
        prompt_text=prompt_text,
        examples=tuple(examples_list),
        anti_patterns=tuple(_parse_bullets(anti_chunk)),
        sources=tuple(_parse_bullets(sources_chunk)) or tuple(
            str(s) for s in (fm.get("source_refs") or [])
        ),
        license_note=str(fm["license_note"]),
        lineage_influenced_by=tuple(lineage.get("influenced_by") or ()),
        lineage_influences=tuple(lineage.get("influences") or ()),
        tags=tuple(fm.get("tags") or ()),
        last_updated=str(fm["last_updated"]),
        sources_collected_via=str(fm["sources_collected_via"]),
    )


def _minimal_yaml_parse(fm_text: str) -> dict[str, object]:
    """Minimal YAML subset parser for environments without PyYAML.

    Supports: top-level ``key: value`` and ``key:`` + dashed list items
    (one level deep). Not a full YAML parser — install PyYAML for full fidelity.
    """
    result: dict[str, object] = {}
    current_key: str | None = None
    current_list: list[str] | None = None
    nested_key: str | None = None
    nested_dict: dict[str, list[str]] | None = None

    for raw in fm_text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("  - "):
            item = line[4:].strip()
            if current_list is not None:
                current_list.append(item)
            elif nested_dict is not None and nested_key is not None:
                nested_dict.setdefault(nested_key, []).append(item)
            continue
        if line.startswith("  ") and ":" in line:
            k, _, v = line.strip().partition(":")
            if nested_dict is not None:
                if v.strip():
                    nested_dict[k.strip()] = [s.strip() for s in v.strip("[]").split(",")
                                              if s.strip()]
                else:
                    nested_key = k.strip()
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            current_key = k.strip()
            nested_key = None
            v_stripped = v.strip()
            if not v_stripped:
                if current_key == "lineage":
                    nested_dict = {}
                    result[current_key] = nested_dict
                    current_list = None
                else:
                    current_list = []
                    result[current_key] = current_list
                    nested_dict = None
            else:
                # Inline value
                if v_stripped.startswith("[") and v_stripped.endswith("]"):
                    items = [s.strip() for s in v_stripped[1:-1].split(",") if s.strip()]
                    result[current_key] = items
                else:
                    result[current_key] = v_stripped
                current_list = None
                nested_dict = None
    return result


class PersonaPromptLibrary:
    """File-system backed library of persona prompts.

    Defaults to the ``persona_prompts/`` sibling directory of this module.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path(__file__).parent / "persona_prompts")
        self._cache: dict[str, PersonaPrompt] = {}
        self._paths: dict[str, Path] = {}
        self._scan()

    def _scan(self) -> None:
        """Build id → path map without parsing bodies."""
        if not self.root.exists():
            return
        for p in self.root.glob("**/*.md"):
            if p.name.startswith("_") or p.name == "README.md":
                continue
            # Cheap id extraction: read only frontmatter
            try:
                head = p.read_text(encoding="utf-8")[:1024]
            except OSError:  # pragma: no cover
                continue
            m = re.search(r"^id:\s*(\S+)", head, re.MULTILINE)
            if m:
                self._paths[m.group(1)] = p

    def discover(self) -> list[str]:
        """Sorted list of all known persona ids."""
        return sorted(self._paths)

    def get(self, persona_id: str) -> PersonaPrompt:
        """Load and cache a single persona by id."""
        if persona_id in self._cache:
            return self._cache[persona_id]
        if persona_id not in self._paths:
            raise KeyError(f"persona '{persona_id}' not found in {self.root}")
        prompt = parse_persona_file(self._paths[persona_id])
        self._cache[persona_id] = prompt
        return prompt

    def by_field(self, field: str) -> list[PersonaPrompt]:
        """All personas whose primary field matches."""
        return [self.get(pid) for pid in self.discover()
                if field in self.get(pid).fields]

    def random_sample(
        self,
        n: int,
        *,
        rng=None,
        fields: list[str] | None = None,
    ) -> list[PersonaPrompt]:
        """Pseudo-random sample of n personas.

        ``fields`` (optional) restricts to personas whose ``fields`` contain
        at least one of the given field names.
        """
        import random
        rng = rng or random.Random()
        pool = self.discover()
        if fields:
            pool = [pid for pid in pool
                    if any(f in self.get(pid).fields for f in fields)]
        n = min(n, len(pool))
        return [self.get(pid) for pid in rng.sample(pool, n)]

    def compose(
        self,
        persona_ids: list[str],
        *,
        density: float = 1.0,
        max_chars: int | None = None,
    ) -> str:
        """Combine multiple personas into one composed prompt block.

        Density in [0, 1] controls how much of each ``prompt_text`` is kept:
        - 1.0 → full prompt text per persona
        - 0.5 → first half (sentence-truncated)
        - 0.0 → only ``display_name`` summary
        """
        density = max(0.0, min(1.0, float(density)))
        parts: list[str] = []
        for pid in persona_ids:
            p = self.get(pid)
            if density <= 0.0:
                parts.append(f"- {p.display_name} ({', '.join(p.fields)})")
                continue
            text = p.prompt_text.strip()
            if density < 1.0:
                cutoff = max(1, int(len(text) * density))
                # snap to nearest sentence boundary backwards
                snippet = text[:cutoff]
                last_period = max(snippet.rfind("。"), snippet.rfind("."))
                if last_period > cutoff // 2:
                    snippet = snippet[:last_period + 1]
                text = snippet
            parts.append(f"### {p.display_name}\n{text}")

        combined = "\n\n".join(parts)
        if max_chars is not None and len(combined) > max_chars:
            combined = combined[:max_chars - 3].rstrip() + "..."
        return combined

    def __len__(self) -> int:
        return len(self._paths)

    def __contains__(self, persona_id: object) -> bool:
        return persona_id in self._paths


__all__ = [
    "PersonaPrompt",
    "PersonaPromptLibrary",
    "PersonaPromptValidationError",
    "parse_persona_file",
]
