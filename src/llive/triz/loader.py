"""TRIZ resource loader (TRIZ-01) — lazy YAML readers for principles / matrix / attributes.

Resources live under ``specs/resources/``:
    - triz_principles.yaml
    - triz_contradiction_matrix.yaml
    - triz_attributes.yaml

API returns immutable cached views; mutation should go through copies.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "specs" / "resources").is_dir():
            return parent
    raise RuntimeError("could not locate project root with specs/resources/")


def _resource_path(filename: str) -> Path:
    return _project_root() / "specs" / "resources" / filename


@dataclass(frozen=True)
class Principle:
    id: int
    name: str
    description: str = ""
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class Attribute:
    id: int
    name: str
    description: str = ""


def _coerce_principle(raw: dict[str, Any]) -> Principle:
    examples = raw.get("examples") or []
    return Principle(
        id=int(raw["id"]),
        name=str(raw.get("name", "")),
        description=str(raw.get("description", "")),
        examples=tuple(str(e) for e in examples),
    )


def _coerce_attribute(raw: dict[str, Any]) -> Attribute:
    return Attribute(
        id=int(raw["id"]),
        name=str(raw.get("name", "")),
        description=str(raw.get("description", "")),
    )


@lru_cache(maxsize=1)
def load_principles() -> dict[int, Principle]:
    path = _resource_path("triz_principles.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("principles") or data.get("items") or []
    return {p.id: p for p in (_coerce_principle(r) for r in items)}


@lru_cache(maxsize=1)
def load_attributes() -> dict[int, Attribute]:
    path = _resource_path("triz_attributes.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("attributes") or data.get("items") or []
    return {a.id: a for a in (_coerce_attribute(r) for r in items)}


@lru_cache(maxsize=1)
def load_matrix() -> dict[tuple[int, int], tuple[int, ...]]:
    """39×39 contradiction matrix → dict[(improving, worsening)] = (principle_ids,)."""
    path = _resource_path("triz_contradiction_matrix.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_rows = data.get("matrix") or data.get("rows") or []
    matrix: dict[tuple[int, int], tuple[int, ...]] = {}
    for row in raw_rows:
        improving = int(row["improving"])
        worsening = int(row["worsening"])
        principles = tuple(int(p) for p in (row.get("principles") or []))
        matrix[(improving, worsening)] = principles
    return matrix


def lookup_principles(improving: int, worsening: int) -> list[Principle]:
    """Look up recommended principles for an (improving, worsening) attribute pair."""
    matrix = load_matrix()
    principles = load_principles()
    ids = matrix.get((int(improving), int(worsening)), ())
    return [principles[i] for i in ids if i in principles]
