# Brief API — Quickstart (LLIVE-002)

> Implementation status: **shipped 2026-05-16** in `src/llive/brief/`.
> Design rationale lives in [`../proposals/brief_api_design.md`](../proposals/brief_api_design.md).

A *Brief* is the smallest unit of externally-submitted work llive accepts.
Use it when an external coding agent, lldesign / lltrade client, or an
MCP caller needs llive to drive its 6-stage FullSense loop on a specific
goal — with audit, approval gate, and tool whitelisting baked in.

## YAML form

```yaml
brief_id: portal-refresh-2026-05-16
goal: |
  Refactor docs/index.md to render Mermaid correctly under just-the-docs.
constraints:
  - "no inline HTML inside fenced ```mermaid``` blocks"
  - "preserve all existing external links"
source: portal:fullsense
priority: 0.7
epistemic_type: pragmatic
backend: ollama:qwen2.5:14b
tools:
  - read_file
  - write_file
success_criteria:
  - "rendered HTML at /docs/index.md contains an SVG"
approval_required: true
```

Only `brief_id` and `goal` are required — everything else has a sensible
default. Unknown keys are rejected loudly.

## CLI

```bash
# Submit a Brief file
llive brief submit path/to/brief.yaml

# Inline form
llive brief submit --goal "Refactor docs/index.md ..." --brief-id portal-refresh \
                   --priority 0.8 --no-approval

# Read the audit trail back
llive brief ledger portal-refresh-2026-05-16
llive brief ledger portal-refresh-2026-05-16 --json --limit 5
```

The ledger is append-only JSONL at
`$LLIVE_BRIEF_LEDGER_DIR/<brief_id>.jsonl` (default `~/.llive/briefs/`).

## Python

```python
from llive.brief import Brief, BriefRunner
from llive.fullsense.loop import FullSenseLoop

brief = Brief(brief_id="b1", goal="Discover a novel pattern")
loop = FullSenseLoop(sandbox=True)
runner = BriefRunner(loop=loop)
result = runner.submit(brief)

print(result.status.value, result.rationale)
```

## MCP

The `submit_brief` tool is registered alongside `query_rad`, `code_review`,
etc. Schema:

```jsonc
{
  "name": "submit_brief",
  "input_schema": {
    "type": "object",
    "required": ["goal"],
    "properties": {
      "goal": {"type": "string"},
      "brief_id": {"type": "string"},
      "constraints": {"type": "array", "items": {"type": "string"}},
      "source": {"type": "string", "default": "mcp"},
      "priority": {"type": "number", "minimum": 0.0, "maximum": 1.0},
      "backend": {"type": "string"},
      "tools": {"type": "array", "items": {"type": "string"}},
      "success_criteria": {"type": "array", "items": {"type": "string"}},
      "approval_required": {"type": "boolean", "default": true}
    }
  }
}
```

`brief_id` is auto-minted if omitted so single-shot MCP callers don't
need to manage identifiers.

## Pipeline invariants

For every Brief, `BriefRunner` records (in order):

1. `brief_submitted` — full Brief payload
2. `stimulus_built` — derived Stimulus envelope
3. `loop_completed` — every FullSense stage diagnostic
4. `decision` — final ActionPlan
5. *(if `approval_required` and decision is PROPOSE/INTERVENE)*
   `approval_requested` → `approval_resolved`
6. *(per tool call)* `tool_invoked` / `tool_rejected` / `tool_failed`
7. `outcome` — terminal BriefResult

Replay-friendly: the same Brief + same ledger trail produces the same
BriefResult. Timestamps live in a `meta` envelope that replay can ignore.

## Validation matrix (Brief overhead)

Measured 2026-05-16 across xs/s/m × {llama3.2:3b, qwen2.5:7b, qwen2.5:14b}
on-prem (Ollama). See `../benchmarks/2026-05-16-progressive-xss/` and
`../benchmarks/2026-05-16-progressive-m/` for the raw matrices.

LLM-only wall time is > 99.8 % of total wall time across every cell —
the Brief API + FullSense loop adds < 1 % overhead.
