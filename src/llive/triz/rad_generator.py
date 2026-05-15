# SPDX-License-Identifier: Apache-2.0
"""RAD-Backed Idea Generator (TRIZ-04 / FR-25).

Given a :class:`Contradiction` and a :class:`PrincipleRecommendation`, produce
a draft :class:`CandidateDiff`-compatible dict whose ``mutation_metadata``
records:

* the contradiction id
* the applied principle id + name
* any RAD corpus evidence consulted (when the raptor corpus dir is mounted)

The generator is **mock-friendly**: it ships with a deterministic
``TemplateIdeaLLM`` that emits a small library of safe ``insert_subblock``
/ ``replace_subblock`` skeletons keyed by principle id. A pluggable
``IdeaLLM`` protocol lets production wire an Anthropic / vLLM client.

RAD lookup is best-effort: the generator searches
``$RAPTOR_CORPUS_DIR/<domain>/INDEX.md`` for principle-related domains
and records ``rad_evidence`` references when files are found. Missing
RAD does not block generation.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from llive.triz.contradiction import Contradiction
from llive.triz.principle_mapper import PrincipleRecommendation


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _default_corpus_dir() -> Path | None:
    env = os.environ.get("RAPTOR_CORPUS_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    fallback = Path("C:/Users/puruy/raptor/.claude/skills/corpus")
    if fallback.is_dir():
        return fallback
    return None


# Principle id -> hint about which RAD corpus directories tend to apply.
_PRINCIPLE_TO_DOMAINS: dict[int, tuple[str, ...]] = {
    1: ("software_engineering", "memory_systems"),
    3: ("memory_systems", "neural_signal"),
    7: ("memory_systems", "software_engineering"),
    10: ("memory_systems",),
    13: ("control_theory", "neural_signal"),
    15: ("software_engineering",),
    19: ("memory_systems", "neural_signal", "bci"),
    25: ("software_engineering",),
    27: ("software_engineering", "control_theory"),
    35: ("memory_systems", "neural_signal", "neuromorphic"),
    37: ("control_theory", "industrial_iot"),
    39: ("industrial_iot", "control_theory"),
    40: ("memory_systems", "neural_signal"),
}


# Principle id -> default change-op skeleton hint (Phase 3 MVR template library).
_PRINCIPLE_TEMPLATES: dict[int, dict[str, Any]] = {
    1: {  # Segmentation -> split a heavy block
        "action": "replace_subblock",
        "from": "ffn_swiglu",
        "to": {"type": "ffn_swiglu", "name": "ffn_segmented_v1"},
    },
    13: {  # The Other Way Around
        "action": "reorder_subblocks",
        "rationale": "swap memory_read / memory_write order",
    },
    15: {  # Dynamic parts
        "action": "insert_subblock",
        "after": "memory_read",
        "spec": {"type": "memory_write", "name": "memory_write_dynamic"},
    },
    19: {  # Periodic action
        "action": "insert_subblock",
        "after": "ffn_swiglu",
        "spec": {"type": "memory_write", "name": "memory_write_periodic"},
    },
    35: {  # Parameter changes
        "action": "replace_subblock",
        "from": "causal_attention",
        "to": {"type": "grouped_query_attention", "name": "attention_gqa_v1"},
    },
    40: {  # Composite materials
        "action": "insert_subblock",
        "after": "pre_norm",
        "spec": {"type": "adapter", "name": "adapter_composite_v1"},
    },
}


@dataclass(frozen=True)
class RadEvidence:
    domain: str
    cluster: str
    relevance: float
    source_path: str | None = None


@dataclass
class GeneratedCandidate:
    candidate_id: str
    container_id: str
    contradiction_id: str
    principle_id: int
    principle_name: str
    diff: dict[str, Any]
    rad_evidence: list[RadEvidence] = field(default_factory=list)
    generated_at: datetime = field(default_factory=_utcnow)


class IdeaLLM(Protocol):
    """Pluggable provider for diff generation. Production wires Anthropic/vLLM."""

    def generate(
        self,
        contradiction: Contradiction,
        recommendation: PrincipleRecommendation,
        container_id: str,
    ) -> dict[str, Any]: ...


@dataclass
class TemplateIdeaLLM:
    """Deterministic, no-network fallback used in tests and offline runs."""

    fallback_principle_id: int = 1

    def generate(
        self,
        contradiction: Contradiction,
        recommendation: PrincipleRecommendation,
        container_id: str,
    ) -> dict[str, Any]:
        template = _PRINCIPLE_TEMPLATES.get(
            recommendation.principle.id, _PRINCIPLE_TEMPLATES[self.fallback_principle_id]
        )
        # copy + bind container id
        change = {k: v for k, v in template.items() if k not in ("rationale",)}
        change["target_container"] = container_id
        return {
            "candidate_id": f"cand_{uuid.uuid4().hex[:12]}",
            "container_id": container_id,
            "changes": [change],
        }


class RadCorpusLookup:
    """Best-effort lookup of RAD INDEX.md entries by principle-suggested domains."""

    def __init__(self, base_dir: Path | str | None = None, *, max_hits: int = 3) -> None:
        if base_dir is None:
            base_dir = _default_corpus_dir()
        self.base_dir = Path(base_dir) if base_dir else None
        self.max_hits = int(max_hits)

    def lookup(self, principle_id: int) -> list[RadEvidence]:
        if self.base_dir is None or not self.base_dir.is_dir():
            return []
        domains = _PRINCIPLE_TO_DOMAINS.get(principle_id, ())
        out: list[RadEvidence] = []
        for d in domains:
            cluster_dir = self.base_dir / d
            if not cluster_dir.is_dir():
                continue
            index = cluster_dir / "INDEX.md"
            if not index.is_file():
                continue
            relevance = _crude_relevance(index, principle_id)
            out.append(
                RadEvidence(
                    domain=d,
                    cluster="root",
                    relevance=relevance,
                    source_path=str(index),
                )
            )
            if len(out) >= self.max_hits:
                break
        return out


def _crude_relevance(path: Path, principle_id: int) -> float:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:  # pragma: no cover - filesystem race
        return 0.5
    needle = f"principle {principle_id}"
    base = 0.6
    if needle.lower() in text.lower():
        base += 0.2
    if "consolidation" in text.lower() or "replay" in text.lower():
        base += 0.1
    return float(min(1.0, base))


class RadBackedIdeaGenerator:
    """Combines :class:`IdeaLLM` and :class:`RadCorpusLookup` into one entry point."""

    def __init__(
        self,
        llm: IdeaLLM | None = None,
        corpus: RadCorpusLookup | None = None,
    ) -> None:
        self.llm = llm or TemplateIdeaLLM()
        self.corpus = corpus or RadCorpusLookup()

    def generate(
        self,
        contradiction: Contradiction,
        recommendation: PrincipleRecommendation,
        *,
        container_id: str,
    ) -> GeneratedCandidate:
        diff = self.llm.generate(contradiction, recommendation, container_id)
        evidence = self.corpus.lookup(recommendation.principle.id)
        return GeneratedCandidate(
            candidate_id=diff.get("candidate_id") or f"cand_{uuid.uuid4().hex[:12]}",
            container_id=container_id,
            contradiction_id=contradiction.contradiction_id,
            principle_id=recommendation.principle.id,
            principle_name=recommendation.principle.name,
            diff=diff,
            rad_evidence=evidence,
        )


def candidate_to_json(c: GeneratedCandidate) -> str:
    payload = {
        "candidate_id": c.candidate_id,
        "container_id": c.container_id,
        "mutation_metadata": {
            "policy": "triz_inspired",
            "contradiction_id": c.contradiction_id,
            "applied_principle": {"id": c.principle_id, "name": c.principle_name},
            "rad_evidence": [
                {
                    "domain": e.domain,
                    "cluster": e.cluster,
                    "relevance": e.relevance,
                    "source_path": e.source_path,
                }
                for e in c.rad_evidence
            ],
        },
        "diff": c.diff,
        "generated_at": c.generated_at.isoformat(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


__all__ = [
    "GeneratedCandidate",
    "IdeaLLM",
    "RadBackedIdeaGenerator",
    "RadCorpusLookup",
    "RadEvidence",
    "TemplateIdeaLLM",
    "candidate_to_json",
]
