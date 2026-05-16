# SPDX-License-Identifier: Apache-2.0
"""SILRunner — cache the 5 Interrogators through TLBCoordinator (C-13).

``SelfInterrogator.interrogate(stim, plan)`` deterministically synthesises
up to 5 ``InterrogationResult`` rows for a given (stimulus, plan) pair.
Many real loops invoke the same combination repeatedly (idle re-tick,
retry, multi-track re-evaluation); a cache short-circuits the rebuild
without touching the existing SelfInterrogator implementation.

The cache key folds the stimulus content (capped to 200 chars) with the
plan decision and confidence, so semantically-identical inputs land on
the same entry. ``SILRunner`` registers exactly one ThoughtLayer
(``SIL/interrogate``) so its hit / miss counters appear next to any
other layers sharing the coordinator (e.g. the multi-track scorer).
"""

from __future__ import annotations

from dataclasses import dataclass

from llive.fullsense.bridges.manifold_cache import semantic_hash
from llive.fullsense.bridges.tlb import ThoughtLayer, TLBCoordinator
from llive.fullsense.self_interrogation import (
    InterrogationResult,
    SelfInterrogator,
)
from llive.fullsense.types import ActionPlan, Stimulus

_LAYER = ThoughtLayer("interrogate", namespace="SIL")


@dataclass
class SILRunner:
    """Cache-fronted facade around ``SelfInterrogator``."""

    base: SelfInterrogator
    coordinator: TLBCoordinator

    @staticmethod
    def cache_key(stim: Stimulus, plan: ActionPlan) -> str:
        confidence = (
            plan.thought.confidence if plan.thought is not None else 0.0
        )
        body = (
            f"{(stim.content or '')[:200]}"
            f"|src={stim.source}"
            f"|epi={stim.epistemic_type}"
            f"|dec={plan.decision}"
            f"|conf={confidence:.3f}"
        )
        return semantic_hash(body)

    def run(self, stim: Stimulus, plan: ActionPlan) -> tuple[InterrogationResult, ...]:
        key = self.cache_key(stim, plan)

        def compute() -> tuple[InterrogationResult, ...]:
            return tuple(self.base.interrogate(stim, plan))

        return self.coordinator.query(_LAYER, key, compute)

    def stats(self) -> dict[str, object]:
        s = self.coordinator.stats().get(_LAYER.id)
        if s is None:
            return {"hits": 0, "misses": 0, "hit_rate": 0.0}
        return {"hits": s.hits, "misses": s.misses, "hit_rate": s.hit_rate}


__all__ = ["SILRunner"]
