# Bugs / Gaps from Brief A/B run — 2026-05-16

> Source: `scripts/run_brief.py` invoked with the lldesign skeleton Brief.
> Comparison baseline: a human-equivalent agent (Claude Code) that produced
> the same 13-file lldesign + 14-file lltrade skeletons in the same session.
> Method captured in `feedback_competitor_benchmark.md`.

## Headline finding

**llive's `FullSenseLoop` is currently a thinking-evaluator, not a doing-agent.**
A Brief comes in, salience / curiosity / thought / ego / altruism scores come
out, and the result is an `ActionPlan(decision=note)`. No code is generated,
no file is written, no LLM is consulted. The gap between "what a Brief is"
and "what llive does with it" is the entire delivery surface for v0.2.x.

## Bug list (severity-ordered)

### 🔴 CRITICAL — gap

#### LLIVE-001 — no LLM backend wired into FullSenseLoop  *[CORRECTED + RESOLVED 2026-05-16]*
- **Correction (re: implementation status):** The `llive.llm` module
  already shipped `LLMBackend / OllamaBackend / AnthropicBackend /
  OpenAIBackend / MockBackend` (Phase C-1.0). The original wording
  "no LLM backend" was inaccurate — the backend layer existed; what was
  missing was the **wiring** from `FullSenseLoop._inner_monologue` to
  any of them. See `feedback_implementation_status_record` for the
  4-tier status taxonomy that this episode produced.
- **Status:** Wired in 2026-05-16 (this session). `FullSenseLoop(llm_backend=...)`
  injection and `LLIVE_LLM_BACKEND=ollama:<model>` env opt-in both
  available. Default (no env, no kwarg) keeps the rule-based template
  path active — backward-compatible.
- **Purity guard:** cloud backends (anthropic / openai / ...) refused
  unless `LLIVE_ALLOW_CLOUD_BACKEND=1` is set. See
  `feedback_llive_measurement_purity` for the measurement-design rationale.
- **Tests added:** 9 (injection / fallback on raise / fallback on empty /
  env-mock = template / env-anthropic refused / env-openai refused /
  cloud override resolves / ollama path open).
- **Empirical confirmation:** `LLIVE_LLM_BACKEND=ollama:llama3.2
  py -3.11 scripts/run_brief.py --json "hi"` returns a real LLM thought
  ("That's an unusual greeting...") instead of the template echo.

#### LLIVE-002 — no Brief API (CLI / MCP) exposed
- **What:** The only public entry point is `FullSenseLoop.process(Stimulus)` —
  there is no CLI command (`llive brief <text>`), no MCP `submit_brief` tool,
  no REST endpoint for external callers (e.g., ll{domain} clients) to enqueue
  Briefs.
- **Impact:** ll{domain} products (lldesign / lltrade / planned llcad / lleda /
  llchip) cannot delegate work into llive without writing custom scaffolding.
- **Reproduction:** `grep -rn 'def tool_submit\|brief' src/llive/mcp/tools.py`
  → 0 matches.
- **Fix sketch:**
  1. Add `submit_brief(text, source, surprise, epistemic_type) -> brief_id`
     to `src/llive/mcp/tools.py`.
  2. Add `llive brief <text-or-file>` to the Typer CLI in `src/llive/cli.py`.
  3. Define a YAML/JSON Brief schema (goal, constraints, tools, success criteria).
- **Estimated effort:** 2 days (schema + CLI + MCP + tests).

### 🟠 HIGH — semantic shallow

#### LLIVE-003 — `thought` is template, not generation
- **What:** `_inner_monologue` ignores the Brief body beyond the first 140
  chars. Output is always `Observation about '{source}': {content[:140]}… —
  novel territory, worth exploring.`
- **Impact:** No real reasoning, no plan decomposition, no constraint
  extraction. Downstream stages run on a placeholder.
- **Reproduction:** Same as LLIVE-001 — see `stages.thought.text`.
- **Fix:** depends on LLIVE-001.

#### LLIVE-004 — TRIZ detection is empty for natural-language Briefs
- **What:** `thought.triz_principles = []` even for Briefs that obviously
  describe a contradiction (e.g., "low cost AND high reliability").
- **Impact:** TRIZ 40 principles knowledge is in the codebase but never
  surfaced for natural-language input. Listed as a differentiator
  ([[project_llive]]) but not delivered.
- **Reproduction:** Run the lldesign Brief — has no exact TRIZ keywords →
  empty `triz_principles`. Should at least detect "modular" → principle 1
  (Segmentation), "asymmetric" → principle 4, etc.
- **Fix:** widen the keyword detector to morphological matches; or back it
  by a small classifier; or hand it to the (missing) LLM.

#### LLIVE-005 — `ego_score / altruism_score` look hardcoded
- **What:** Both scores returned 0.1 for a long, content-rich Brief.
- **Impact:** Loss of signal — the "ego vs altruism" axis can't differentiate
  briefs.
- **Reproduction:** See run result; vary `--surprise` / `--epistemic` flags —
  scores don't move.
- **Fix:** inspect `EgoAltruismScorer.score()`; either pass through Brief
  content or document this as a deliberate baseline.

### 🟡 MEDIUM — UX / portability

#### LLIVE-006 — `run_brief.py` crashes on Windows cp932 stdout
- **Status:** **fixed in this session** — added `sys.stdout.reconfigure(encoding="utf-8")`.
- **Why it matters:** any future demo script must include the same guard, or
  output a JSON-only line to a file. Document in CONTRIBUTING.

#### LLIVE-007 — `process()` returns `None` from `_inner_monologue` on stages that fail salience
- **Status:** documented design (`SILENT` path), but the stage dict for
  short-circuited cycles is sparse and hard to diff in A/B runs.
- **Fix:** always populate `stages.thought = None` (or a placeholder) so
  diff tools don't have to guess.

#### LLIVE-008 — Approval Bus is not exercised by `FullSenseLoop`
- **What:** The C-1 Approval Bus + SQLite Ledger are described as the v0.6
  flagship feature, but `FullSenseLoop.process()` does not call them. The
  decisions emitted (NOTE / PROPOSE / INTERVENE) bypass the Ledger.
- **Impact:** No audit trail for Brief processing — the SIL differentiator
  vs Claude Code / Perplexity / Codex / Gemini isn't actually delivered yet
  on the Brief path.
- **Fix:** wire the loop's `_finalise` to record every cycle in the Ledger;
  gate `PROPOSE` and `INTERVENE` on the Approval Bus.

## What the same Brief produced via the human-equivalent agent

- 13 files written under `D:/projects/lldesign/` (README, LICENSE, NOTICE,
  SECURITY, CONTRIBUTING, pyproject, src/__init__, docs/{_config, index,
  SPEC, PROGRESS, NOTES}, tests/test_smoke)
- pytest passing (2 passed)
- git init + initial commit + remote add + push to
  `git@github.com:furuse-kazufumi/lldesign.git`
- portal-side `docs/index.md` Family Tree updated, `docs/roadmap.md` +
  `docs/comparison.md` created and pushed
- ~6 minutes of wall clock

llive currently produces: **one ActionPlan(decision=note)** in 0.14 ms.

The gap is structural, not a parameter tweak.

## Suggested resolution order

1. **LLIVE-001 + LLIVE-002 (week 1)** — close the LLM + Brief API gap. After
   this, the bug is "the agent is dumb", not "there is no agent."
2. **LLIVE-008 (week 1, same PR cluster)** — wire Ledger so v0.6 SIL claim
   becomes truthful on the Brief path.
3. **LLIVE-003 + LLIVE-004 (week 2)** — improve thought quality and TRIZ
   coverage once the LLM is wired.
4. **LLIVE-005 (week 2)** — re-baseline EgoAltruismScorer or document the
   baseline.
5. **LLIVE-006 + LLIVE-007 (incidental)** — fold into next docs / demo PR.

## Cross-references

- `scripts/run_brief.py` — the A/B probe used to generate this report
- `D:/projects/lldesign/` and `D:/projects/lltrade/` — human-equivalent skeleton outputs
- `~/.claude/.../memory/feedback_competitor_benchmark.md` — benchmark methodology
- `~/.claude/.../memory/feedback_webpage_research_first.md` — research-first principle
