# SPDX-License-Identifier: Apache-2.0
"""TRIZ Principle Mapper (TRIZ-03 / FR-24).

Wraps :func:`llive.triz.loader.lookup_principles` and the matrix data to
produce ordered, scored recommendations for a given :class:`Contradiction`.

Scoring is intentionally simple at Phase 3 MVR:

* base score 1.0 for any matrix hit
* `+0.15` per documented `examples` entry on the principle (cap +0.45)
* tie-break by lower principle id (stable, deterministic)

The mapper has **no LLM dependency** so it stays cheap and unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from llive.triz.contradiction import Contradiction
from llive.triz.loader import Principle, load_matrix, load_principles


@dataclass
class PrincipleRecommendation:
    principle: Principle
    score: float
    rank: int
    rationale: str = ""


@dataclass
class MappingResult:
    contradiction_id: str
    improving_id: int
    worsening_id: int
    recommendations: list[PrincipleRecommendation] = field(default_factory=list)
    fallback_used: bool = False  # true when matrix had no entry; we returned heuristic fallback


_FALLBACK_PRINCIPLES: tuple[int, ...] = (1, 13, 15, 35, 40)


def map_contradiction(
    contradiction: Contradiction,
    *,
    top_k: int = 3,
    matrix: dict[tuple[int, int], tuple[int, ...]] | None = None,
    principles_index: dict[int, Principle] | None = None,
) -> MappingResult:
    matrix = matrix if matrix is not None else load_matrix()
    principles = principles_index if principles_index is not None else load_principles()
    pair = (int(contradiction.improve_feature_id), int(contradiction.degrade_feature_id))
    ids = matrix.get(pair, ())
    fallback = False
    if not ids:
        ids = tuple(p for p in _FALLBACK_PRINCIPLES if p in principles)
        fallback = True
    candidates: list[tuple[Principle, float]] = []
    for pid in ids:
        if pid not in principles:
            continue
        principle = principles[pid]
        score = 1.0 + min(0.45, 0.15 * len(principle.examples))
        candidates.append((principle, score))
    candidates.sort(key=lambda x: (-x[1], x[0].id))
    recs: list[PrincipleRecommendation] = []
    for rank, (principle, score) in enumerate(candidates[: max(0, int(top_k))], start=1):
        recs.append(
            PrincipleRecommendation(
                principle=principle,
                score=float(score),
                rank=rank,
                rationale=_short_rationale(contradiction, principle, fallback),
            )
        )
    return MappingResult(
        contradiction_id=contradiction.contradiction_id,
        improving_id=pair[0],
        worsening_id=pair[1],
        recommendations=recs,
        fallback_used=fallback,
    )


def _short_rationale(c: Contradiction, principle: Principle, fallback: bool) -> str:
    if fallback:
        return (
            f"matrix miss for ({c.improve_feature_id},{c.degrade_feature_id}); "
            f"fallback principle {principle.id} suggested."
        )
    examples = "; ".join(principle.examples[:2])
    if examples:
        return f"principle {principle.id} ({principle.name}) — e.g. {examples}"
    return f"principle {principle.id} ({principle.name})"


__all__ = ["MappingResult", "PrincipleRecommendation", "map_contradiction"]
