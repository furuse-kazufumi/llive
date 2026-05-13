"""Built-in sub-blocks for Phase 1 (BC-02 minimum 5).

| Sub-block          | Role                                                       |
|--------------------|------------------------------------------------------------|
| `pre_norm`         | metadata marker — HF model 内蔵の RMSNorm を象徴 (no-op) |
| `causal_attention` | metadata marker — HF model 内蔵 attention を象徴 (no-op) |
| `memory_read`      | semantic + episodic memory を query → context 追加        |
| `ffn_swiglu`       | metadata marker — HF model 内蔵 FFN を象徴 (no-op)        |
| `memory_write`     | surprise gate を通って memory に書込                       |

「marker」型 sub-block は trace を残すだけで state を素通しする。実際の数値計算は
HFAdapter が担当する (Phase 1 の現実的な分割)。`memory_read` / `memory_write` のみ
副作用を持つ。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from llive.container.registry import SubBlockRegistry
from llive.memory.encoder import MemoryEncoder
from llive.memory.episodic import EpisodicEvent, EpisodicMemory
from llive.memory.provenance import Provenance
from llive.memory.semantic import SemanticMemory
from llive.memory.surprise import SurpriseGate


@dataclass
class _MarkerBlock:
    name: str
    type: str

    def __call__(self, state):
        # marker sub-blocks are no-op pass-throughs for Phase 1
        return state


def _make_marker(type_name: str):
    def factory(_config: dict[str, Any]):
        return _MarkerBlock(name=type_name, type=type_name)

    return factory


# ---------------------------------------------------------------------------
# Shared memory wiring
# ---------------------------------------------------------------------------


@dataclass
class MemoryBackends:
    """Process-shared memory backends (semantic + episodic + encoder + gate)."""

    encoder: MemoryEncoder = field(default_factory=lambda: MemoryEncoder(prefer_fallback=False))
    semantic: SemanticMemory | None = None
    episodic: EpisodicMemory | None = None
    surprise: SurpriseGate = field(default_factory=lambda: SurpriseGate(theta=0.3))

    def ensure_semantic(self) -> SemanticMemory:
        if self.semantic is None:
            self.semantic = SemanticMemory(dim=self.encoder.dim)
        return self.semantic

    def ensure_episodic(self) -> EpisodicMemory:
        if self.episodic is None:
            self.episodic = EpisodicMemory()
        return self.episodic


_BACKENDS: MemoryBackends | None = None


def get_memory_backends() -> MemoryBackends:
    global _BACKENDS
    if _BACKENDS is None:
        _BACKENDS = MemoryBackends()
    return _BACKENDS


def set_memory_backends(backends: MemoryBackends | None) -> None:
    """Override the process-shared backends (tests / orchestration)."""
    global _BACKENDS
    _BACKENDS = backends


# ---------------------------------------------------------------------------
# Active sub-blocks
# ---------------------------------------------------------------------------


@dataclass
class MemoryReadBlock:
    name: str = "memory_read"
    type: str = "memory_read"
    sources: tuple[str, ...] = ("semantic", "episodic")
    top_k: int = 4

    @classmethod
    def factory(cls, config: dict[str, Any]):
        srcs = config.get("source") or config.get("sources") or ["semantic", "episodic"]
        return cls(sources=tuple(srcs), top_k=int(config.get("top_k", 4)))

    def __call__(self, state):
        backends = get_memory_backends()
        retrieved: list[str] = []
        if "semantic" in self.sources:
            sem = backends.ensure_semantic()
            if len(sem) > 0:
                q_emb = backends.encoder.encode(state.prompt)
                hits = sem.query(q_emb, top_k=self.top_k)
                state.memory_accesses.append(
                    {
                        "op": "read",
                        "layer": "semantic",
                        "hits": [{"id": h.entry_id, "score": float(h.score)} for h in hits],
                    }
                )
                retrieved.extend(h.content for h in hits)
        if "episodic" in self.sources:
            ep = backends.ensure_episodic()
            recent = ep.query_recent(limit=self.top_k)
            state.memory_accesses.append(
                {
                    "op": "read",
                    "layer": "episodic",
                    "hits": [{"id": r.event_id, "ts": r.ts.isoformat()} for r in recent],
                }
            )
            retrieved.extend(r.content for r in recent)
        if retrieved:
            state.retrieved_context.extend(retrieved)
        return state


@dataclass
class MemoryWriteBlock:
    name: str = "memory_write"
    type: str = "memory_write"
    policy: str = "surprise_gated"
    target: str = "semantic"  # "semantic" | "episodic" | "both"
    source_type: str = "llm_generation"

    @classmethod
    def factory(cls, config: dict[str, Any]):
        return cls(
            policy=str(config.get("policy", "surprise_gated")),
            target=str(config.get("target", "semantic")),
            source_type=str(config.get("source_type", "llm_generation")),
        )

    def __call__(self, state):
        content = state.output or state.prompt
        if not content:
            return state
        backends = get_memory_backends()
        embedding = backends.encoder.encode(content)
        sem = backends.ensure_semantic()
        existing = sem.all_embeddings()
        surprise = backends.surprise.compute_surprise(embedding, existing)
        state.surprise = float(surprise)
        gated = self.policy != "surprise_gated" or backends.surprise.should_write(surprise)
        if not gated:
            state.memory_accesses.append(
                {"op": "write_skip", "layer": self.target, "reason": "below_theta", "surprise": surprise}
            )
            return state
        prov = Provenance(
            source_type=self.source_type,
            source_id=state.meta.get("request_id", "anon"),
            confidence=1.0 - max(0.0, 0.5 - surprise),  # rough heuristic
        )
        if self.target in ("semantic", "both"):
            eid = sem.write(content, embedding, prov)
            state.memory_accesses.append(
                {"op": "write", "layer": "semantic", "entry_id": eid, "surprise": surprise}
            )
        if self.target in ("episodic", "both"):
            ep = backends.ensure_episodic()
            eid = ep.write(
                EpisodicEvent(content=content, provenance=prov, metadata={"surprise": surprise})
            )
            state.memory_accesses.append(
                {"op": "write", "layer": "episodic", "event_id": eid, "surprise": surprise}
            )
        return state


# ---------------------------------------------------------------------------
# Registration entry-point
# ---------------------------------------------------------------------------


def register_builtins(registry: SubBlockRegistry) -> None:
    """Register Phase 1 built-in sub-blocks. Idempotent only on a fresh registry."""
    for marker in ("pre_norm", "causal_attention", "ffn_swiglu", "residual"):
        if not registry.has(marker):
            registry.register(marker, _make_marker(marker))
    if not registry.has("memory_read"):
        registry.register("memory_read", MemoryReadBlock.factory)
    if not registry.has("memory_write"):
        registry.register("memory_write", MemoryWriteBlock.factory)
