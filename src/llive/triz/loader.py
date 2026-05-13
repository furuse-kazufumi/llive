"""TRIZ resource loader (TRIZ-01) — lazy YAML readers.

Phase 0 で specs/resources/ に置かれた以下を読み込む：
    - triz_principles.yaml  (list of {id, name, jp, brief, ...})
    - triz_features.yaml    (list of {id, name, jp, llive_mapping}) — 39+11 attributes
    - triz_matrix_compact.yaml  (dict improving_id: {worsening_id: [principle_ids]})

Phase 0 のファイル名 (triz_features / triz_matrix_compact) は legacy。
Phase 3 で正式 (triz_contradiction_matrix / triz_attributes) に rename 予定。
ローダは両方を受け付ける。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _packaged_resources_dir() -> Path | None:
    """llive/_specs/resources/ (shipped inside the wheel)."""
    here = Path(__file__).resolve()
    candidate = here.parent.parent / "_specs" / "resources"
    return candidate if candidate.is_dir() else None


def _project_root() -> Path:
    """Development-tree fallback: walk up until specs/resources/ is found."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "specs" / "resources").is_dir():
            return parent
    raise RuntimeError("could not locate project root with specs/resources/")


def _resource_path(*candidates: str) -> Path:
    packaged = _packaged_resources_dir()
    if packaged is not None:
        for name in candidates:
            p = packaged / name
            if p.exists():
                return p
    base = _project_root() / "specs" / "resources"
    for name in candidates:
        p = base / name
        if p.exists():
            return p
    raise FileNotFoundError(f"none of {candidates} exist under packaged or {base}")


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
    examples = raw.get("examples") or raw.get("llive_applications") or []
    description = str(raw.get("description", "") or raw.get("brief", "") or raw.get("jp", ""))
    return Principle(
        id=int(raw["id"]),
        name=str(raw.get("name", "")),
        description=description,
        examples=tuple(str(e) for e in examples),
    )


def _coerce_attribute(raw: dict[str, Any]) -> Attribute:
    description = str(raw.get("description", "") or raw.get("jp", ""))
    return Attribute(
        id=int(raw["id"]),
        name=str(raw.get("name", "")),
        description=description,
    )


def _unwrap_list(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in ("principles", "attributes", "features", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [d for d in value if isinstance(d, dict)]
    return []


@lru_cache(maxsize=1)
def load_principles() -> dict[int, Principle]:
    path = _resource_path("triz_principles.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = _unwrap_list(data)
    return {p.id: p for p in (_coerce_principle(r) for r in items)}


@lru_cache(maxsize=1)
def load_attributes() -> dict[int, Attribute]:
    path = _resource_path("triz_attributes.yaml", "triz_features.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = _unwrap_list(data)
    return {a.id: a for a in (_coerce_attribute(r) for r in items)}


@lru_cache(maxsize=1)
def load_matrix() -> dict[tuple[int, int], tuple[int, ...]]:
    """Contradiction matrix → dict[(improving, worsening)] = (principle_ids,).

    Supports two on-disk shapes:
        1. dict: ``improving_id -> {worsening_id: [principle_ids]}`` (compact form)
        2. list of rows: ``[{improving: i, worsening: w, principles: [...]}, ...]``
    """
    path = _resource_path("triz_contradiction_matrix.yaml", "triz_matrix_compact.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    matrix: dict[tuple[int, int], tuple[int, ...]] = {}
    if isinstance(data, dict):
        # try nested form first
        nested_ok = False
        for improving, inner in data.items():
            if isinstance(improving, int) and isinstance(inner, dict):
                nested_ok = True
                for worsening, principles in inner.items():
                    if isinstance(worsening, int) and isinstance(principles, list):
                        matrix[(int(improving), int(worsening))] = tuple(int(p) for p in principles)
        if nested_ok:
            return matrix
        rows = data.get("matrix") or data.get("rows") or []
    else:
        rows = data or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            improving = int(row["improving"])
            worsening = int(row["worsening"])
        except (KeyError, TypeError, ValueError):
            continue
        principles = tuple(int(p) for p in (row.get("principles") or []))
        matrix[(improving, worsening)] = principles
    return matrix


def lookup_principles(improving: int, worsening: int) -> list[Principle]:
    matrix = load_matrix()
    principles = load_principles()
    ids = matrix.get((int(improving), int(worsening)), ())
    return [principles[i] for i in ids if i in principles]
