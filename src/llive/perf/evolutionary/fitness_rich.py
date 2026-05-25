# SPDX-License-Identifier: Apache-2.0
"""Richer **multi-modal / multi-objective** proxy fitness (Stage 1 of the
"make the evolution actually evolve" redesign).

Why this exists
---------------
The original :func:`llive.perf.evolutionary.persona_evolution._proxy_fitness`
collapses the 10×4 ``c_factors`` matrix to a **layer-averaged 10-vector** and
scores ``0.7*balance + 0.3*provenance`` — a single, smooth, uni-modal hill whose
optimum is "all thought factors uniformly high". Empirically (proxy run, seed 2,
500 gens) this made:

* every founder persona lineage go **extinct by gen 23** (uniform-high is *not*
  where any persona sits, so persona-seeded individuals are selected against),
* ``best`` plateau at gen 281 (44 % of the run adds zero improvement),
* diversity collapse by gen 25 (single peak → premature convergence),
* ``c_impl`` / ``c_prompt`` / ``c_meta`` evolve under **zero** selection pressure
  (pure neutral drift — fitness never reads them).

Research backing (see fullsense/docs/research): premature convergence + the
many-objective "curse of dimensionality" (Pareto dominance loses discriminative
power past ~4 objectives), and open-ended-evolution requirements (variation +
heredity + selection are *not sufficient* for open-endedness). The fix is a
**multi-modal** landscape (one niche per persona) that exercises the **full 40
``c_factors`` dims** plus the categorical chromosomes, and exposes a
**multi-objective breakdown** so niching / NSGA-II / lexicase selection can be
wired on top (Stage 2).

What this fitness rewards
-------------------------
For each founder persona we build an *archetype* 10×4 matrix = that persona's
``factor_affinity`` broadcast across the memory layers (the same ``"uniform"``
broadcast used to seed founders, so **each founder sits exactly on its own
archetype peak**, similarity = 1.0). The score is the **max similarity across
archetypes** — a genuinely multi-modal landscape with one peak per persona, so
distinct persona lineages can coexist in distinct niches instead of all being
pulled to a single uniform-high optimum.

* every one of the 40 ``c_factors`` cells is under selection (matching the
  nearest archetype cell-by-cell), 4× the effective dimensionality of the old
  proxy;
* a small **chromosome-coherence** term puts (mild) selection pressure on
  ``c_prompt`` / ``c_meta`` so they are no longer purely decorative;
* ``breakdown["archetype::<persona>"]`` holds the per-archetype similarities —
  these are the multi-objective vector that Stage-2 NSGA-II / lexicase consume.

HONEST DISCLOSURE: this is still a **proxy** (deterministic, no LLM). A clean
multi-modal proxy proves the *machinery* can maintain niches; it does not prove
the evolved configs are good. Real fitness = LLM task eval (see
``compare_against_llm_baselines``). Tag every result "proxy".
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from llive.benchmark.runtime_metadata import collect_runtime_metadata
from llive.perf.evolutionary.fitness import Fitness
from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.individual import FitnessReport
from llive.perf.evolutionary.persona import (
    NUM_THOUGHT_FACTORS,
    get_persona,
)
from llive.perf.evolutionary.thought_factor_per_layer import (
    DEFAULT_MEMORY_LAYER_NAMES,
    NUM_MEMORY_LAYERS,
)

#: rule_set tokens that FullSense treats as load-bearing (rewarded for coherence).
_CORE_RULES = ("fail_closed", "honest_disclosure")


def _factor_matrix(genome: object) -> np.ndarray:
    """Return a (10, n_layers) factor matrix for either genome type.

    * :class:`Genome3D` → its ``c_factors`` matrix (full 10×4, **no averaging**).
    * flat ``Genome`` → thought-factor dims 0..9 broadcast across layers (so the
      same archetype math applies; flat genomes simply can't differentiate layers).
    """
    c_factors = getattr(genome, "c_factors", None)
    if c_factors is not None:
        return np.asarray(c_factors.as_array(), dtype=np.float64)
    as_array = getattr(genome, "as_array", None)
    if callable(as_array):
        vec = np.asarray(as_array(), dtype=np.float64)[:NUM_THOUGHT_FACTORS]
        return np.tile(vec[:, None], (1, NUM_MEMORY_LAYERS))
    raise TypeError(f"unsupported genome type for rich fitness: {type(genome).__name__}")


def build_archetypes(persona_ids: Sequence[str]) -> dict[str, np.ndarray]:
    """persona id → archetype (10×4) matrix = affinity broadcast uniformly.

    Uniform broadcast matches ``build_founder_genome_3d(..., "uniform")`` so each
    founder lands exactly on its own archetype peak (similarity 1.0).
    """
    archetypes: dict[str, np.ndarray] = {}
    n_layers = len(DEFAULT_MEMORY_LAYER_NAMES)
    for pid in persona_ids:
        affinity = np.asarray(get_persona(pid).factor_affinity, dtype=np.float64)
        if affinity.shape[0] != NUM_THOUGHT_FACTORS:
            raise ValueError(
                f"persona {pid!r} affinity has {affinity.shape[0]} dims, "
                f"expected {NUM_THOUGHT_FACTORS}"
            )
        archetypes[pid] = np.tile(affinity[:, None], (1, n_layers))
    return archetypes


def _similarity(factors: np.ndarray, archetype: np.ndarray) -> float:
    """1 - mean cell-wise L1 distance over the full matrix. Cells ∈ [0,1] ⇒ ∈ [0,1].

    Uses *all* cells (10×4 = 40), so layer-level deviations are penalised — the
    layer axis is no longer fitness-neutral (it was averaged away in the old proxy).
    """
    if factors.shape != archetype.shape:
        # flat genome (10×4 broadcast) vs 10×4 archetype always match; guard anyway
        n = min(factors.shape[1], archetype.shape[1])
        factors, archetype = factors[:, :n], archetype[:, :n]
    return float(1.0 - np.mean(np.abs(factors - archetype)))


def _chromosome_coherence(genome: object) -> float:
    """Mild [0,1] reward on c_prompt / c_meta so they aren't pure neutral drift.

    Deterministic, structure-based (not persona-specific — persona-tied chromosome
    objectives are Stage 2). Rewards: presence of FullSense core rules, a
    non-degenerate (but not bloated) skill_set, and a sane meta selection_pressure.
    Flat genomes (no chromosomes) get a neutral 0.5.
    """
    c_prompt = getattr(genome, "c_prompt", None)
    c_meta = getattr(genome, "c_meta", None)
    if c_prompt is None and c_meta is None:
        return 0.5

    terms: list[float] = []
    if c_prompt is not None:
        rules = set(getattr(c_prompt, "rule_set", ()) or ())
        terms.append(sum(1 for r in _CORE_RULES if r in rules) / len(_CORE_RULES))
        skills = getattr(c_prompt, "skill_set", ()) or ()
        # reward 2..5 skills (some specialisation, not everything-on)
        n = len(set(skills))
        terms.append(1.0 if 2 <= n <= 5 else max(0.0, 1.0 - abs(n - 3) / 5.0))
    if c_meta is not None:
        sp = float(getattr(c_meta, "selection_pressure", 0.5) or 0.5)
        # peak coherence at moderate pressure ~0.5, falling off toward extremes
        terms.append(max(0.0, 1.0 - abs(sp - 0.5) * 2.0))
    return float(np.mean(terms)) if terms else 0.5


def make_rich_proxy_fitness(
    persona_ids: Sequence[str],
    *,
    factor_weight: float = 0.85,
) -> Fitness:
    """Build a multi-modal / multi-objective proxy :data:`Fitness` callable.

    Parameters
    ----------
    persona_ids:
        Founder personas → one archetype peak each (the multi-modal niches).
    factor_weight:
        Weight on the 40-dim factor-match term; ``1 - factor_weight`` goes to the
        chromosome-coherence term. Default 0.85 keeps the factor landscape dominant
        while still putting non-zero pressure on the categorical chromosomes.

    Returns
    -------
    Fitness
        ``Callable[[Genome | Genome3D], FitnessReport]``. ``score`` is the scalar
        (max-archetype similarity blended with coherence) for single-objective
        consumers; ``breakdown`` exposes per-archetype similarities + the nearest
        persona for Stage-2 niching / NSGA-II / lexicase.
    """
    if not 0.0 <= factor_weight <= 1.0:
        raise ValueError(f"factor_weight must be in [0,1], got {factor_weight}")
    archetypes = build_archetypes(persona_ids)
    persona_list = list(persona_ids)

    def fitness(genome: object) -> FitnessReport:  # noqa: ANN001
        factors = _factor_matrix(genome)
        sims = {pid: _similarity(factors, arch) for pid, arch in archetypes.items()}
        nearest = max(sims, key=sims.get)
        factor_score = sims[nearest]
        coherence = _chromosome_coherence(genome)
        score = factor_weight * factor_score + (1.0 - factor_weight) * coherence

        breakdown = {f"archetype::{pid}": v for pid, v in sims.items()}
        breakdown["factor_score"] = factor_score
        breakdown["chromosome_coherence"] = coherence
        breakdown["nearest_persona_idx"] = float(persona_list.index(nearest))

        return FitnessReport(
            score=float(max(0.0, min(1.0, score))),
            breakdown=breakdown,
            runtime_metadata=dict(collect_runtime_metadata()),
            n_samples=1,
            notes=(
                "PROXY fitness (NOT real LLM evaluation). Multi-modal: max similarity "
                f"across {len(persona_list)} persona archetypes over the full 10x4 "
                "c_factors matrix, blended with chromosome coherence. Per-archetype "
                "similarities in breakdown are the multi-objective vector for Stage-2 "
                f"niching/NSGA-II/lexicase. nearest_persona={nearest}."
            ),
        )

    return fitness


__all__ = [
    "build_archetypes",
    "make_rich_proxy_fitness",
]
