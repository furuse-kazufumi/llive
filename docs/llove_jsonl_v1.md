# llive ↔ llove JSONL Specification (v1)

**Phase 2 OBS-03 deliverable.** llive writes; llove tails / reads.

This spec freezes the on-disk file paths and JSON schemas that the llove
TUI viewers (`RouteTraceViewer`, `MemoryLinkVizPanel`, `BWTDashboard`)
consume. llive will not change these without bumping `version` and
keeping a deprecation window.

> **No realtime IPC in Phase 2** — llove polls / tails JSONL files. Phase
> 4 may add UNIX socket / named pipe push, gated behind a feature flag.

---

## File locations

All paths are relative to `$LLIVE_DATA_DIR` (default `D:/data/llive`).

| File | Producer | Consumer | Notes |
|---|---|---|---|
| `logs/llove/route_trace.jsonl` | `llive.observability.trace.write_trace` | llove `RouteTraceViewer` | Mirror of Phase 1 trace JSONL with `version=1` framing |
| `logs/llove/memory_link.jsonl` | `llive.memory.concept.ConceptPageRepo` on upsert | llove `MemoryLinkVizPanel` | One row per ConceptPage update |
| `logs/llove/bwt.jsonl` | `llive.evolution.bwt.BWTMeter.dump_jsonl` | llove `BWTDashboard` | One row per bench run |
| `logs/llove/concept_index.jsonl` | `llive.memory.concept.ConceptPageRepo.export_index` | llove `MemoryLinkVizPanel` | Periodic full re-export (compaction) |

JSONL = one JSON object per line. UTF-8. No trailing comma. Lines should
parse independently (no multi-line objects).

---

## `route_trace.jsonl` (RouteTraceViewer)

```json
{
  "version": 1,
  "kind": "route_trace",
  "request_id": "hex",
  "timestamp": "2026-05-13T08:30:01Z",
  "container": "adaptive_reasoning_v1",
  "subblocks": [
    {"name": "pre_norm", "type": "pre_norm", "duration_ms": 0.12, "note": ""},
    {"name": "memory_read", "type": "memory_read", "duration_ms": 1.4, "note": ""},
    {"name": "ffn_swiglu", "type": "ffn_swiglu", "duration_ms": 0.18, "note": ""},
    {"name": "memory_write", "type": "memory_write", "duration_ms": 0.42, "note": ""}
  ],
  "memory_accesses": [
    {"op": "read", "layer": "semantic", "hits": [{"id": "hex", "score": 0.83}]},
    {"op": "write", "layer": "semantic", "entry_id": "hex", "surprise": 0.71}
  ],
  "metrics": {"latency_ms": 2.12, "subblock_count": 4}
}
```

Backwards-compatible note: Phase 1 traces lack the `version` and `kind`
fields. llove must accept both, defaulting `kind` to `route_trace`.

---

## `memory_link.jsonl` (MemoryLinkVizPanel)

```json
{
  "version": 1,
  "kind": "concept_update",
  "timestamp": "2026-05-13T08:31:02Z",
  "concept_id": "memory-consolidation",
  "title": "Memory Consolidation",
  "page_type": "domain_concept",
  "linked_entry_ids": ["hex", "hex"],
  "linked_concept_ids": ["surprise-gate"],
  "surprise_stats": {"n": 6, "mean": 0.42, "m2": 0.05},
  "summary": "<= 1500 chars"
}
```

Emitted by `ConceptPageRepo.upsert` (one row per upsert, append-only).
llove deduplicates by `concept_id` keeping the latest entry.

---

## `bwt.jsonl` (BWTDashboard)

```json
{
  "version": 1,
  "kind": "bwt_summary",
  "timestamp": "2026-05-13T08:32:03Z",
  "task_order": ["t1", "t2", "t3", "t4", "t5"],
  "n_tasks": 5,
  "bwt": -0.008,
  "avg_accuracy": 0.78,
  "per_task_drop": {"t1": -0.01, "t2": -0.006, "t3": -0.008, "t4": -0.009},
  "diagonal": {"t1": 0.81, "t2": 0.79, "t3": 0.83, "t4": 0.80, "t5": 0.82},
  "final": {"t1": 0.80, "t2": 0.78, "t3": 0.82, "t4": 0.79, "t5": 0.82}
}
```

llove plots `bwt` as a sparkline over time and renders `per_task_drop`
as a horizontal bar chart.

---

## `concept_index.jsonl` (compaction snapshot)

Periodically (or via `llive consolidate compact`), llive may emit a full
index snapshot to break the `memory_link.jsonl` append-only stream into
manageable chunks:

```json
{"version": 1, "kind": "snapshot_marker", "timestamp": "...", "ttl_after_seconds": 86400}
{"version": 1, "kind": "concept_record", "concept_id": "...", "title": "...", "page_type": "...", "linked_concept_ids": [...]}
... one per page ...
{"version": 1, "kind": "snapshot_end", "timestamp": "..."}
```

llove can fast-forward past expired snapshot markers.

---

## Versioning

- `version: 1` is the Phase 2 baseline. Required on every row.
- Future versions add new optional fields only; required field removals
  bump the major version.
- llove must tolerate unknown optional fields silently.

---

*Spec frozen: 2026-05-13 (Phase 2 OBS-03 deliverable)*
