# SPDX-License-Identifier: Apache-2.0
"""Per-page-type JSON Schemas (LLW-03).

Schemas live in ``specs/wiki_schemas/`` (development tree) and are mirrored
into ``src/llive/_specs/wiki_schemas/`` for wheel-shipped use. Loaders try
the packaged copy first, then fall back to the dev tree.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

KNOWN_PAGE_TYPES = (
    "domain_concept",
    "experiment_record",
    "failure_post_mortem",
    "principle_application",
)


class WikiSchemaError(Exception):
    def __init__(self, page_type: str, errors: list[str]) -> None:
        self.page_type = page_type
        self.errors = errors
        super().__init__(f"{page_type} validation failed: " + "; ".join(errors))


def _packaged_dir() -> Path | None:
    here = Path(__file__).resolve()
    candidate = here.parent.parent / "_specs" / "wiki_schemas"
    return candidate if candidate.is_dir() else None


def _dev_dir() -> Path | None:  # pragma: no cover - dev-tree fallback only
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "specs" / "wiki_schemas"
        if cand.is_dir():
            return cand
    return None


def _schema_path(page_type: str) -> Path:
    fname = f"{page_type}.v1.json"
    packaged = _packaged_dir()
    if packaged is not None and (packaged / fname).exists():
        return packaged / fname
    dev = _dev_dir()  # pragma: no cover - dev fallback
    if dev is not None and (dev / fname).exists():  # pragma: no cover
        return dev / fname
    raise FileNotFoundError(f"wiki schema not found for page_type {page_type!r}")  # pragma: no cover


@cache
def _load_schema(page_type: str) -> dict[str, Any]:
    with _schema_path(page_type).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_page_fields(page_type: str, fields: dict[str, Any]) -> None:
    if page_type not in KNOWN_PAGE_TYPES:
        raise WikiSchemaError(page_type, [f"unknown page_type (known: {KNOWN_PAGE_TYPES})"])
    schema = _load_schema(page_type)
    validator = Draft202012Validator(schema)
    errors: list[ValidationError] = sorted(validator.iter_errors(fields), key=lambda e: e.path)
    if errors:
        msgs = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]
        raise WikiSchemaError(page_type, msgs)


def list_page_types() -> list[str]:
    return list(KNOWN_PAGE_TYPES)
