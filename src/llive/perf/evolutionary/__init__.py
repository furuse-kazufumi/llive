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

from llive.perf.evolutionary.coevolution_governance import (
    CoevolutionGovernance,
    CollusionDetector,
    GovernanceReport,
    collusion_risk_score,
)
from llive.perf.evolutionary.cross_substrate import (
    DEFAULT_INTENT_DIM,
    AbstractGenome,
    Substrate,
    SubstrateAdapter,
)
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
from llive.perf.evolutionary.expert_evolution import (
    CompositionStat,
    ExpertCompositionGenome,
    ExpertCompositionMutation,
    SurvivalRateTracker,
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
from llive.perf.evolutionary.frozen_gene import (
    MIN_SIGNATURE_BYTES,
    FreezeReason,
    FrozenGene,
)
from llive.perf.evolutionary.frozen_registry import FrozenGeneRegistry
from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.genome_3d import (
    Genome3D,
    cross_layer_crossover,
    intra_layer_crossover,
)
from llive.perf.evolutionary.impl_chromosome import (
    KNOWN_IMPL_ALGORITHM_FAMILIES,
    KNOWN_IMPL_JUDGE_MODELS,
    KNOWN_IMPL_LANGUAGES,
    KNOWN_IMPL_MEMORY_BACKENDS,
    KNOWN_IMPL_ORCHESTRATION_MODES,
    KNOWN_IMPL_PARALLEL_STRATEGIES,
    KNOWN_IMPL_SELECTOR_CLASSES,
    ImplChromosome,
)
from llive.perf.evolutionary.individual import FitnessReport, Individual
from llive.perf.evolutionary.island_model import (
    IslandModel,
    MigrationPolicy,
    Topology,
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
from llive.perf.evolutionary.mating import (
    LexicaseSelection,
    MutualScorePairSelector,
)
from llive.perf.evolutionary.meta_chromosome import (
    KNOWN_ALGORITHM_IDS,
    KNOWN_CROSSOVER_STRATEGIES,
    LAYER_NAMES,
    MetaChromosome,
    ucb1_score,
)
from llive.perf.evolutionary.meta_loop import (
    AlgorithmFn,
    MetaEvolutionLoop,
    MetaLoopState,
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
from llive.perf.evolutionary.novelty_lane import (
    MultiObjectiveSelector,
    NoveltyDescriptor,
    NoveltyScore,
    compute_novelty_scores,
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
from llive.perf.evolutionary.persona_corpus_loader import (
    PersonaCandidate,
    PersonaCorpusLoader,
)
from llive.perf.evolutionary.persona_import import (
    PersonaImportAlgorithm,
    PersonaImportPlan,
    PersonaZoneShareEvent,
)
from llive.perf.evolutionary.persona_survival import PersonaSurvivalAnalysis
from llive.perf.evolutionary.phylogeny import (
    KNOWN_OPS,
    PhyEdge,
    PhyNode,
    PhyTree,
    compute_individual_id,
)
from llive.perf.evolutionary.population import Population, PopulationStats
from llive.perf.evolutionary.prompt_chromosome import (
    KNOWN_PROMPT_LANGUAGE_STYLES,
    KNOWN_PROMPT_PERSONAS,
    KNOWN_PROMPT_RULES,
    KNOWN_PROMPT_SKILLS,
    KNOWN_PROMPT_TEMPLATES,
    PromptChromosome,
)
from llive.perf.evolutionary.quality_diversity import (
    MAPElitesCell,
    MAPElitesGrid,
    PersonaOverlapPenalty,
    default_map_elites_features,
    default_persona_features,
    default_thought_features,
)
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
from llive.perf.evolutionary.substrate_adapters import (
    BciSubstrateAdapter,
    CythonSubstrateAdapter,
    NeuromorphicSubstrateAdapter,
    PythonSubstrateAdapter,
    RustSubstrateAdapter,
    TypescriptSubstrateAdapter,
)

__all__ = [
    "DEFAULT_INTENT_DIM",
    "KNOWN_ALGORITHM_IDS",
    "KNOWN_CROSSOVER_STRATEGIES",
    "KNOWN_IMPL_ALGORITHM_FAMILIES",
    "KNOWN_IMPL_JUDGE_MODELS",
    "KNOWN_IMPL_LANGUAGES",
    "KNOWN_IMPL_MEMORY_BACKENDS",
    "KNOWN_IMPL_ORCHESTRATION_MODES",
    "KNOWN_IMPL_PARALLEL_STRATEGIES",
    "KNOWN_IMPL_SELECTOR_CLASSES",
    "KNOWN_OPS",
    "KNOWN_PROMPT_LANGUAGE_STYLES",
    "KNOWN_PROMPT_PERSONAS",
    "KNOWN_PROMPT_RULES",
    "KNOWN_PROMPT_SKILLS",
    "KNOWN_PROMPT_TEMPLATES",
    "LAYER_NAMES",
    "LIVE_VARIANT_GENOME_BOUNDS",
    "LIVE_VARIANT_GENOME_LABELS",
    "LIVE_VARIANT_SEGMENTS",
    "LLM_GENOME_BOUNDS",
    "LLM_GENOME_LABELS",
    "LV_OBJECT_DIMS",
    "MIN_SIGNATURE_BYTES",
    "PERSONA_ONTOLOGY",
    "THOUGHT_FACTORS",
    "UCB_GENOME_BOUNDS",
    "UCB_GENOME_LABELS",
    "AbstractGenome",
    "AlgorithmFn",
    "AsyncFitness",
    "AsyncioScheduler",
    "BciSubstrateAdapter",
    "BlendCrossover",
    "ChainedMutation",
    "CoevolutionGovernance",
    "CollusionDetector",
    "CompositionStat",
    "CouncilDecision",
    "CythonSubstrateAdapter",
    "DiversityMetrics",
    "DiversityMonitor",
    "DiversityPreservingBreedFilter",
    "ElitismSelection",
    "EvolutionConfig",
    "EvolutionLoop",
    "EvolutionResult",
    "Expert",
    "ExpertCompositionGenome",
    "ExpertCompositionMutation",
    "ExpertPanel",
    "Fitness",
    "FitnessFn",
    "FitnessReport",
    "FreezeReason",
    "FrozenGene",
    "FrozenGeneRegistry",
    "GaussianMutation",
    "Genome",
    "Genome3D",
    "GenomeBounds",
    "GovernanceReport",
    "ImplChromosome",
    "Individual",
    "IslandModel",
    "LexicaseSelection",
    "LlivVariantBuilder",
    "LlivVariantConfig",
    "LlmFitnessConfig",
    "MAPElitesCell",
    "MAPElitesGrid",
    "MetaChromosome",
    "MetaEvolutionLoop",
    "MetaLoopState",
    "MetaMutation",
    "MigrationPolicy",
    "MockVariantFitnessConfig",
    "MultiObjectiveSelector",
    "MultiprocessingScheduler",
    "MutualScorePairSelector",
    "NSGA2Selection",
    "NeuromorphicSubstrateAdapter",
    "NoveltyDescriptor",
    "NoveltyScore",
    "NoveltyScorer",
    "PairScoreFn",
    "PeerEvaluationMatrix",
    "PeerFitnessAdapter",
    "Persona",
    "PersonaCandidate",
    "PersonaComposition",
    "PersonaCompositionMutation",
    "PersonaCorpusLoader",
    "PersonaImportAlgorithm",
    "PersonaImportPlan",
    "PersonaOverlapPenalty",
    "PersonaSurvivalAnalysis",
    "PersonaZoneShareEvent",
    "PhyEdge",
    "PhyNode",
    "PhyTree",
    "Population",
    "PopulationStats",
    "PromptChromosome",
    "ResetMutation",
    "RouletteSelection",
    "SegmentCrossover",
    "SegmentedScheduler",
    "SelfAdaptiveGaussianMutation",
    "SpeciatedTournamentSelection",
    "Speciation",
    "SpeciationLayer",
    "Species",
    "SurvivalRateTracker",
    "Topology",
    "TournamentSelection",
    "UcbFitnessConfig",
    "UniformCrossover",
    "VariantSubprocessError",
    "VariantSubprocessScheduler",
    "Winner",
    "build_meta_strategy_variant_bounds",
    "build_panel_from_personas",
    "build_self_adaptive_meta_strategy_variant_bounds",
    "build_self_adaptive_variant_bounds",
    "call_fitness_with_seed",
    "collusion_risk_score",
    "compute_individual_id",
    "compute_novelty_scores",
    "cross_layer_crossover",
    "crowding_distance",
    "default_map_elites_features",
    "default_persona_features",
    "default_thought_features",
    "default_variant_meta_strategies",
    "derive_sub_seed",
    "fitness_accepts_seed",
    "get_persona",
    "initial_sigma_values",
    "initialize_self_adaptive_variant_genome_values",
    "intra_layer_crossover",
    "latin_hypercube_population",
    "list_persona_ids",
    "llm_fitness_factory",
    "load_winners_jsonl",
    "make_meta_variant_mutation",
    "make_self_adaptive_variant_mutation",
    "mock_variant_fitness_factory",
    "non_dominated_sort",
    "pack_meta_strategy_bounds",
    "pack_self_adaptive_bounds",
    "persona_dissimilarity",
    "random_persona_composition",
    "render_lineage_mermaid",
    "rosenbrock_fitness",
    "serial_scheduler",
    "sphere_fitness",
    "strategy_distribution",
    "ucb1_score",
    "ucb_fitness_factory",
    "wrap_fitness_for_extended_genome",
    "write_lineage_mermaid_file",
    "write_winners_jsonl",
]
