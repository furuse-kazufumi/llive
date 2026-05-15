# 9 axes hit production in 2 days — llive v0.6.0 update

> Two days after [my previous post (2026-05-14)](./post_2026-05-14_overview.en.md),
> `llmesh-llive` went from "8 design pillars" to "9-axis MVP skeleton complete +
> first axis production-hardened + dual-license switch". Posting a short update
> just to capture the pace.

## What changed (2026-05-14 → 2026-05-16)

| Area | 2026-05-14 (previous) | 2026-05-16 (now) |
|---|---|---|
| Tests | 444 PASS | **815 PASS** (+371) |
| Architecture axes | 8 design pillars | **9-axis skeleton complete** (KAR / DTKR / APO / ICP / TLB / Math / PM / RPAR / SIL) |
| Conformance Manifest | not tracked | **holds=24 / violated=0 / undecidable=1** |
| Approval Bus | in-memory MVP | **production-hardened with policy + SQLite ledger** (C-1 done) |
| License | MIT | **Apache-2.0 + Commercial dual-license** (v0.6.0) |
| Governance | LICENSE only | NOTICE / CONTRIBUTING (DCO) / SECURITY / TRADEMARK |
| SPDX headers | none | **204 `.py` files now carry `SPDX-License-Identifier: Apache-2.0`** |

## The 9-axis skeleton — final shape of FullSense Spec v1.1

We extended FullSense Spec to 9 axes and shipped a minimal implementation for each:

- **KAR (Knowledge Autarky)** — long-term roadmap to extend RAD from 49 → 100 domains
- **DTKR (Disk-Tier Knowledge Routing)** — disk-side MoE, one skill = one file for modular evolution
- **APO (Autonomous Performance Optimization)** — self-tuning under §E2 bounded modification
- **ICP (Idle-Collaboration Protocol)** — peer Local LLM mesh during idle time (LLMesh-style)
- **TLB (Thought Layer Bridge)** — manifold cache + global coordinator to control multi-perspective combinatorics
- **Math Toolkit** — each axis pulls mathematical grounding from RAD corpora
- **PM (Publication Media)** — asciinema / SVG / GIF / mp4 embedded into README
- **RPAR (Robotic Process Automation Realisation)** — staged Sandbox → Permitted-action migration
- **SIL (Self-Interrogation Layer)** — 5 interrogators challenge the agent from multiple angles

Conformance Manifest sits at **holds=24 / violated=0**, so the 9-axis MVP is spec-conformant.

## Approval Bus, production-hardened (C-1 done)

When an RPA layer takes real-world side effects, the approval bus is the load-bearing piece.
The v0.5.x implementation was in-memory only. v0.6.0 ships:

- **Policy abstraction** — `AllowList`, `DenyList`, `CompositePolicy`, plus a `deny_overrides(allow, deny)` helper for the typical "deny-first" composition
- **SQLite persistence** — stdlib `sqlite3` only. Schema v1 (requests / responses / meta), replay survives a restart
- **Backward compatible** — `ApprovalBus()` with no args behaves exactly like before (all 8 legacy tests untouched)

Next: integrate `@govern(policy)` into ProductionOutputBus (C-2).

## Why dual-license

To keep OSS adoption frictionless while reducing long-term patent exposure and preserving room for commercial deals, v0.6.0 switches from MIT to **Apache-2.0 + Commercial**:

- Apache-2.0 — explicit **patent grant** for users, retaliation clause reduces contributor patent risk
- Commercial — for organisations that need SLA, indemnification, or closed-source integration

NOTICE / CONTRIBUTING (DCO 1.1) / SECURITY / TRADEMARK files were added in the same pass to match the OSS conventions familiar from the `@apache` / `@cncf` world.

## Career-side takeaways

Adding to the list from the previous post, these two days produced four new "design judgments" worth keeping:

1. **9-axis spec pinned by unit tests** — instead of formal verification, a runtime conformance manifest is checked every CI run
2. **Production-hardening an approval bus** — auto-policy + persistent ledger + backward compatibility, all retrofitted without breaking changes
3. **Drawing the OSS / commercial line** — being able to explain *why* dual-license is appropriate, in a vocabulary that stakeholders accept
4. **SPDX / NOTICE / DCO / SBOM operations** — treating *license quality* as a CI signal, not just code quality

#3 in particular is the place where AI startups and regulated-industry AI teams **stall on documentation**, not on engineering.

## Numbers as of today

- **v0.6.0** (cut today) — 9-axis skeleton + C-1 production + dual-license
- **815 tests / ruff clean** (v0.5.0 was 444 + 371 added since)
- PyPI: `pip install llmesh-llive`
- 4 repositories in parallel: llive / llmesh / llove / llmesh-demos

## What I want to demonstrate

In short: **an individual side project can sustain this pace** when the roadmap is concrete, tests are written first (so 0→1 estimates don't drift), and the spec is pinned in CLAUDE.md + CONTRIBUTING.md (so decisions don't loop).

> GitHub: <https://github.com/furuse-kazufumi/llive>
> PyPI: `pip install llmesh-llive`

#AI #LLM #ContinualLearning #MLOps #OpenSource #ApacheLicense #IndieDev
