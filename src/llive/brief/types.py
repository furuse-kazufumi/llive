# SPDX-License-Identifier: Apache-2.0
"""Type definitions for the Brief API.

Briefs are immutable: once parsed, the :class:`Brief` instance never changes.
This is intentional — the same Brief value is recorded in the ledger,
passed to the loop, and surfaced back to the caller in the
:class:`BriefResult`, so mutation in any of those places would corrupt
replay.

The dataclass uses ``frozen=True`` and tuples (not lists) for collection
fields to enforce hashability and structural immutability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from llive.fullsense.types import EpistemicType

# Brief IDs are used as filesystem path segments (ledger file names) and as
# DB primary keys; constrain them to ascii word + dash + dot so they can be
# safely shell-quoted and embedded in URLs without further escaping.
_BRIEF_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$")


class BriefValidationError(ValueError):
    """Raised when a :class:`Brief` field violates its contract.

    Distinct from generic ``ValueError`` so callers (CLI, MCP) can convert
    it to a structured user-facing error without catching unrelated
    bugs from deeper in the loop.
    """


class BriefStatus(StrEnum):
    """Terminal status of a Brief run.

    The values are stable wire-format strings — they appear in ledger rows,
    MCP responses, and CLI output, so renames are breaking changes.
    """

    COMPLETED = "completed"
    REJECTED = "rejected"            # Approval Bus denied PROPOSE / INTERVENE
    SILENT = "silent"                # Loop chose ActionDecision.SILENT — nothing to do
    AWAITING_APPROVAL = "awaiting_approval"  # paused — resume via CLI / MCP
    ERROR = "error"                  # internal failure; see ``BriefResult.error``


@dataclass(frozen=True)
class Brief:
    """Structured work unit submitted to llive.

    Only :attr:`goal` is required; everything else has a sensible default
    so MCP callers can submit a single-field Brief and still get a valid
    run.
    """

    brief_id: str
    goal: str
    constraints: tuple[str, ...] = ()
    source: str = "manual"
    priority: float = 0.5
    epistemic_type: EpistemicType = EpistemicType.PRAGMATIC
    # Empty string → BriefRunner resolves from env (LLIVE_DEFAULT_BACKEND or
    # the standard LLM backend resolution chain). Explicit value pins a
    # backend, e.g. ``ollama:qwen2.5:14b``.
    backend: str = ""
    tools: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    approval_required: bool = True
    ledger_path: Path | None = None

    def __post_init__(self) -> None:
        if not self.brief_id or not _BRIEF_ID_RE.match(self.brief_id):
            raise BriefValidationError(
                f"brief_id must match {_BRIEF_ID_RE.pattern}, got {self.brief_id!r}"
            )
        if not self.goal or not self.goal.strip():
            raise BriefValidationError("goal must be a non-empty string")
        if not 0.0 <= float(self.priority) <= 1.0:
            raise BriefValidationError(
                f"priority must be in [0.0, 1.0], got {self.priority!r}"
            )
        if not isinstance(self.constraints, tuple):
            raise BriefValidationError("constraints must be a tuple of strings")
        if not isinstance(self.tools, tuple):
            raise BriefValidationError("tools must be a tuple of strings")
        if not isinstance(self.success_criteria, tuple):
            raise BriefValidationError("success_criteria must be a tuple of strings")
        if self.ledger_path is not None and not isinstance(self.ledger_path, Path):
            raise BriefValidationError(
                f"ledger_path must be a pathlib.Path or None, got {type(self.ledger_path).__name__}"
            )


@dataclass
class BriefResult:
    """Return value from :meth:`~llive.brief.runner.BriefRunner.submit`.

    Mutable on purpose: a Brief that pauses for approval may be resumed and
    promoted from :attr:`BriefStatus.AWAITING_APPROVAL` to
    :attr:`BriefStatus.COMPLETED` without constructing a new result.

    **COG-01 Triple Output (2026-05-17)** — the three uncertainty-axis
    fields are always present so downstream consumers can rely on them:

    * ``confidence`` — derived from the loop's thought confidence and the
      tool execution success ratio (0.0 = no confidence, 1.0 = full).
    * ``assumptions`` — explicit assumptions surfaced during grounding
      (e.g. "Brief assumes ollama backend available"). Defaults to ``()``.
    * ``missing_evidence`` — gaps the runner couldn't fill itself; the LLM
      and downstream auditors should treat these as known unknowns.
    """

    brief_id: str
    status: BriefStatus
    rationale: str = ""
    artifacts: tuple[str, ...] = ()
    tool_outputs: tuple[Mapping[str, Any], ...] = ()
    ledger_entries: int = 0
    error: str | None = None
    # COG-01 — uncertainty axis triple
    confidence: float = 0.5
    assumptions: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()


def brief_to_dict(brief: Brief) -> dict[str, Any]:
    """Serialise a :class:`Brief` to a JSON/YAML-friendly dict.

    Tuples become lists, :class:`Path` becomes its POSIX string form, and
    :class:`EpistemicType` becomes its string value. The output round-trips
    through :func:`~llive.brief.loader.load_brief` (and is what the SIL
    ledger stores).
    """
    out: dict[str, Any] = {}
    for f in fields(brief):
        value = getattr(brief, f.name)
        if isinstance(value, tuple):
            out[f.name] = list(value)
        elif isinstance(value, Path):
            out[f.name] = value.as_posix()
        elif isinstance(value, EpistemicType):
            out[f.name] = value.value
        else:
            out[f.name] = value
    return out
