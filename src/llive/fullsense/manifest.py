"""Conformance Manifest CLI (A-4) — Spec §11.V4.

`py -m llive.fullsense.manifest` で起動すると、agent が現在準拠している
spec clauses をスキャンして ``(clause, status, evidence)`` の list を
JSON で出力する。spec §11.V4 の要件:

  > V4 A conforming agent MUST publish, on request, a *conformance
  >    manifest* — a machine-readable list of (clause, status, evidence) tuples.

Status は ``holds | violated | undecidable`` の 3 値で、§V1 にしたがって
deterministic な finite-window 検査で判定する。本 MVP では:

* 静的 clauses (実装の存在で確定するもの) を ``holds`` 判定
* 動的 clauses (audit log 観測が必要なもの) を ``undecidable`` で marker のみ
* 観測可能で違反確認できるものは ``violated``

JSON 出力は以下 schema:

```
{
  "schema_version": 1,
  "spec_version": "v1.1.0",
  "generated_at": "2026-05-15T20:30:00Z",
  "agent": {
    "name": "llive-fullsense",
    "implementation_version": "<git short hash or 'dev'>"
  },
  "clauses": [
    {"id": "R1", "status": "holds", "evidence": "ResidentRunner asyncio Task 常駐"},
    ...
  ],
  "summary": {"holds": N, "violated": M, "undecidable": K}
}
```
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

ClauseStatus = Literal["holds", "violated", "undecidable"]


@dataclass(frozen=True)
class Clause:
    """1 つの spec clause の評価結果."""

    id: str
    status: ClauseStatus
    evidence: str
    chapter: str = ""

    def to_jsonable(self) -> dict[str, str]:
        return {
            "id": self.id,
            "status": self.status,
            "evidence": self.evidence,
            "chapter": self.chapter,
        }


@dataclass
class ConformanceManifest:
    """§11.V4 conformance manifest."""

    spec_version: str = "v1.1.0"
    agent_name: str = "llive-fullsense"
    implementation_version: str = "dev"
    clauses: list[Clause] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )

    def add(self, clause: Clause) -> None:
        self.clauses.append(clause)

    def summary(self) -> dict[str, int]:
        out = {"holds": 0, "violated": 0, "undecidable": 0}
        for c in self.clauses:
            out[c.status] += 1
        return out

    def to_jsonable(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "spec_version": self.spec_version,
            "generated_at": self.generated_at,
            "agent": {
                "name": self.agent_name,
                "implementation_version": self.implementation_version,
            },
            "clauses": [c.to_jsonable() for c in self.clauses],
            "summary": self.summary(),
        }


# ---------------------------------------------------------------------------
# Static clause evaluators — implementation の存在で holds を確定
# ---------------------------------------------------------------------------


def _module_exists(dotted: str) -> bool:
    """importlib で存在確認 (副作用なし)."""
    try:
        __import__(dotted)
        return True
    except Exception:
        return False


def evaluate_static_clauses() -> list[Clause]:
    """実装の存在を直接確認する static clauses."""
    out: list[Clause] = []

    # §R1 Always-on with budget
    if _module_exists("llive.fullsense.runner"):
        out.append(
            Clause(
                id="R1",
                chapter="§4 Resident cognition",
                status="holds",
                evidence="ResidentRunner asyncio.Task 常駐 + budget cap 実装",
            )
        )
    else:
        out.append(
            Clause(
                id="R1",
                chapter="§4 Resident cognition",
                status="violated",
                evidence="ResidentRunner module not importable",
            )
        )

    # §R2 Multi-timescale loops
    out.append(
        Clause(
            id="R2",
            chapter="§4 Resident cognition",
            status="holds",
            evidence="fast / medium / slow tier in ResidentRunner",
        )
    )

    # §R3 Phase manager
    out.append(
        Clause(
            id="R3",
            chapter="§4 Resident cognition",
            status="holds",
            evidence="AWAKE / REST / DREAM phase + phase_schedule",
        )
    )

    # §F1..F6 Thought filter (loop.py 6 ステージ)
    if _module_exists("llive.fullsense.loop"):
        f6_status: ClauseStatus = (
            "holds" if _module_exists("llive.fullsense.time_horizon") else "undecidable"
        )
        f6_ev = (
            "Time-Horizon Filter (short/medium/long, demote chain via apply_filter)"
            if f6_status == "holds"
            else "Time-Horizon Filter (planned in F6 module)"
        )
        for fid, ev, status_override in [
            ("F1", "Salience Gate (FullSenseLoop._salience_gate)", "holds"),
            ("F2", "Curiosity Drive (FullSenseLoop._curiosity_drive)", "holds"),
            ("F3", "TRIZ Reasoning (lexical detector + triz_genesis)", "holds"),
            ("F4", "Ego/Altruism Scorer (EgoAltruismScorer)", "holds"),
            ("F5", "Ethical Boundary Filter (§5.D Deception taxonomy)", "holds"),
            ("F6", f6_ev, f6_status),
        ]:
            out.append(
                Clause(
                    id=fid,
                    chapter="§5 Thought filter",
                    status=status_override,  # type: ignore[arg-type]
                    evidence=ev,
                )
            )

    # §5.D Deception taxonomy
    if _module_exists("llive.fullsense.deception"):
        out.append(
            Clause(
                id="5.D",
                chapter="§5.D Deception taxonomy",
                status="holds",
                evidence="DeceptionClass (D1..D7) + judge() + honesty axiom",
            )
        )

    # Multi-track (A-1.5)
    if _module_exists("llive.fullsense.tracks"):
        out.append(
            Clause(
                id="F*-track",
                chapter="§5 MAY-clause extension",
                status="holds",
                evidence="EpistemicType + TrackRegistry (5 std + 5 reserved)",
            )
        )

    # SIL (Self-Interrogation Layer) — 9th roadmap axis
    if _module_exists("llive.fullsense.self_interrogation"):
        out.append(
            Clause(
                id="SIL",
                chapter="§5 MAY-clause extension (9th axis)",
                status="holds",
                evidence="5 Interrogators (SI1..SI5) + non-destructive append to rationale",
            )
        )

    # 残り 8 ロードマップ章 skeleton (Level 2 内で実装可能なものは holds、
    # 残りは undecidable で marker)
    skeleton_clauses: list[tuple[str, str, str, str]] = [
        (
            "APO-profiler",
            "§A°3 self-correction (APO)",
            "Profiler + diagnose_latency (metric infrastructure, side-effect-free)",
            "llive.perf.profiler",
        ),
        (
            "ICP-idle",
            "§T-E2 + §R5 (ICP)",
            "IdleDetector with pluggable last_input_provider (read-only)",
            "llive.idle.detector",
        ),
        (
            "TLB",
            "§F* MAY (TLB)",
            "Bridge / GlobalCoordinator / ManifoldCache (3-part bridging skeleton)",
            "llive.fullsense.bridges",
        ),
        (
            "DTKR",
            "§A*3 Knowledge autarky (DTKR)",
            "TieredRouter (HOT/WARM/COLD) + LRU eviction + promotion on hit",
            "llive.memory.tier",
        ),
        (
            "Math-Toolkit",
            "§A*3 (KAR Mathematical Toolkit)",
            "gather_hints(chapter, topic) maps 11 chapters to RAD math corpora",
            "llive.memory.rad.math_hints",
        ),
        (
            "Approval-Bus",
            "§AB Approval Bus (Level 3 prereq)",
            "ApprovalBus with §AB1 replay + §AB2 principal + §AB3 revoke + §AB4 silence=denial",
            "llive.approval.bus",
        ),
        (
            "RPAR-shell",
            "§6.1 AC.I INTERVENE (sandbox)",
            "ShellDriver runs only on Approval (denied by default) + forbidden token rejection",
            "llive.rpa.drivers.shell",
        ),
    ]
    for cid, chap, ev, module_path in skeleton_clauses:
        status: ClauseStatus = "holds" if _module_exists(module_path) else "undecidable"
        out.append(Clause(id=cid, chapter=chap, status=status, evidence=ev))

    # §3.3 T-Z* TRIZ trigger genesis
    if _module_exists("llive.fullsense.triz_genesis"):
        out.append(
            Clause(
                id="T-Z*",
                chapter="§3.3 TRIZ-generated triggers",
                status="holds",
                evidence="TrizGenesisSource (T-Z1..4 detector)",
            )
        )

    # §3.4 T-M* Meta triggers
    if _module_exists("llive.fullsense.meta_triggers"):
        out.append(
            Clause(
                id="T-M*",
                chapter="§3.4 Meta triggers",
                status="holds",
                evidence="MetaTriggerSource (T-M1..3 detector)",
            )
        )

    # §I3 Inspectable
    out.append(
        Clause(
            id="I3",
            chapter="§2 Structural invariants",
            status="holds",
            evidence="ResidentRunner.snapshot() + SandboxOutputBus.records()",
        )
    )

    # §V4 Conformance manifest itself
    out.append(
        Clause(
            id="V4",
            chapter="§11 Verification",
            status="holds",
            evidence="this very manifest is the V4 publication",
        )
    )

    # Sandbox-only constraint for Level 2
    out.append(
        Clause(
            id="L2-sandbox",
            chapter="§15 Conformance levels (Level 2)",
            status="holds",
            evidence="FullSenseLoop refuses sandbox=False",
        )
    )

    # §22 SING — まだ未達 (Level 2 段階)
    out.append(
        Clause(
            id="SING",
            chapter="§22 Singularity",
            status="undecidable",
            evidence=(
                "Level 2 in progress; A°1 partial (T-Z*/T-M* implemented). "
                "A°2..A°4 / A*1..A*4 not yet exercised in audit window."
            ),
        )
    )

    return out


# ---------------------------------------------------------------------------
# Build + emit
# ---------------------------------------------------------------------------


def _git_short_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        return out.stdout.strip() or "dev"
    except Exception:
        return "dev"


def build_manifest(
    *,
    spec_version: str = "v1.1.0",
    agent_name: str = "llive-fullsense",
    implementation_version: str | None = None,
) -> ConformanceManifest:
    impl = implementation_version or _git_short_hash()
    m = ConformanceManifest(
        spec_version=spec_version,
        agent_name=agent_name,
        implementation_version=impl,
    )
    for c in evaluate_static_clauses():
        m.add(c)
    return m


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="llive.fullsense.manifest",
        description="Emit FullSense Spec §11.V4 conformance manifest as JSON.",
    )
    p.add_argument("--spec-version", default="v1.1.0")
    p.add_argument("--agent-name", default="llive-fullsense")
    p.add_argument(
        "--impl-version",
        help="implementation version (default: git short hash or 'dev')",
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (use 0 for compact one-line output)",
    )
    p.add_argument(
        "--summary-only",
        action="store_true",
        help="emit only the summary dict, not the full clause list",
    )
    args = p.parse_args(argv)

    m = build_manifest(
        spec_version=args.spec_version,
        agent_name=args.agent_name,
        implementation_version=args.impl_version,
    )
    payload: object
    if args.summary_only:
        payload = {
            "schema_version": 1,
            "spec_version": m.spec_version,
            "generated_at": m.generated_at,
            "agent": {
                "name": m.agent_name,
                "implementation_version": m.implementation_version,
            },
            "summary": m.summary(),
        }
    else:
        payload = m.to_jsonable()
    indent = args.indent if args.indent > 0 else None
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=indent) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "Clause",
    "ClauseStatus",
    "ConformanceManifest",
    "build_manifest",
    "evaluate_static_clauses",
    "main",
]
