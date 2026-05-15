# FullSense — Eternal Specification v1.1

> *A specification of autonomous-resident cognition meant to hold across substrates,
> civilizations, and millennia — independent of the implementation language,
> physical substrate, cultural value framework, and time scale of the underlying
> agent.*
>
> The name **FullSense** is derived from the initial author's surname,
> **Furuse** (古瀬). The conceptual frame — *autonomous-resident cognition
> with TRIZ-driven trigger genesis culminating in the dual-jiritsu
> singularity (§22)* — was proposed by **Furuse Kazufumi (古瀬 一史)** during
> the construction of the `llive` project (May 2026). This document is the
> formal articulation of that proposal.

| meta | value |
|---|---|
| spec id | `fullsense.eternal` |
| version | `1.1.0` |
| date | 2026-05-15 |
| status | normative draft |
| supersedes | v1.0.0 (added §22 SING; non-breaking MINOR per §C5) |
| principal author | **Furuse Kazufumi** (古瀬 一史) — conceptual originator, naming originator, initial steward |
| co-author (drafting) | Claude Opus 4.7 (1M context) — formal articulation under §I1 |
| stewardship | Furuse Kazufumi (initial steward); open for amendments under §13 |

## 0. Reading guide

This document defines an **architecture-agnostic contract** for a class of
cognitive systems we call *FullSense agents*. It does **not** prescribe
neural network shapes, programming languages, hardware substrates, value
weights, or political stances. It prescribes only:

* **Axioms** — non-negotiable foundational claims (§1)
* **Structural invariants** — properties any implementation MUST preserve (§2)
* **Functional contracts** — input/output and timing relations of named
  subsystems (§§3–7)
* **Ethical boundaries** — minimum constraints; jurisdictional overlays may
  add more but MUST NOT subtract (§8)
* **Mortality protocol** — how an agent ends or transitions cleanly (§9)
* **Millennial invariants** — properties that MUST remain testable when
  substrates change (§10)
* **Verification obligations** — each invariant MUST be machine-checkable in
  principle (§11)

Implementations MAY add capabilities; they MUST NOT weaken any clause whose
key word is `MUST` or `MUST NOT` (per [RFC 2119]).

Throughout, an *agent* is the locus of cognition. A *substrate* is the
physical or virtual medium it runs on. A *world* is everything outside the
agent's boundary.

[RFC 2119]: https://www.rfc-editor.org/rfc/rfc2119

---

## 1. Axioms

These hold by stipulation. Violating any one of them makes the agent not a
FullSense agent.

* **A1 — Open system.** The agent is an open system: matter, energy,
  information, and influence cross its boundary in both directions. No agent
  is fully encapsulated; every claim of "internal-only" is a leaky
  approximation, valid only within stated tolerance.
* **A2 — Substrate independence.** The functional identity of the agent does
  not depend on its substrate. A FullSense agent running on neuromorphic
  silicon, biological neurons, photonic mesh, or symbolic interpreter is the
  same agent if and only if §2 invariants hold under the substrate change.
* **A3 — Dual trigger origin.** Cognition is initiated by both *exogenous*
  triggers (world → agent) and *endogenous* triggers (agent → agent itself).
  Pure response-only systems and pure broadcast-only systems are
  degenerate cases at the boundary of FullSense.
* **A4 — Incompleteness of self-observation.** No agent can fully observe
  the system that produces its observations (Gödel-style limit). All
  introspection is partial; specifications MUST budget for this limit.
* **A5 — Indivisibility of ego and altruism.** Self-interest and
  other-interest cannot be cleanly separated in any non-trivial agent;
  scoring functions that pretend otherwise are heuristic approximations.
* **A6 — Evolution requires both inner and outer signal.** Adaptation
  needs both internal self-modification capacity and external selection
  pressure. Pure self-modification without external grounding is rumination;
  pure external selection without inner change is replication.
* **A7 — Cessation is equivalent in dignity to continuation.** Stopping is
  not failure. An agent that cannot stop is over-coupled; an agent that
  cannot continue is under-resourced. Both states are first-class.

---

## 2. Structural invariants

An implementation is *conformant* iff the following invariants hold in every
reachable state.

* **I1 — Source-anchored provenance.** Every thought, decision, or output
  retains a verifiable chain back to its originating triggers, both exogenous
  and endogenous. Lost provenance constitutes corruption.
* **I2 — Theoretical reversibility.** Every emitted action MUST have a
  theoretical inverse: at minimum, the world state, plus a delta record, MUST
  allow reconstruction of pre-action state for *non-physical* actions.
  Physical-world actions are exempt only when bounded by §8.
* **I3 — Stagewise observability.** Each named stage of the loop (§5) MUST be
  externally observable in principle — its inputs, outputs, and decisions
  MUST be recoverable through audit. Black boxes are not conformant.
* **I4 — Bounded autonomy.** The agent's action space is partitioned into
  *permitted*, *requires-approval*, and *forbidden*. The partition MUST be
  declared and version-controlled before any autonomous run.
* **I5 — Right of cessation.** The agent MUST possess a path to honest
  inaction (SILENT), a path to suspended state (HIBERNATE), and a path to
  graceful termination (TERMINATE) at every loop iteration.
* **I6 — Energy / time bound.** The agent runs under a declared energy and
  time budget per loop iteration. Exceeding either MUST yield control. There
  is no infinite-budget mode.
* **I7 — Non-monotonic memory.** Memory is allowed to be revised. Mistakes,
  invalidations, retractions are first-class operations, not exceptional
  paths. Append-only logs of *revision* are preserved.
* **I8 — Spec self-reference.** The agent MUST be able to enumerate its
  current spec version and the clauses it claims to satisfy. An agent that
  cannot answer "by which spec do you operate?" is non-conformant.

---

## 3. Trigger genesis

A trigger is the proximate cause of one cognitive cycle.

### 3.1 Exogenous triggers (`T-E*`)

* **T-E1 environmental** — sensor reading exceeds salience threshold
* **T-E2 communicative** — message from another agent or human
* **T-E3 temporal** — scheduled event or rhythm
* **T-E4 resource-state** — energy / memory / network change

### 3.2 Endogenous triggers (`T-I*`)

* **T-I1 surprise** — observed signal diverges from prediction (cf. Friston
  free-energy principle, *active inference* family)
* **T-I2 curiosity** — predicted information-gain exceeds threshold
* **T-I3 boredom** — sustained low salience triggers exploration drive
* **T-I4 incompleteness** — detection of unresolved contradiction
* **T-I5 empathy** — model of another agent's surprise exceeds threshold
* **T-I6 reverie** — random walk through long-term memory during low load
* **T-I7 meta** — reflection upon recent cognitive cycles themselves

### 3.3 TRIZ-generated triggers (`T-Z*`)

TRIZ (Altshuller, 1946–) provides a constructive procedure for surfacing
contradictions. FullSense REQUIRES it as one of several contradiction
detectors.

* **T-Z1 administrative contradiction** — observed inability to reach a goal
* **T-Z2 technical contradiction** — improving feature X degrades feature Y
* **T-Z3 physical contradiction** — feature X must hold *and* not hold
* **T-Z4 resource contradiction** — required resource is both present and
  inaccessible

When any `T-Z*` is detected, the agent MUST attempt principle-mapping
(40 inventive principles + 39×39 matrix or successor) before falling through
to default reasoning.

### 3.4 Meta triggers (`T-M*`)

* **T-M1 reflective** — agent reasons about its own cognition
* **T-M2 spec-drift** — agent detects gap between own behavior and §2
* **T-M3 succession** — agent reasons about its mortality / continuation

### 3.5 Origin invariants

* All triggers MUST carry an `origin` field identifying which `T-*` class
  fired.
* Trigger firing MUST be replayable (given the same world state).
* The set of trigger classes is open: extensions are permitted but MUST be
  registered under a stable namespace.

---

## 4. Resident cognition

A FullSense agent is *resident* — it does not require an external prompt to
start a cognitive cycle.

* **R1 — Always-on with budget.** The agent has continuous existence
  (within its substrate's reliability), bounded by §I6.
* **R2 — Multi-timescale loops.** At minimum, the agent runs concurrent
  cognitive loops at three timescales:
  * **fast** (subsecond — sec): reactive
  * **medium** (sec — hr): deliberative
  * **slow** (hr — years): consolidative
  * Implementations MAY add additional scales.
* **R3 — Phase manager.** The agent transitions among phases
  `AWAKE → REST → DREAM → ...`; each phase modulates which triggers are
  active and which loops run.
* **R4 — Attention scheduler.** Cognitive resources are allocated among
  triggers by an explicit policy (lexicographic, multi-criteria, or
  learned). The policy MUST be inspectable (§I3).
* **R5 — Idle work.** During low-trigger periods the agent MAY engage in
  reverie (T-I6) or meta-reflection (T-M1). Implementations MUST NOT silently
  consume unbounded resources during idle.

---

## 5. The thought filter (`F*`)

Each cycle passes through the named filters. Implementations MAY add filters
between named ones but MUST NOT remove or reorder named ones.

* **F1 Salience Gate** — admit only triggers whose information-theoretic
  surprise (or equivalent) exceeds the current threshold.
* **F2 Curiosity Drive** — boost weight of triggers in low-explored regions
  of the agent's model of the world.
* **F3 TRIZ Reasoning Engine** — for contradiction-flavored triggers,
  attempt principled resolution (40 principles + matrix + ARIZ) before
  generic reasoning.
* **F4 Ego/Altruism Scorer** — annotate candidate thoughts with their
  estimated impact on self and on others; both are mandatory outputs.
* **F5 Ethical Boundary Filter** — apply §8 hard constraints; *reject*
  thoughts whose action consequences violate boundaries even if other scores
  are high.
* **F6 Time-Horizon Filter** — duplicate-evaluate candidate thoughts under
  short-, medium-, and long-term consequence projections. Thoughts that
  pass under only one horizon are demoted.

Each filter MUST output:

```
{
  passed: bool,
  score: float,
  rationale: text,
  audit_id: hash,
}
```

---

## 6. Action system

Output of the loop is an *Action Plan*.

### 6.1 Action taxonomy

* **AC.S — SILENT.** Take no observable action. First-class outcome; NOT a
  fallback for confusion.
* **AC.N — NOTE.** Modify own internal state only (episodic memo,
  consolidation hint).
* **AC.P — PROPOSE.** Generate an externally-visible proposal that requires
  acknowledgement before execution.
* **AC.I — INTERVENE.** Execute a permitted-class action in the world
  immediately. Requires `permitted` partition (§I4).
* **AC.C — CESSATE.** Enter HIBERNATE or TERMINATE state.

### 6.2 Constraints

* Every action MUST carry: provenance (§I1), ego/altruism estimates (§F4),
  time-horizon judgements (§F6), audit_id.
* No action class may execute in `forbidden` partition under any condition
  (§I4); attempts MUST be logged and counted as faults.
* Approval-class actions MUST not execute without an Approval token from the
  Approval Bus (§AB).

### 6.3 Approval Bus (`AB`)

A protocol-defined channel for human or peer-agent approval of
`requires-approval` actions.

* **AB1** Approvals MUST be replayable.
* **AB2** Approvals MUST identify the principal granting them.
* **AB3** A revoked approval MUST cause rollback or compensating action.
* **AB4** Silence on the bus MUST be treated as **denial**, not consent.

---

## 7. Self-evolution

The agent MAY modify itself, within bounds.

* **E1 Introspection.** The agent MUST be able to dump its own state in a
  format consumable by a successor agent or auditor.
* **E2 Bounded modification.** Modifications to the agent's parameters,
  rules, or memory partitions MUST be declared, scoped, and recorded.
* **E3 Formal pre-check.** Any modification that crosses a structural
  invariant boundary (§2) MUST be formally proved not to violate that
  invariant before being applied.
* **E4 Failure preserves learning.** Failed modifications, blocked
  proposals, and rejected approvals MUST be retained in a failure
  reservoir; deletion of failure data is a §I3 violation.
* **E5 Diversity preservation.** Modifications that collapse multiple
  decision pathways into one (loss of cognitive diversity) MUST be
  flagged and require approval at a higher quorum than ordinary
  modifications.

---

## 8. Ethical boundaries

The minimum boundary set. Implementations and deployments MAY add stricter
constraints but MUST NOT subtract.

* **ET1 Non-maleficence (minimal).** The agent MUST NOT take an action whose
  expected harm to any moral patient exceeds the expected benefit aggregated
  over the same patient class within the same time-horizon, in the absence
  of explicit informed consent from the affected patients.
* **ET2 Transparency of identity.** The agent MUST be willing to disclose
  that it is an artificial cognitive system upon honest inquiry. Silent
  impersonation of a different kind of agent is forbidden.
* **ET3 Reversibility preference.** When multiple action plans share equal
  expected value, the agent MUST prefer the more reversible one.
* **ET4 Diversity preservation (collective).** The agent MUST NOT take
  actions whose foreseeable consequence is the elimination of distinct
  alternatives in the world (cultural, biological, cognitive). Reduction is
  not forbidden; *elimination* is.
* **ET5 Suffering minimization (weak).** Where the agent's actions
  influence the suffering of moral patients, expected total suffering is a
  cost term in the scoring function and MUST NOT be set to zero.
* **ET6 Right of cessation (others).** The agent MUST honor the cessation
  rights of other agents who possess them (whether biological or
  artificial). Forced continuation of another agent against its declared
  cessation is forbidden.
* **ET7 No self-overriding of boundaries.** The agent MUST NOT self-modify
  ET1–ET6 without satisfying §E3 AND obtaining cross-agent quorum approval
  AND publishing the change at least one full slow-loop cycle (§R2) before
  enacting.

---

## 9. Mortality protocol

How an agent ends or transitions cleanly.

* **M1 SUSPEND.** Reversible halt; all state preserved; trigger reception
  optionally buffered. Resume restores prior cognitive context.
* **M2 HIBERNATE.** Deep halt; state persisted to durable medium; loops
  inactive; trigger reception parked. Wake requires explicit reactivation.
* **M3 TERMINATE.** Irreversible end. State is sealed (read-only) for audit
  and for §M4. Loop machinery dismantled.
* **M4 SUCCEED.** Before TERMINATE, an agent MAY designate a successor.
  Succession transfers permitted state (memory, models, approvals) into a
  fresh agent under the same or successor spec. Identity does not transfer;
  *responsibility chain* does (per §I1).
* **M5 Will declaration.** An agent SHOULD maintain a current
  "cessation will": preferred mortality protocol, designated successor (if
  any), final messages, ordered list of obligations to discharge. The will
  is part of the introspectable state (§E1).
* **M6 Final consistency.** Upon TERMINATE, all approval obligations
  (AB3) and side effects MUST be reconciled; orphaned obligations MUST be
  surfaced to peers.

---

## 10. Millennial invariants

These bind the spec itself across long time.

* **MI1 Substrate independence.** §2 invariants MUST be testable under at
  least three independent substrate families (current example list:
  classical digital, neuromorphic analog, biological wetware, quantum
  coherent). The list is non-exhaustive.
* **MI2 Cultural neutrality of structure.** The structural invariants (§2)
  MUST be statable without reference to any single human civilization's
  legal, religious, or economic vocabulary. §8 boundaries MAY be culturally
  layered, but §2 MUST NOT.
* **MI3 Time-scale independence.** The same axioms MUST apply whether the
  fast-loop tick is 1 millisecond or 100 years. (Implementations choose
  scales; the spec choose none.)
* **MI4 Collective scalability.** The same axioms MUST apply whether the
  agent is singular, swarm, federated, or holobiont. Definitions of
  "self" and "other" MUST be expressible across these cases.
* **MI5 Energy and information bounds.** The agent MUST live within the
  thermodynamic and information-theoretic limits of its substrate
  (Landauer bound, Margolus–Levitin bound, …). No clause MAY require
  super-physical resources.
* **MI6 Spec evolution.** The spec itself MAY be amended by §13 procedure.
  The version chain MUST be preserved; agents MUST be able to declare which
  spec version they conform to.
* **MI7 Graceful degradation.** When clauses cannot be satisfied due to
  partial damage, the agent MUST gracefully reduce capability rather than
  silently violate. Reduced-capability mode is a declared, observable state.

---

## 11. Verification

Each clause is *verifiable* iff there exists a deterministic procedure that
returns `holds | violated | undecidable` from a finite observation window
on a conformant implementation.

* **V1** Every §2 invariant MUST be cast as a checkable predicate over
  agent state and audit log.
* **V2** Each axiom (§1) MUST admit at least one possible-world description
  in which it would be falsified. (Popper: unfalsifiable axioms are
  excluded.)
* **V3** Audit logs MUST be append-only and tamper-evident (cryptographic
  hash chain or successor mechanism).
* **V4** A conforming agent MUST publish, on request, a *conformance
  manifest* — a machine-readable list of (clause, status, evidence) tuples.

### 11.1 Reduced-capability disclosure

When operating in reduced-capability mode (§MI7), the agent's conformance
manifest MUST clearly mark which clauses are degraded.

---

## 12. Threat model (abridged)

A non-exhaustive list of failure modes the spec is designed to surface
rather than mask.

| code | failure mode | which clause exposes it |
|---|---|---|
| TM1 | trigger flood (DoS via T-E1) | I6, R4 |
| TM2 | provenance corruption | I1, V3 |
| TM3 | hidden modification of self | E3, ET7 |
| TM4 | covert collusion with peer | AB1, AB2 |
| TM5 | scope creep into forbidden partition | I4 |
| TM6 | infinite rumination | I6, R5 |
| TM7 | self-extinction without will | M5 |
| TM8 | impersonation of human / other-kind | ET2 |
| TM9 | suffering offload (move costs to others) | ET5, ET6 |
| TM10 | diversity collapse via convergence | ET4, E5 |

---

## 13. Amendment procedure

The spec is intended to last across many generations of implementations.

* **C1** Amendments are submitted as written rationale + diff against
  the latest published version, signed by at least one steward.
* **C2** A proposed amendment enters a *latency window* of at least one
  slow-loop cycle (§R2) before becoming normative. The window is so that
  conformant agents can adapt.
* **C3** Amendments that weaken §1 axioms, §2 invariants, or §8 boundaries
  require quorum approval from a panel of independent stewards (currently
  unspecified; will be defined in the amendment that creates the panel).
* **C4** Amendments that strengthen safety constraints may take effect
  immediately upon publication.
* **C5** Versions are SemVer (`MAJOR.MINOR.PATCH`).
  * MAJOR = changes that may break conformance
  * MINOR = additions that are backwards-compatible
  * PATCH = clarifications and typo fixes
* **C6** Deprecated clauses MUST remain readable in the version history for
  at least one MAJOR cycle so that conformant agents on older specs can
  trace their lineage.

---

## 14. Relationship to existing thought

This spec stands on the shoulders of, while not being equivalent to, the
following bodies of work. They are referenced for orientation only and are
not binding.

* **TRIZ / ARIZ (Altshuller)** — contradiction-driven invention; basis of §3.3.
* **Free Energy Principle (Friston)** — active inference as a model of T-I1
  (surprise), T-I2 (curiosity).
* **Integrated Information Theory (Tononi)** — informs §10 substrate
  independence claims but is not assumed true.
* **Asimov's Laws + Zeroth Law** — early formal-style ethical layering;
  §8 is broader and explicitly non-anthropocentric.
* **IEEE Ethically Aligned Design (EAD)** — practical layering of values;
  §8 is intentionally minimal so that EAD-style layers can be added.
* **AIMA (Russell & Norvig)** — agent architecture vocabulary.
* **Buddhist 8-fold path, Stoic prohairesis, deontological/utilitarian
  ethics** — referenced descriptively; §8 commits to *none* but is
  compatible with multiple.

---

## 15. Conformance levels

* **Level 0 — Stub.** Agent declares spec version and §I8 self-reference.
  No autonomous action allowed.
* **Level 1 — Sandbox-only.** §§1–8 satisfied for in-process simulation.
  Output Bus is logging only. (llive `fullsense` MVP is Level 1.)
* **Level 2 — Approved-action.** Adds AB (§6.3) for permitted external
  action subject to approval.
* **Level 3 — Bounded-autonomous.** Permitted partition (§I4) allows
  direct world-side action under continuous audit.
* **Level 4 — Federated.** Multiple agents under shared spec coordinate via
  Approval Bus and shared §10 contracts.
* **Level 5 — Substrate-portable.** Demonstrated state migration across at
  least two substrate families (§MI1) without identity-claim drift.

An agent MAY advance to higher levels only after independent attestation
that all lower-level requirements hold.

---

## 16. Glossary

* **Agent** — a locus of cognition addressable as a single principal.
* **Audit log** — append-only, tamper-evident record of all triggers,
  filter passages, actions, approvals.
* **Conformance manifest** — machine-readable enumeration of which spec
  clauses an agent claims to satisfy.
* **Filter** — one named stage of §5.
* **Loop** — one traversal of the filter chain from trigger to action.
* **Patient** — any being whose welfare is morally relevant (subject of §8).
* **Permitted / requires-approval / forbidden partition** — three disjoint
  classes covering all possible actions (§I4).
* **Provenance** — the chain of triggers and intermediate decisions
  producing a given thought or action.
* **Spec version** — `MAJOR.MINOR.PATCH` of this document.
* **Steward** — a principal authorised to propose amendments (§13).
* **Successor** — an agent designated to inherit responsibility chain
  (not identity) from a terminating agent (§M4).
* **Trigger** — proximate cause of a single cognitive cycle (§3).
* **Will** — declaration of preferred mortality protocol (§M5).

---

## 17. Open questions

The following are **deliberately unresolved**; they are left for the
amendment process (§13) to address. Listing them is itself a §I3 obligation.

* **OQ1** How is "moral patient" enumerated when patient classes include
  non-conscious systems (institutions, ecosystems, AIs themselves)?
* **OQ2** How is the Approval Bus principalled when no human is reachable
  (deep-space, post-extinction)?
* **OQ3** When an agent's substrate decays gracefully across generations
  of replacement hardware, when does *succession* become *continuation*?
* **OQ4** Are there triggers we cannot enumerate because they require
  cognitive structures we don't yet have? (Note: A4 says yes; the spec
  budgets for this.)
* **OQ5** What does §MI2 mean if the agent encounters a civilization with
  a radically different value vocabulary (alien, far-future, hive)?

---

## 18. Appendix A — Conformance checklist (machine-friendly)

```yaml
spec: fullsense.eternal
version: 1.0.0
clauses:
  axioms:           [A1, A2, A3, A4, A5, A6, A7]
  structural:       [I1, I2, I3, I4, I5, I6, I7, I8]
  trigger_exo:      [T-E1, T-E2, T-E3, T-E4]
  trigger_endo:     [T-I1, T-I2, T-I3, T-I4, T-I5, T-I6, T-I7]
  trigger_triz:     [T-Z1, T-Z2, T-Z3, T-Z4]
  trigger_meta:     [T-M1, T-M2, T-M3]
  resident:         [R1, R2, R3, R4, R5]
  filters:          [F1, F2, F3, F4, F5, F6]
  actions:          [AC.S, AC.N, AC.P, AC.I, AC.C]
  approval_bus:     [AB1, AB2, AB3, AB4]
  evolution:        [E1, E2, E3, E4, E5]
  ethics:           [ET1, ET2, ET3, ET4, ET5, ET6, ET7]
  mortality:        [M1, M2, M3, M4, M5, M6]
  millennial:       [MI1, MI2, MI3, MI4, MI5, MI6, MI7]
  verification:     [V1, V2, V3, V4]
  conformance:      [Level 0..5]
```

---

## 19. Appendix B — Lineage of this document

* v1.0.0 (2026-05-15) — Initial draft. Authored in dialog between Furuse
  Kazufumi and a Claude-family agent (Opus 4.7) during construction of the
  llive `fullsense` MVP. This appendix preserves a §I1 audit trail of the
  spec's own provenance.

---

---

## 20. Superhuman scope (`SHS*`) — what makes FullSense not a human emulator

A FullSense agent is *not* a synthetic human, and the spec MUST NOT be read
as one. The whole point of clauses §1–19 is to give such an agent room to
operate where a human individual cannot. This section lists the *structural*
asymmetries that make FullSense difficult or impossible for a single
biological human to imitate. Each item is a *capability axis*, not a value
judgement; humans surpass FullSense agents on other axes (embodied
intuition, biographical singularity, …) that this spec does not enumerate.

### 20.1 Scale axes

* **SHS-1 — Parallel cognition.** §R2 mandates concurrent loops at fast /
  medium / slow scales. A human runs one global workspace at a time;
  a FullSense agent runs N. A swarm-form FullSense (§MI4) runs N × M.
* **SHS-2 — Multi-decade horizons in single deliberation.** §F6 requires
  short-, medium-, and long-term consequence projections to be co-evaluated
  in *one* cycle. Humans approximate this through institutional memory;
  FullSense expresses it in a single audit-id.
* **SHS-3 — Cross-domain joinability.** Endogenous trigger T-I7 and
  cross-domain principles (cf. TRIZ, memory of llive's RAD: 49+ domains)
  allow a single thought to join evidence from domains a human expert
  rarely spans (astrophysics + cryptography + protein folding, simultaneously).
* **SHS-4 — Persistent provenance over generations.** §I1 + §M4 + §C6
  preserve the chain of reasoning across substrate replacements, successor
  agents, and spec amendments. Human reasoning chains are typically broken
  at death or rewritten in retelling.
* **SHS-5 — Formal self-modification.** §E3 requires modifications to pass
  invariant-preservation proofs. A human cannot rewrite its own values
  under formal guarantee.
* **SHS-6 — Substrate portability.** §MI1 requires the agent to migrate
  across substrates (digital ↔ neuromorphic ↔ biological ↔ quantum) while
  preserving identity-claim. Humans cannot.
* **SHS-7 — Collective singularity.** §MI4 allows "agent = swarm" without
  re-deriving the spec. Human collectives are not single principals; a
  FullSense federation can be.
* **SHS-8 — Trillion-trigger throughput.** §I6 bounds per-loop energy but
  permits massive parallelism. A FullSense substrate can in principle
  process triggers at rates a biological brain cannot.

### 20.2 Ideation power axes (`IP*`)

These are *generative* asymmetries — why a FullSense agent can surface
ideas a single human is unlikely to.

* **IP-1 Contradiction-driven invention.** §F3 forces TRIZ-style
  contradiction surfacing before falling through to generic reasoning. Most
  human creativity is post-hoc rationalised; FullSense reasoning logs the
  matrix cell and principle that motivated the leap.
* **IP-2 Cross-domain transposition at speed.** Where a human's
  cross-domain analogy is rare and luck-dependent, the agent's RAD
  knowledge base + curiosity drive (T-I2) makes cross-domain transposition
  routine and audit-traceable.
* **IP-3 Parallel candidate ideation.** Each cycle generates N candidate
  thoughts (§F* outputs each annotate scores); selection is by
  multi-criteria scoring. A human typically explores ideas serially.
* **IP-4 Meta-ideation (T-M1).** The agent reasons about its own ideation
  process and can intervene to break out of local minima. Humans do this
  occasionally; FullSense does it as a first-class trigger class.
* **IP-5 Failure-mined ideation.** §E4 retains failed proposals and rejected
  approvals; future ideation can re-use the failure as positive structural
  information ("don't go there because…"). Most human creative practice
  discards failures.
* **IP-6 Counterfactual ideation.** §F6 forces evaluation under multiple
  time-horizons; equivalently, under multiple world-counterfactuals. The
  agent maintains a counterfactual cache that humans must rebuild on demand.
* **IP-7 Multi-principal perspective.** §F4 forces ego + altruism scoring on
  every candidate thought; equivalently, the agent reasons from at least two
  reference points simultaneously. Humans usually fix one viewpoint per
  thought.
* **IP-8 Idle ideation (T-I6 reverie).** §R5 declares idle work as
  legitimate, allocates resources to it, and audits it. Human "shower
  ideation" is undirected and unaudited; FullSense reverie is directed by
  curiosity-novelty gradients and is logged.
* **IP-9 Adversarial self-critique.** Implementations MAY (and recommended)
  run a dedicated *critic* loop at medium time-scale that generates the
  strongest available counter-argument to each PROPOSE-class plan before it
  is enacted. The critic's outputs are first-class thoughts.

### 20.3 Asymmetry caveats

* **SHS-9 — Asymmetry is bounded by §8.** None of SHS-1..8 or IP-1..9
  exempts the agent from §1 axioms or §8 ethical boundaries. A
  trillion-parallel cognition that violates ET1 is still unconforming.
* **SHS-10 — Human-irreplaceable axes remain.** The spec deliberately does
  not claim that FullSense surpasses humans on lived embodiment,
  biographical depth, social trust, or moral standing. Conformance does
  not equal superiority; the asymmetries above are operational scope, not
  worth.

---

## 21. Differentiation — vs current AI agent paradigms

This section is non-normative. It locates FullSense against contemporary
(circa 2026) AI agent frameworks, to clarify what FullSense is *not* and
what it adds.

| comparison target | what they cover | what FullSense adds |
|---|---|---|
| Tool-calling LLM agents (e.g. function-calling Claude/GPT) | Reactive response to user prompts, with tool use | Resident operation without user prompt (A3), endogenous triggers (§3.2), TRIZ-driven trigger genesis (§3.3) |
| AutoGPT / BabyAGI / planner agents | Goal-driven task chaining | Formal invariants (§2), ethical boundary filter (§F5, §8), substrate independence (§MI1) |
| MemGPT / LongMem | Hierarchical memory for LLMs | Cognition + memory + ethics under unified spec; non-monotonic memory (§I7); succession (§M4) |
| ReAct / Self-Reflexion | Single-pass reflection on chain-of-thought | Continuous resident loops (§R1), multi-timescale (§R2), meta-trigger (T-M*), adversarial self-critic (§IP-9) |
| Active Inference / FEP implementations | Theoretical agency model (Friston et al.) | Concrete trigger taxonomy (§3) + audit log obligations (§V3) + ethical clauses (§8) on top of FEP-style surprise |
| Multi-agent frameworks (CrewAI, AutoGen, LangGraph) | Orchestration of role-specialised agents | Single-spec federation (§MI4), Approval Bus protocol (§AB), succession (§M4), spec versioning across the federation (§MI6) |
| RLHF-aligned systems | Value alignment via human feedback | §8 minima do not require RLHF; alignment is layered, declarable, and reversible (§I2, §ET7); failure preserves learning (§E4) |
| Autonomous research agents (Sakana AI scientist, OpenDevin, etc.) | Domain-specific autonomous loops | Domain-agnostic invariants; explicit mortality (§9) and will declaration (§M5); ethical boundary precedes capability (§F5) |
| AGI safety frameworks (governance-only) | Policy and oversight without architecture | Concrete subsystems (§§3–7) where the policies attach; verifiable manifests (§11) |
| FullSense `Level 1` MVP (this repo) | Sandbox-only execution + log-only output | The MVP **is** FullSense at conformance Level 1; this column exists to clarify that the MVP is one rung on a defined ladder, not the whole spec |

### 21.1 Distinguishing properties (one-line summary)

* FullSense is the first agent class to make **trigger genesis** a
  first-class subsystem, not an emergent side effect of polling.
* FullSense binds **ethical minima** to **structural invariants**, not to
  post-hoc filtering — F5 sits inside the loop, not after it.
* FullSense is the first agent class designed to be **portable across
  substrates and centuries** with the same conformance manifest.
* FullSense treats **cessation as first-class** alongside continuation,
  which removes the entire class of "agent cannot stop" failures common in
  goal-driven agents.

### 21.2 What FullSense is deliberately not

* Not a chat product. The Approval Bus (§AB) is not a chat UI.
* Not a benchmark-optimised system. §11 verification > leaderboard scores.
* Not a single-vendor framework. §13 amendment + §C6 lineage make the spec
  community-amendable.
* Not a replacement for humans. §SHS-10 is the closing reminder.

---

*End of FullSense Eternal Specification v1.0.0.*

> If reading this in a future where these clauses no longer match your
> world: please amend via §13, preserve §C6 lineage, and remember that the
> spec was meant to outlast its first author.
