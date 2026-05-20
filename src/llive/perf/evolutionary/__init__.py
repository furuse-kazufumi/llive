# SPDX-License-Identifier: Apache-2.0
"""Evolutionary optimization layer (llive v0.B).

ロボット歩行進化の AI 版. 集団 → 評価 → 選別 → 交配 → 突然変異 → 次世代 を
回して hyperparameter を進化させる. 既存 UCBSynapticSelector (収束型) と
直交し, 個体内 variant 選択は UCB, 個体間競争は GA に分担できる.

主要シンボル:

* :class:`Genome`, :class:`GenomeBounds`
* :class:`Individual`, :class:`FitnessReport`
* :class:`Population`, :class:`PopulationStats`
* :class:`TournamentSelection`, :class:`RouletteSelection`, :class:`ElitismSelection`
* :class:`UniformCrossover`, :class:`BlendCrossover`
* :class:`GaussianMutation`, :class:`ResetMutation`, :class:`ChainedMutation`
* :class:`EvolutionLoop`, :class:`EvolutionConfig`, :class:`EvolutionResult`
* :class:`MultiprocessingScheduler`, :class:`AsyncioScheduler`, :func:`serial_scheduler`
* :func:`sphere_fitness`, :func:`rosenbrock_fitness`, :func:`ucb_fitness_factory`
"""

from llive.perf.evolutionary.crossover import (
    BlendCrossover,
    SegmentCrossover,
    UniformCrossover,
)
from llive.perf.evolutionary.fitness import (
    Fitness,
    FitnessFn,
    rosenbrock_fitness,
    sphere_fitness,
)
from llive.perf.evolutionary.fitness_llm import (
    LLM_GENOME_BOUNDS,
    LLM_GENOME_LABELS,
    LlmFitnessConfig,
    llm_fitness_factory,
)
from llive.perf.evolutionary.fitness_ucb import (
    UCB_GENOME_BOUNDS,
    UCB_GENOME_LABELS,
    UcbFitnessConfig,
    ucb_fitness_factory,
)
from llive.perf.evolutionary.lineage import (
    Winner,
    load_winners_jsonl,
    render_lineage_mermaid,
    write_lineage_mermaid_file,
    write_winners_jsonl,
)
from llive.perf.evolutionary.llive_variant import (
    LIVE_VARIANT_GENOME_BOUNDS,
    LIVE_VARIANT_GENOME_LABELS,
    LIVE_VARIANT_SEGMENTS,
    LlivVariantBuilder,
    LlivVariantConfig,
    MockVariantFitnessConfig,
    SegmentedScheduler,
    mock_variant_fitness_factory,
)
from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.individual import FitnessReport, Individual
from llive.perf.evolutionary.loop import (
    EvolutionConfig,
    EvolutionLoop,
    EvolutionResult,
)
from llive.perf.evolutionary.mutation import (
    ChainedMutation,
    GaussianMutation,
    ResetMutation,
)
from llive.perf.evolutionary.population import Population, PopulationStats
from llive.perf.evolutionary.scheduler import (
    AsyncFitness,
    AsyncioScheduler,
    MultiprocessingScheduler,
    serial_scheduler,
)
from llive.perf.evolutionary.seeds import (
    call_fitness_with_seed,
    derive_sub_seed,
    fitness_accepts_seed,
)
from llive.perf.evolutionary.selection import (
    ElitismSelection,
    RouletteSelection,
    TournamentSelection,
)

__all__ = [
    "AsyncFitness",
    "AsyncioScheduler",
    "BlendCrossover",
    "ChainedMutation",
    "ElitismSelection",
    "EvolutionConfig",
    "EvolutionLoop",
    "EvolutionResult",
    "Fitness",
    "FitnessFn",
    "FitnessReport",
    "GaussianMutation",
    "Genome",
    "GenomeBounds",
    "Individual",
    "MultiprocessingScheduler",
    "Population",
    "PopulationStats",
    "ResetMutation",
    "RouletteSelection",
    "TournamentSelection",
    "LIVE_VARIANT_GENOME_BOUNDS",
    "LIVE_VARIANT_GENOME_LABELS",
    "LIVE_VARIANT_SEGMENTS",
    "LLM_GENOME_BOUNDS",
    "LLM_GENOME_LABELS",
    "LlivVariantBuilder",
    "LlivVariantConfig",
    "LlmFitnessConfig",
    "MockVariantFitnessConfig",
    "SegmentCrossover",
    "SegmentedScheduler",
    "UCB_GENOME_BOUNDS",
    "UCB_GENOME_LABELS",
    "UcbFitnessConfig",
    "UniformCrossover",
    "Winner",
    "call_fitness_with_seed",
    "derive_sub_seed",
    "fitness_accepts_seed",
    "llm_fitness_factory",
    "load_winners_jsonl",
    "mock_variant_fitness_factory",
    "render_lineage_mermaid",
    "rosenbrock_fitness",
    "serial_scheduler",
    "sphere_fitness",
    "ucb_fitness_factory",
]
