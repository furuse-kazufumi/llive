# SPDX-License-Identifier: Apache-2.0
"""YAML and dict loaders for :class:`~llive.brief.types.Brief`.

The loaders accept the canonical YAML shape from
``docs/proposals/brief_api_design.md``. Anything outside the documented
field set is rejected — unknown keys are almost always typos and silently
dropping them tends to hide bugs that surface much later in the loop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from llive.brief.types import Brief, BriefValidationError
from llive.fullsense.types import EpistemicType

# Field set must stay in sync with Brief — guard against silent drift.
_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "brief_id",
        "goal",
        "constraints",
        "source",
        "priority",
        "epistemic_type",
        "backend",
        "tools",
        "success_criteria",
        "approval_required",
        "ledger_path",
    }
)


def _coerce_string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        # Single bare string under a list-shaped key is almost always a YAML
        # mistake (forgot the dash). Reject loudly.
        raise BriefValidationError(
            f"{field_name} must be a list of strings, got a bare string {value!r}"
        )
    if not isinstance(value, (list, tuple)):
        raise BriefValidationError(
            f"{field_name} must be a list of strings, got {type(value).__name__}"
        )
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise BriefValidationError(
                f"{field_name}[{i}] must be a string, got {type(item).__name__}"
            )
        out.append(item)
    return tuple(out)


def _coerce_epistemic_type(value: Any) -> EpistemicType:
    if value is None:
        return EpistemicType.PRAGMATIC
    if isinstance(value, EpistemicType):
        return value
    if isinstance(value, str):
        try:
            return EpistemicType(value)
        except ValueError as exc:
            valid = ", ".join(e.value for e in EpistemicType)
            raise BriefValidationError(
                f"epistemic_type must be one of [{valid}], got {value!r}"
            ) from exc
    raise BriefValidationError(
        f"epistemic_type must be a string or EpistemicType, got {type(value).__name__}"
    )


def _coerce_ledger_path(value: Any) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        # Expand ``~`` so the YAML can portably reference the user home dir.
        return Path(value).expanduser()
    raise BriefValidationError(
        f"ledger_path must be a string or pathlib.Path, got {type(value).__name__}"
    )


def _from_mapping(payload: Mapping[str, Any]) -> Brief:
    unknown = set(payload) - _ALLOWED_KEYS
    if unknown:
        raise BriefValidationError(
            f"unknown Brief field(s): {sorted(unknown)!r}; allowed: {sorted(_ALLOWED_KEYS)!r}"
        )

    if "brief_id" not in payload:
        raise BriefValidationError("brief_id is required")
    if "goal" not in payload:
        raise BriefValidationError("goal is required")

    return Brief(
        brief_id=str(payload["brief_id"]),
        goal=str(payload["goal"]),
        constraints=_coerce_string_tuple(payload.get("constraints"), "constraints"),
        source=str(payload.get("source", "manual")),
        priority=float(payload.get("priority", 0.5)),
        epistemic_type=_coerce_epistemic_type(payload.get("epistemic_type")),
        backend=str(payload.get("backend", "")),
        tools=_coerce_string_tuple(payload.get("tools"), "tools"),
        success_criteria=_coerce_string_tuple(
            payload.get("success_criteria"), "success_criteria"
        ),
        approval_required=bool(payload.get("approval_required", True)),
        ledger_path=_coerce_ledger_path(payload.get("ledger_path")),
    )


def loads_brief(text: str) -> Brief:
    """Parse a YAML *string* into a :class:`Brief`."""
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise BriefValidationError(f"invalid YAML: {exc}") from exc
    if not isinstance(parsed, Mapping):
        raise BriefValidationError(
            f"Brief YAML must be a mapping, got {type(parsed).__name__}"
        )
    return _from_mapping(parsed)


def load_brief(path: str | Path) -> Brief:
    """Read a YAML file from disk and return a :class:`Brief`."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise BriefValidationError(f"Brief file not found: {p}")
    return loads_brief(p.read_text(encoding="utf-8"))
