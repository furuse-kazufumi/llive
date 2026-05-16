# Proposal — Brief API + LLM Backend (LLIVE-001 / LLIVE-002)

> **Status:** draft (2026-05-16). Not yet implemented. Captures the design
> the maintainer agreed to after the A/B run that produced
> `docs/BUGS_2026-05-16_brief_ab.md`.

## Why

The 2026-05-16 Brief A/B run showed that `FullSenseLoop.process(Stimulus)`
is a thinking-evaluator, not a doing-agent. To deliver on the FullSense
positioning vs Claude Code / Codex / Gemini, llive needs:

1. **LLIVE-001** — an LLM backend wired into `_inner_monologue` (and
   eventually into curiosity scoring).
2. **LLIVE-002** — a Brief API (CLI + MCP tool) so external clients
   (lldesign / lltrade / planned llcad / lleda / llchip) can submit
   structured work.

This proposal sketches the smallest design that closes both gaps without
breaking the existing 6-stage loop semantics or the C-1 Approval Bus.

## Non-goals (explicitly)

- Replacing the existing `FullSenseLoop` sandbox semantics
- Routing Brief outputs to a "real" production output bus (that's the
  separate C-2 work on `ProductionOutputBus` + `@govern`)
- Multi-agent orchestration (Briefs are single-agent for v0.7)
- Web UI (CLI + MCP only for v0.7)

## API surface

### 1. Brief schema (YAML, parsed to dataclass)

```yaml
# Minimum viable Brief — every field has a sensible default except `goal`.
brief_id: webpage-portal-refresh-2026-05-16
goal: |
  Refactor docs/index.md to render Mermaid correctly under just-the-docs.
constraints:
  - "no inline HTML inside fenced ```mermaid``` blocks"
  - "preserve all existing external links"
source: portal:fullsense
priority: 0.7
epistemic_type: pragmatic
backend: ollama:qwen2.5:14b      # default: env LLIVE_DEFAULT_BACKEND
tools:                            # whitelist of tools the agent may call
  - read_file
  - write_file
  - run_shell
success_criteria:
  - "rendered HTML at /docs/index.md contains an SVG, not raw mermaid text"
  - "no broken external links (Lychee passes)"
approval_required: true           # default: true; gates PROPOSE+INTERVENE
ledger_path: ~/.llive/briefs/webpage-portal-refresh-2026-05-16.db
```

### 2. Python API

```python
# src/llive/brief/types.py
@dataclass
class Brief:
    brief_id: str
    goal: str
    constraints: tuple[str, ...] = ()
    source: str = "manual"
    priority: float = 0.5
    epistemic_type: EpistemicType = EpistemicType.PRAGMATIC
    backend: str = ""              # "" -> resolve from env
    tools: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    approval_required: bool = True
    ledger_path: Path | None = None

# src/llive/brief/runner.py
class BriefRunner:
    def __init__(
        self,
        *,
        loop: FullSenseLoop,
        backend: LLMBackend,
        approval_bus: ApprovalBus,
        ledger: SqliteLedger,
        tools: Mapping[str, ToolHandler],
    ) -> None: ...

    def submit(self, brief: Brief) -> BriefResult: ...
```

### 3. LLM backend protocol

```python
# src/llive/llm/backend.py
class LLMBackend(Protocol):
    """The minimum surface llive's loop calls."""

    def complete(self, prompt: str, *, max_tokens: int = 4096,
                 temperature: float = 0.2) -> str: ...

    def supports_tools(self) -> bool: ...

    def name(self) -> str: ...   # e.g. "ollama:qwen2.5:14b"

# src/llive/llm/ollama_backend.py
class OllamaBackend:
    """Default implementation. URL from LLIVE_OLLAMA_URL or http://localhost:11434"""
```

### 4. CLI

```bash
# Submit a Brief file
llive brief submit path/to/brief.yaml

# Inline Brief (single-line goal)
llive brief submit --goal "Refactor docs/index.md ..." --priority 0.8

# Inspect ledger
llive brief ledger --brief-id webpage-portal-refresh-2026-05-16

# Resume a paused Brief (e.g. after an approval prompt)
llive brief resume <brief_id>
```

### 5. MCP tool

```jsonc
// Added to src/llive/mcp/tools.py
{
  "name": "submit_brief",
  "description": "Submit a Brief to llive for processing. Returns brief_id; poll with brief_status.",
  "inputSchema": {
    "type": "object",
    "required": ["goal"],
    "properties": {
      "goal": {"type": "string"},
      "constraints": {"type": "array", "items": {"type": "string"}},
      "source": {"type": "string", "default": "mcp"},
      "priority": {"type": "number", "minimum": 0, "maximum": 1},
      "backend": {"type": "string"},
      "tools": {"type": "array", "items": {"type": "string"}},
      "success_criteria": {"type": "array", "items": {"type": "string"}},
      "approval_required": {"type": "boolean", "default": true}
    }
  }
}
```

## Loop integration

`BriefRunner.submit(brief)` shape:

```
1. Translate Brief -> Stimulus(content=goal+constraints, source, surprise=priority,
                               epistemic_type)
2. record_brief(ledger, brief)                       # SIL axis
3. loop.process(stim) -> result                      # current 6-stage loop
4. if result.plan.decision in {PROPOSE, INTERVENE} and brief.approval_required:
       decision = approval_bus.request(action=...)   # blocks for HITL via llove
       if decision == REJECTED: return BriefResult(status='rejected', ...)
5. Execute tool calls in result.plan.tools  (whitelist-checked against brief.tools)
6. record_outcome(ledger, brief.brief_id, result, tool_outputs)
7. return BriefResult(status='completed', artifacts=..., ledger_entries=...)
```

Key invariants:

- **C-1 Approval Bus is on the path** — closes LLIVE-008
- **Tool whitelist enforced by `BriefRunner`, not by the LLM** — closes the
  "LLM hallucinates `rm -rf`" failure mode (RPAR axis)
- **Ledger record per stage** — Brief, Stimulus, plan, each tool call, final
  outcome — for reproducibility (SIL axis)

## Backwards compatibility

- Existing `loop.process(Stimulus)` API unchanged. `BriefRunner` calls it.
- Existing `ResidentRunner` unchanged. `BriefRunner` is a separate single-shot
  driver. They can co-exist; a `BriefSource` `StimulusSource` adapter can
  feed BriefRunner-emitted Stimuli into ResidentRunner if desired.

## Test plan (TDD order)

1. `tests/brief/test_brief_schema.py` — Brief YAML round-trip, defaults,
   validation errors
2. `tests/llm/test_backend_protocol.py` — `LLMBackend` Protocol shape +
   a `FakeBackend` for tests
3. `tests/brief/test_runner_no_tools.py` — submit a Brief, FakeBackend
   returns canned text, BriefResult has expected status + ledger rows
4. `tests/brief/test_runner_with_tools.py` — whitelist enforced, tool call
   recorded
5. `tests/brief/test_runner_approval_block.py` — `approval_required=True` +
   `PROPOSE` decision -> Approval Bus called -> reject path -> Brief status
6. `tests/cli/test_brief_subcommand.py` — `llive brief submit ...` round-trip
7. `tests/mcp/test_submit_brief_tool.py` — MCP tool returns brief_id +
   ledger entry recorded
8. `tests/integration/test_brief_real_ollama.py` — opt-in (env
   `LLIVE_TEST_OLLAMA=1`) — hit a real local Ollama, expect non-empty
   completion (smoke only, no semantic check)

## Effort estimate

| Step | Effort |
|---|---|
| Brief schema + dataclass + YAML loader | 0.5 day |
| `LLMBackend` Protocol + FakeBackend + OllamaBackend | 0.5 day |
| `BriefRunner` core (steps 1-3, 6, 7) | 0.5 day |
| Approval Bus integration (step 4) | 0.5 day |
| Tool whitelist + execution (step 5) | 0.5 day |
| CLI `llive brief ...` | 0.5 day |
| MCP `submit_brief` tool | 0.5 day |
| Tests 1-7 | 1.0 day |
| Integration test 8 + docs | 0.5 day |
| **Total** | **~5 days** for v0.7.0 |

## Out of scope (parked for v0.8+)

- Streaming Brief progress to llove (push API) — v0.8
- Multi-Brief parallelism with budget allocation — v0.8
- LLM-tool calling auto-loop (the LLM picks which tool, llive executes,
  result goes back to LLM) — v0.8; v0.7 has the LLM emit a flat list of
  tool calls in its plan and BriefRunner executes them in order
- Production output bus (`@govern` + ProductionOutputBus) — separate C-2
  work, depends on v0.7 stability

## Cross-references

- Bug list this proposal closes: `docs/BUGS_2026-05-16_brief_ab.md`
- Probe used to find the gaps: `scripts/run_brief.py`
- Competitor benchmark methodology:
  `~/.claude/.../memory/feedback_competitor_benchmark.md`
- FullSense umbrella roadmap entry:
  `https://furuse-kazufumi.github.io/fullsense/roadmap.html`
- ll{domain} clients that will exercise this API first:
  - `D:/projects/lldesign/` (design Briefs)
  - `D:/projects/lltrade/` (trading research Briefs, paper-only)
