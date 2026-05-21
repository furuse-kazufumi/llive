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
from llive.perf.evolutionary.diversity import (
    DiversityMetrics,
    DiversityMonitor,
    DiversityPreservingBreedFilter,
    NoveltyScorer,
    latin_hypercube_population,
)
from llive.perf.evolutionary.expert_council import (
    CouncilDecision,
    Expert,
    ExpertPanel,
    build_panel_from_personas,
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
from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.individual import FitnessReport, Individual
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
from llive.perf.evolutionary.llive_variant_extras import (
    LV_OBJECT_DIMS,
    build_meta_strategy_variant_bounds,
    build_self_adaptive_meta_strategy_variant_bounds,
    build_self_adaptive_variant_bounds,
    default_variant_meta_strategies,
    initialize_self_adaptive_variant_genome_values,
    make_meta_variant_mutation,
    make_self_adaptive_variant_mutation,
    wrap_fitness_for_extended_genome,
)
from llive.perf.evolutionary.loop import (
    EvolutionConfig,
    EvolutionLoop,
    EvolutionResult,
)
from llive.perf.evolutionary.island_model import (
    IslandModel,
    MigrationPolicy,
    Topology,
)
from llive.perf.evolutionary.mating import (
    LexicaseSelection,
    MutualScorePairSelector,
)
from llive.perf.evolutionary.meta_mutation import (
    MetaMutation,
    pack_meta_strategy_bounds,
    strategy_distribution,
)
from llive.perf.evolutionary.mutation import (
    ChainedMutation,
    GaussianMutation,
    ResetMutation,
)
from llive.perf.evolutionary.nsga2 import (
    NSGA2Selection,
    crowding_distance,
    non_dominated_sort,
)
from llive.perf.evolutionary.peer_evaluation import (
    PairScoreFn,
    PeerEvaluationMatrix,
    PeerFitnessAdapter,
)
from llive.perf.evolutionary.persona import (
    PERSONA_ONTOLOGY,
    THOUGHT_FACTORS,
    Persona,
    PersonaComposition,
    PersonaCompositionMutation,
    get_persona,
    list_persona_ids,
    persona_dissimilarity,
    random_persona_composition,
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
from llive.perf.evolutionary.self_adaptive import (
    SelfAdaptiveGaussianMutation,
    initial_sigma_values,
    pack_self_adaptive_bounds,
)
from llive.perf.evolutionary.speciation import (
    SpeciatedTournamentSelection,
    Speciation,
    SpeciationLayer,
    Species,
)
from llive.perf.evolutionary.subprocess_scheduler import (
    VariantSubprocessError,
    VariantSubprocessScheduler,
)

__all__ = [
    "LIVE_VARIANT_GENOME_BOUNDS",
    "LIVE_VARIANT_GENOME_LABELS",
    "LIVE_VARIANT_SEGMENTS",
    "LLM_GENOME_BOUNDS",
    "LLM_GENOME_LABELS",
    "LV_OBJECT_DIMS",
    "PERSONA_ONTOLOGY",
    "THOUGHT_FACTORS",
    "UCB_GENOME_BOUNDS",
    "UCB_GENOME_LABELS",
    "AsyncFitness",
    "AsyncioScheduler",
    "BlendCrossover",
    "ChainedMutation",
    "DiversityMetrics",
    "DiversityMonitor",
    "DiversityPreservingBreedFilter",
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
    "LexicaseSelection",
    "LlivVariantBuilder",
    "LlivVariantConfig",
    "LlmFitnessConfig",
    "MetaMutation",
    "MockVariantFitnessConfig",
    "MultiprocessingScheduler",
    "MutualScorePairSelector",
    "NoveltyScorer",
    "PairScoreFn",
    "PeerEvaluationMatrix",
    "PeerFitnessAdapter",
    "Persona",
    "PersonaComposition",
    "PersonaCompositionMutation",
    "Population",
    "PopulationStats",
    "ResetMutation",
    "RouletteSelection",
    "SegmentCrossover",
    "SegmentedScheduler",
    "SelfAdaptiveGaussianMutation",
    "TournamentSelection",
    "UcbFitnessConfig",
    "UniformCrossover",
    "VariantSubprocessError",
    "VariantSubprocessScheduler",
    "Winner",
    "build_meta_strategy_variant_bounds",
    "build_self_adaptive_meta_strategy_variant_bounds",
    "build_self_adaptive_variant_bounds",
    "call_fitness_with_seed",
    "default_variant_meta_strategies",
    "derive_sub_seed",
    "fitness_accepts_seed",
    "get_persona",
    "initial_sigma_values",
    "initialize_self_adaptive_variant_genome_values",
    "latin_hypercube_population",
    "list_persona_ids",
    "llm_fitness_factory",
    "load_winners_jsonl",
    "make_meta_variant_mutation",
    "make_self_adaptive_variant_mutation",
    "mock_variant_fitness_factory",
    "pack_meta_strategy_bounds",
    "pack_self_adaptive_bounds",
    "persona_dissimilarity",
    "random_persona_composition",
    "render_lineage_mermaid",
    "rosenbrock_fitness",
    "serial_scheduler",
    "sphere_fitness",
    "strategy_distribution",
    "ucb_fitness_factory",
    "wrap_fitness_for_extended_genome",
    "write_lineage_mermaid_file",
    "write_winners_jsonl",
]
