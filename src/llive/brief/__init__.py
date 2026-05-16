# SPDX-License-Identifier: Apache-2.0
"""Brief API — structured work units submitted to llive.

A *Brief* is the smallest unit of externally-submitted work llive accepts.
External clients (lldesign, lltrade, planned llcad/lleda/llchip, MCP callers)
publish a Brief; the :class:`~llive.brief.runner.BriefRunner` translates it
into a :class:`~llive.fullsense.types.Stimulus`, drives the existing 6-stage
FullSense loop, gates PROPOSE/INTERVENE through the Approval Bus, executes
whitelisted tools, and records every stage in the SIL ledger.

Public surface (kept minimal for v0.7.0):

* :class:`Brief` — dataclass; the parsed YAML or programmatic submission.
* :class:`BriefStatus` — terminal status of a Brief run.
* :class:`BriefResult` — return value from :meth:`BriefRunner.submit`.
* :func:`load_brief` — YAML → :class:`Brief` parser used by the CLI and MCP.
* :func:`brief_to_dict` — round-trip helper used by the ledger and tests.

The :class:`~llive.brief.runner.BriefRunner` is exported lazily to avoid an
import-time cycle with :mod:`llive.fullsense.loop`.
"""

from __future__ import annotations

from llive.brief.types import (
    Brief,
    BriefResult,
    BriefStatus,
    BriefValidationError,
    brief_to_dict,
)
from llive.brief.loader import load_brief, loads_brief
from llive.brief.ledger import BriefLedger, LedgerRecord, TraceGraph, default_ledger_path
from llive.brief.runner import BriefRunner, ToolHandler
from llive.brief.governance import (
    GovernanceConfig,
    GovernanceScorer,
    GovernanceVerdict,
)
from llive.brief.grounding import (
    BriefGrounder,
    GroundedBrief,
    GroundingConfig,
    RadCitation,
    TrizCitation,
)

__all__ = [
    "Brief",
    "BriefGrounder",
    "BriefLedger",
    "BriefResult",
    "BriefRunner",
    "BriefStatus",
    "BriefValidationError",
    "GovernanceConfig",
    "GovernanceScorer",
    "GovernanceVerdict",
    "GroundedBrief",
    "GroundingConfig",
    "LedgerRecord",
    "RadCitation",
    "ToolHandler",
    "TraceGraph",
    "TrizCitation",
    "brief_to_dict",
    "default_ledger_path",
    "load_brief",
    "loads_brief",
]
