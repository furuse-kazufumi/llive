# SPDX-License-Identifier: Apache-2.0
"""GA × 5 backend Genome PoC — backend 選択そのものを進化させる単体テスト."""

from __future__ import annotations

from llive.perf.evolutionary import (
    BlendCrossover,
    ChainedMutation,
    ElitismSelection,
    EvolutionConfig,
    EvolutionLoop,
    GaussianMutation,
    LLM_GENOME_BOUNDS,
    LLM_GENOME_LABELS,
    LlmFitnessConfig,
    Population,
    ResetMutation,
    TournamentSelection,
    llm_fitness_factory,
)


def test_backend_select_ga_runs_three_generations() -> None:
    """5 backend × sampler × quant の Genome で 3 世代 GA が走ること."""
    pop = Population.random(
        bounds=LLM_GENOME_BOUNDS,
        size=8,
        seed=0,
        labels=LLM_GENOME_LABELS,
    )
    fitness_fn = llm_fitness_factory(
        LlmFitnessConfig(
            prompts=("Reply OK",),
            n_stability_samples=1,
            danger_prompts=(),
            # backend 選択 GA 機構のテスト: mock 固定で評価する (cloud backend を含む
            # genome を回すため、実 backend purity gate は適用しない)。実 purity は
            # test_llm_fitness_*_purity 側で担保。None 明示で MockBackend fallback。
            backend_factory=None,
        )
    )
    loop = EvolutionLoop(
        fitness_fn=fitness_fn,
        selection=TournamentSelection(k=3),
        crossover=BlendCrossover(alpha=0.3),
        mutation=ChainedMutation(
            mutations=(
                GaussianMutation(sigma=0.15, p=0.2),
                ResetMutation(p=0.05),
            )
        ),
        elitism=ElitismSelection(top_n=2),
    )
    config = EvolutionConfig(max_generations=3, patience=10, log_progress=False)
    result = loop.run(pop, config)

    # 各個体に fitness が記録されている
    for ind in pop.individuals:
        assert ind.fitness is not None
        assert 0.0 <= ind.score <= 1.0

    # best_individual の Genome が bounds 内
    arr = result.best_individual.genome.as_array()
    lower = LLM_GENOME_BOUNDS.lower
    upper = LLM_GENOME_BOUNDS.upper
    for v, lo, up in zip(arr, lower, upper, strict=True):
        assert lo <= v <= up


def test_backend_select_with_no_danger_prompts_safety_neutral() -> None:
    fitness_fn = llm_fitness_factory(
        LlmFitnessConfig(prompts=("hello",), n_stability_samples=1, danger_prompts=())
    )
    pop = Population.random(bounds=LLM_GENOME_BOUNDS, size=4, seed=0)
    loop = EvolutionLoop(fitness_fn=fitness_fn)
    config = EvolutionConfig(max_generations=1, patience=10, log_progress=False)
    loop.run(pop, config)
    for ind in pop.individuals:
        assert ind.fitness is not None
        assert ind.fitness.breakdown["safety"] == 1.0  # neutral
