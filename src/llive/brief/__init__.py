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
from llive.brief.eval_spec import (
    EvalEvaluator,
    EvalReport,
    EvalSpec,
    Metric,
    MetricResult,
    MetricsRegistry,
    StopCondition,
)
from llive.brief.premortem import (
    FailureScenario,
    PremortemGenerator,
    PremortemReport,
)
from llive.brief.prompt_lint import (
    LintFinding,
    LintReport,
    PromptLinter,
)
from llive.brief.roles import (
    ArchitectLens,
    AuditorLens,
    BlackHatLens,
    BlueHatLens,
    CriticLens,
    ExecutorLens,
    GreenHatLens,
    HatPerspective,
    MultiTrackSummary,
    PerspectiveLens,
    PerspectiveNote,
    RedHatLens,
    RoleBasedMultiTrack,
    RolePerspective,
    WhiteHatLens,
    YellowHatLens,
)

__all__ = [
    "ArchitectLens",
    "AuditorLens",
    "BlackHatLens",
    "BlueHatLens",
    "Brief",
    "BriefGrounder",
    "BriefLedger",
    "BriefResult",
    "BriefRunner",
    "BriefStatus",
    "BriefValidationError",
    "CriticLens",
    "ExecutorLens",
    "FailureScenario",
    "GovernanceConfig",
    "GovernanceScorer",
    "GovernanceVerdict",
    "GreenHatLens",
    "GroundedBrief",
    "GroundingConfig",
    "HatPerspective",
    "LedgerRecord",
    "LintFinding",
    "LintReport",
    "MultiTrackSummary",
    "PerspectiveLens",
    "PerspectiveNote",
    "PremortemGenerator",
    "PremortemReport",
    "PromptLinter",
    "RadCitation",
    "RedHatLens",
    "RoleBasedMultiTrack",
    "RolePerspective",
    "ToolHandler",
    "TraceGraph",
    "TrizCitation",
    "WhiteHatLens",
    "YellowHatLens",
    "brief_to_dict",
    "default_ledger_path",
    "load_brief",
    "loads_brief",
]
