# A personal project to take LLM forgetting seriously — llive

> Designing and shipping `llmesh-llive`, a self-evolving modular-memory LLM framework.
> I'm building it both to **understand AI more deeply** and to **anchor my engineering career** around hard problems.

## Why I started

The more LLMs are pushed into real products, the more often the same wall shows up:

> Teach the model new knowledge, and somehow its old judgement breaks.

This **catastrophic forgetting** is one of the largest reasons AI adoption stalls in regulated industries and audit-driven environments. `llive` is my personal attempt to recast that pain into a design problem: *how do you absorb new capability continuously without retraining the giant frozen LLM core?*

In practice this turned out to be a topic that **both AI users and AI builders** are forced to reason about. Anyone who works on LLMs in production eventually has to defend their answer.

## The 8 design pillars of llive

1. **Frozen core, plastic periphery** — the decoder-only LLM core stays frozen. Adapters / LoRA / 4-layer external memory / variable-length BlockContainer absorb new capability.
2. **4 memory layers with separated responsibility** — semantic (knowledge), episodic (experience), structural (relations), parameter (delta weights).
3. **Declarative structure description** — sub-block sequences expressed in YAML, in units that the AI itself can propose and compare.
4. **Reviewed self-evolution** — only memory writes and minor routing changes happen online; structural mutations go through an offline review path.
5. **Biological memory directly embedded** — hippocampal–cortical consolidation cycles, surprise scoring, phase transitions.
6. **Promotion gated by formal verification** — Lean / Z3 / TLA+ check structural invariants *before* LLM-based evaluation runs.
7. **Native llmesh / llove integration** — industrial IoT sensors flow straight into episodic memory; HITL closes inside the TUI.
8. **TRIZ ideation built in** — the 40 inventive principles + 39×39 contradiction matrix + ARIZ + 9-windows are implemented as a mutation policy. Metric contradictions are auto-detected, mapped to principles, grounded in research corpora, and turned into CandidateDiffs autonomously.

## Why this matters for my career

LLM tooling moves fast and is easy to look fluent in without owning real depth. Building `llive` left me with a stack of **design decisions** I can defend, not just buzzwords:

- I can articulate, at the implementation level, how hard *production* continual learning really is.
- I now use formal verification (Lean / Z3 / TLA+) **before** LLM-based scoring as a way to cut evaluation cost and risk.
- I had to translate biological memory models into CS, which sharpened my ability to bridge fields.
- I implemented **TRIZ inventive principles as a mutation policy**, importing patent-world reasoning into ML systems.
- I built **Ed25519-signed adapters and a SHA-256 audit chain** into continual learning, getting close to what regulated-industry AI actually needs.

These are the kinds of skills that are asked for in AI startups, regulated-industry adoption teams, and research-oriented R&D groups alike.

## Where it stands today (2026-05-14)

- **v0.3.0** — Phase 3 (Controlled Self-Evolution MVR) + Phase 4 (Production Security MVR) shipped together.
- **429 tests / 98% coverage / 0 lint warnings**.
- Z3 static verifier, Failed Reservoir, Reverse-Evolution Monitor, TRIZ Self-Reflection, Ed25519 signed adapters, SHA-256 audit chain.
- Next: Phase 5+ Rust acceleration (requirements v0.7 defined; staged after Phase 4 + EVO stability).
- PyPI: `pip install llmesh-llive`.

## Where it's going

This OSS aims to become a **reference implementation engineers can argue from** when pushing AI adoption inside regulated environments. Pair `llive` with `llmesh` (on-prem MCP hub) and `llove` (TUI dashboard) and you get a continual-learning stack that stays off the cloud, preserves audit trails, and is observable on-site.

If this resonates, the easiest entry is `pip install llmesh-llive` — design decisions, failures, and the evolution itself are kept in the repo and docs as openly as I can.

> GitHub: <https://github.com/furuse-kazufumi/llive>
> PyPI: `pip install llmesh-llive`

#AI #LLM #ContinualLearning #MLOps #FormalVerification #OpenSource #IndieHacker #Career
