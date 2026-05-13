"""JSON Schema (Draft 2020-12) validator for llive YAML specs (BC-03)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from llive.schema.models import CandidateDiff, ContainerSpec, SubBlockSpec


class SchemaValidationError(Exception):
    """Raised when a YAML/JSON document fails schema validation."""

    def __init__(self, kind: str, errors: list[str]) -> None:
        self.kind = kind
        self.errors = errors
        msg = f"{kind} validation failed: " + "; ".join(errors)
        super().__init__(msg)


_SCHEMA_FILES = {
    "container-spec.v1": "container-spec.v1.json",
    "subblock-spec.v1": "subblock-spec.v1.json",
    "candidate-diff.v1": "candidate-diff.v1.json",
}


def _packaged_schema_path(filename: str) -> Path | None:
    """Look for the schema as a packaged resource at llive/_specs/schemas/."""
    here = Path(__file__).resolve()
    candidate = here.parent.parent / "_specs" / "schemas" / filename
    return candidate if candidate.exists() else None


def _project_root() -> Path:  # pragma: no cover - dev tree fallback only
    """Locate a development-tree project root with specs/schemas/."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "specs" / "schemas").is_dir():
            return parent
    raise RuntimeError("could not locate project root with specs/schemas/")


@cache
def _load_schema(name: str) -> dict[str, Any]:
    if name not in _SCHEMA_FILES:
        raise KeyError(f"unknown schema {name!r}")
    filename = _SCHEMA_FILES[name]
    # 1) prefer the schemas shipped inside the wheel
    packaged = _packaged_schema_path(filename)
    if packaged is not None:
        with packaged.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    # 2) fall back to the development tree (`specs/schemas/` at project root)
    root = _project_root()  # pragma: no cover - dev fallback
    schema_path = root / "specs" / "schemas" / filename  # pragma: no cover
    with schema_path.open("r", encoding="utf-8") as fh:  # pragma: no cover
        return json.load(fh)  # pragma: no cover


def _parse(text_or_obj: str | dict[str, Any] | Path) -> dict[str, Any]:
    if isinstance(text_or_obj, dict):
        return text_or_obj
    if isinstance(text_or_obj, Path):
        with text_or_obj.open("r", encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = text_or_obj  # pragma: no cover - covered by `str` direct input path
    return yaml.safe_load(text)


def _validate_against(name: str, data: dict[str, Any]) -> None:
    schema = _load_schema(name)
    validator = Draft202012Validator(schema)
    errors: list[ValidationError] = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        msgs = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]
        raise SchemaValidationError(name, msgs)


def validate_container_spec(source: str | dict[str, Any] | Path) -> ContainerSpec:
    data = _parse(source)
    _validate_against("container-spec.v1", data)
    return ContainerSpec.model_validate(data)


def validate_subblock_spec(source: str | dict[str, Any] | Path) -> SubBlockSpec:
    data = _parse(source)
    _validate_against("subblock-spec.v1", data)
    return SubBlockSpec.model_validate(data)


def validate_candidate_diff(source: str | dict[str, Any] | Path) -> CandidateDiff:
    data = _parse(source)
    _validate_against("candidate-diff.v1", data)
    return CandidateDiff.model_validate(data)


def get_schema(name: str) -> dict[str, Any]:
    """Public accessor for the raw JSON Schema (used by `llive schema show`)."""
    return _load_schema(name)


def known_schemas() -> list[str]:
    return list(_SCHEMA_FILES.keys())
