# evolutionary モジュール棚卸し (2026-05-27)

北極星「連続進化 × ライブ MoA オーケストラ」× lldarwin v2 (ε-lexicase + novelty + 適応難易度 + MAP-Elites + factor-subspace QD + 中立貯蔵庫) を軸に、
`src/llive/perf/evolutionary/` の全モジュール (61 本) を分類する。

> **HONEST DISCLOSURE**: 配線判定は静的 import 解析ベース。`__init__.py` の一括 import は「記述あり」と判断したが、
> `run_persona_evolution` / `EvolutionLoop` / `lldarwin_v2` の **実行経路で直接呼ばれるか** を第一基準とした。
> 動的 import (`from X import Y` が関数内 lazy ロードの場合) は注記。テスト数は `tests/` 配下の `def test_` 数。

---

## 1. モジュール分類表

| モジュール名 | 行数 | 配線状況 | 北極星貢献度 | frozen判定 | テスト数 |
|---|---|---|---|---|---|
| `genome.py` | 118 | **配線済** (persona_evolution, loop) | コア | - | - |
| `individual.py` | 103 | **配線済** (persona_evolution, loop) | コア | - | - |
| `population.py` | 155 | **配線済** (persona_evolution, loop) | コア | - | - |
| `fitness.py` | 55 | **配線済** (loop, persona_evolution, lldarwin) | コア | - | - |
| `loop.py` | 317 | **配線済** (persona_evolution が直接 import) | コア | - | - |
| `selection.py` | 57 | **配線済** (loop.py が直接 import) | コア | - | - |
| `crossover.py` | 97 | **配線済** (loop.py が直接 import) | コア | - | - |
| `mutation.py` | 55 | **配線済** (loop.py が直接 import) | コア | - | - |
| `seeds.py` | 86 | **配線済** (loop.py が直接 import) | コア | - | - |
| `mating.py` | 179 | **配線済** (lldarwin.py が import; LexicaseSelection がコア) | コア | - | - |
| `lldarwin.py` | 238 | **配線済** (lldarwin_v2.py が import; MultiPressureSelector) | コア | - | - |
| `lldarwin_v2.py` | 205 | **配線済** (scripts/ablation + テストで run 経路から呼ばれる) | コア (S1選択核プリセット) | - | - |
| `diversity.py` | 318 | **配線済** (lldarwin.py が NoveltyScorer を import) | コア (novelty scorer) | - | - |
| `quality_diversity.py` | 403 | **配線済** (lldarwin.py が FactorSubspaceNovelty; persona_evolution で lazy import) | コア (MAP-Elites + factor-subspace QD) | - | - |
| `pressures.py` | 253 | **配線済** (lldarwin_v2.py が AdaptivePercentileGate + factor_vector を直接 import) | コア (適応難易度gate) | - | - |
| `lineage_reservoir.py` | 121 | **配線済** (persona_evolution が lazy import; lineage_reservoir=True で実行) | コア (中立貯蔵庫) | - | 7 |
| `genome_3d.py` | 225 | **配線済** (persona_evolution, individual, population が import) | コア (多層ゲノム) | - | - |
| `genome_3d_operators.py` | 59 | **配線済** (persona_evolution が直接 import) | コア (Genome3D演算子) | - | - |
| `persona.py` | 477 | **配線済** (persona_evolution が直接 import; PERSONA_ONTOLOGY) | コア (persona定義) | - | - |
| `persona_evolution.py` | 837 | **配線済** (turnkey driver = 実行起点) | コア (turnkey orchestrator) | - | 多数 |
| `lineage.py` | 190 | **配線済** (persona_evolution が直接 import; winners.jsonl) | コア (系統記録) | - | - |
| `llive_variant.py` | 330 | **配線済** (persona_evolution が LIVE_VARIANT_GENOME_BOUNDS 等を直接 import) | コア (Genome bounds/labels) | - | - |
| `prompt_chromosome.py` | 267 | **配線済** (persona_evolution が直接 import; PromptChromosome) | コア (Genome3D c_prompt層) | - | 0 |
| `thought_factor_per_layer.py` | 307 | **配線済** (persona_evolution が直接 import; Genome3D layer chromosome) | コア (Genome3D c_factors層) | - | 25 |
| `genome_version.py` | 167 | **配線済** (cma_es_diversity, テスト群) | 補助 (バージョン管理) | - | 15 |
| `novelty_lane.py` | 238 | **配線済** (__init__ のみ; NoveltyDescriptor/MultiObjectiveSelector) | 補助 (NSGA-II前処理 + novelty augment) | - | 31 |
| `phylogeny.py` | 709 | 未配線 (__init__ のみ export。experiments/phylogeny_svg_demo で利用) | 周辺 (系統樹構造・可視化) | 隔離候補 | 45 |
| `svg_render.py` | 452 | 部分配線 (scripts/render_evolution_svg.py から呼ばれる; run 本体からは呼ばれない) | 周辺 (可視化) | 保留 | 17 |
| `real_pressures.py` | 328 | 部分配線 (scripts/run_persona_evolution_long.py + poc_orchestra.py から参照; Stage2後半実LLM) | 補助 (実LLM評価、未完成) | 保留 | 9 |
| `fitness_llm.py` | 320 | 部分配線 (scripts/run_persona_evolution_long.py + テスト群) | 補助 (LLM fitness factory) | 保留 | 23 |
| `fitness_rich.py` | 179 | 未配線 (__init__ のみ export) | 補助 (rich multi-axis fitness) | 隔離候補 | 0 |
| `fitness_ucb.py` | 109 | 未配線 (__init__ のみ export) | 補助 (UCB fitness factory) | 隔離候補 | 0 |
| `llive_variant_extras.py` | 167 | 部分配線 (__init__ + subprocess_scheduler経由) | 補助 (self_adaptive/meta_strategy variant) | 保留 | 14 |
| `subprocess_scheduler.py` | 279 | 部分配線 (__init__ のみ; VariantSubprocessScheduler) | 補助 (variant subprocess実行) | 保留 | - |
| `scheduler.py` | 85 | 未配線 (本体 loop.py は内部 _serial_scheduler を使用; AsyncioScheduler/MPSchedulerは未使用) | 補助 (並列スケジューラ) | 隔離候補 | 0 |
| `parallel_mutation.py` | 227 | 未配線 (__init__ + test_duplication.py のみ) | 補助 (並列評価) | 隔離候補 | 0 |
| `impl_chromosome.py` | 283 | 未配線 (__init__ のみ export) | 周辺 (実装戦略染色体) | 隔離候補 | 0 |
| `meta_chromosome.py` | 278 | 未配線 (genome_3d.py が内部import; experiments/poc でのみ使用) | 周辺 (メタアルゴリズム染色体) | 隔離候補 | 29 |
| `meta_loop.py` | 251 | 未配線 (__init__ + experiments/meta_evolution_poc のみ) | 周辺 (メタ進化ループ) | 隔離候補 | 0 |
| `meta_mutation.py` | 114 | 未配線 (__init__ + llive_variant_extras経由のみ) | 周辺 (メタ戦略突然変異) | 隔離候補 | 10 |
| `island_model.py` | 168 | 未配線 (__init__ のみ export) | 周辺 (島モデル GA) | 隔離候補 | 17 |
| `expert_council.py` | 293 | 未配線 (__init__ + expert_evolution.py のみ) | 周辺 (expert panel) | 隔離候補 | 20 |
| `expert_evolution.py` | 271 | 未配線 (__init__ + persona_survival.py のみ) | 周辺 (expert composition進化) | 隔離候補 | 22 |
| `speciation.py` | 207 | 未配線 (__init__ のみ export) | 周辺 (種分化) | 隔離候補 | 12 |
| `nsga2.py` | 234 | 未配線 (__init__ のみ export) | 周辺 (NSGA-II多目的) | 隔離候補 | 14 |
| `peer_evaluation.py` | 302 | 未配線 (mating.py + coevolution_governance.py のみ; run経路に届かない) | 周辺 (peer評価行列) | 隔離候補 | 14 |
| `coevolution_governance.py` | 243 | 未配線 (__init__ のみ; CollusionDetector/ApprovalBus skeleton) | 周辺 (共謀検出skeleton) | 隔離候補 | 28 |
| `self_adaptive.py` | 158 | 未配線 (__init__ + llive_variant_extras経由のみ) | 周辺 (自己適応ステップ幅) | 隔離候補 | 14 |
| `cma_es.py` | 430 | 未配線 (__init__ + テスト群のみ) | 周辺 (CMA-ES adapter) | 隔離候補 | 63 (重い) |
| `cma_es_diversity.py` | 370 | 未配線 (__init__ + テスト群 + frozen_registry経由のみ) | 周辺 (CMA-ES多様性ドライバ) | 隔離候補 | 21 |
| `cross_substrate.py` | 246 | 未配線 (__init__ + substrate_adapters経由のみ) | 周辺 (抽象substrate) | 隔離候補 | 37 |
| `substrate_adapters.py` | 208 | 未配線 (__init__ + cross_substrate.py が内部型のみ参照) | 周辺 (Rust/Python/etc adapter) | 隔離候補 | 0 |
| `mcp_substrate_adapter.py` | 233 | 未配線 (__init__ + experiments/mcp_genome_poc のみ) | 周辺 (MCP genome adapter) | 隔離候補 | 0 |
| `recursive_inference.py` | 146 | 未配線 (__init__ + recursion_depth内部のみ) | 周辺 (再帰推論) | 隔離候補 | 0 |
| `recursion_depth.py` | 313 | 未配線 (__init__ のみ export) | 周辺 (再帰深度遺伝子) | 隔離候補 | 30 |
| `duplication.py` | 118 | 未配線 (__init__ + llive_variant_extras; run経路に届かない) | 周辺 (遺伝子重複) | 隔離候補 | 43 (重い) |
| `frozen_gene.py` | 213 | 未配線 (__init__ + cma_es_diversity経由のみ) | 周辺 (凍結遺伝子) | 隔離候補 | 49 (重い) |
| `frozen_registry.py` | 135 | 未配線 (__init__ + frozen_gene経由のみ) | 周辺 (凍結レジストリ) | 隔離候補 | 0 |
| `latent_reservoir.py` | 135 | 未配線 (import元なし; 実験的染色体) | 周辺 (潜在変異貯蔵庫) | 隔離候補 | 0 |
| `persona_import.py` | 350 | 未配線 (__init__ のみ export) | 周辺 (persona zone-share algorithm) | 隔離候補 | 26 |
| `persona_survival.py` | 121 | 未配線 (__init__ + persona_extended経由のみ) | 周辺 (persona生存分析) | 隔離候補 | 16 |
| `persona_corpus_loader.py` | 355 | 未配線 (__init__ のみ export) | 周辺 (persona corpus loader) | 隔離候補 | 19 |
| `persona_extended.py` | 139 | 未配線 (__init__ のみ export) | 周辺 (persona拡張定義) | 隔離候補 | 6 |
| `__init__.py` | 546 | — (re-export 集約のみ) | — | — | — |

---

## 2. コア最小セット (進化エンジン + lldarwin v2 が回る最小モジュール群)

以下の **24 モジュール** があれば `run_persona_evolution(selection=build_lldarwin_v2_selector())` が完走できる。

### 進化基盤 (11 本)
| モジュール | 役割 |
|---|---|
| `genome.py` | Genome / GenomeBounds 定義 |
| `individual.py` | Individual / FitnessReport |
| `population.py` | Population / PopulationStats |
| `fitness.py` | Fitness 型 |
| `selection.py` | TournamentSelection / ElitismSelection (loop内部default) |
| `crossover.py` | UniformCrossover (loop内部default) |
| `mutation.py` | GaussianMutation / ChainedMutation (loop内部default) |
| `seeds.py` | call_fitness_with_seed / fitness_accepts_seed |
| `mating.py` | LexicaseSelection (lldarwin がコアで使用) |
| `loop.py` | EvolutionLoop / EvolutionConfig |
| `lineage.py` | winners.jsonl 書出し |

### lldarwin v2 選択核 (4 本)
| モジュール | 役割 |
|---|---|
| `diversity.py` | NoveltyScorer (novelty pressure) |
| `quality_diversity.py` | FactorSubspaceNovelty / MAPElitesGrid (QD archive) |
| `pressures.py` | AdaptivePercentileGate + factor_vector (適応難易度) |
| `lldarwin.py` | MultiPressureSelector / MinimalCriterionGate |
| `lldarwin_v2.py` | S1選択核プリセット build_lldarwin_v2_selector() |

### Genome3D + persona層 (7 本)
| モジュール | 役割 |
|---|---|
| `genome_3d.py` | Genome3D (多層ゲノム) |
| `genome_3d_operators.py` | Genome3DCrossover / Genome3DMutation |
| `prompt_chromosome.py` | c_prompt 層 |
| `thought_factor_per_layer.py` | c_factors 層 |
| `persona.py` | PERSONA_ONTOLOGY / get_persona |
| `llive_variant.py` | LIVE_VARIANT_GENOME_BOUNDS / LIVE_VARIANT_GENOME_LABELS |
| `persona_evolution.py` | turnkey driver (run_persona_evolution) |

### 補助コア (2 本、opt-in だが実質必須)
| モジュール | 役割 |
|---|---|
| `lineage_reservoir.py` | 中立貯蔵庫 (lineage_reservoir=True で活性化) |
| `genome_version.py` | Genome バージョン管理 (cma_es_diversity等が参照) |

---

## 3. frozen 候補リスト

「未配線かつ北極星に直結しない」モジュール。`experimental/` 等へ隔離可能 (可逆)。

### テスト依存が軽い (隔離コスト低: 優先候補)

| モジュール | テスト数 | 隔離コメント |
|---|---|---|
| `latent_reservoir.py` | 0 | import元なし。要件はあるが未配線。最優先隔離。 |
| `impl_chromosome.py` | 0 | __init__経由のみ。将来拡張用 skeleton。 |
| `meta_loop.py` | 0 | experiments/poc のみ。MetaEvolutionLoop は本体から未使用。 |
| `scheduler.py` | 0 | loop.py が内部 _serial_scheduler を使用。AsyncioScheduler等は未使用。 |
| `parallel_mutation.py` | 0 | test_duplication.py のみ。evaluate_parallel は本体未使用。 |
| `substrate_adapters.py` | 0 | cross_substrate内部型参照のみ。 |
| `mcp_substrate_adapter.py` | 0 | experiments/mcp_genome_poc のみ。 |
| `recursive_inference.py` | 0 | recursion_depth内部のみ。 |
| `frozen_registry.py` | 0 | frozen_gene経由のみ。 |
| `fitness_rich.py` | 0 | __init__のみ。rich multi-axis fitness は未使用。 |
| `fitness_ucb.py` | 0 | __init__のみ。UCB fitness factoryは本体未使用。 |
| `persona_extended.py` | 6 | __init__のみ。 |

### テスト依存が中程度 (隔離前にテスト移動が必要)

| モジュール | テスト数 | 隔離コメント |
|---|---|---|
| `speciation.py` | 12 | __init__のみ。SpeciationLayer は本体未使用。 |
| `nsga2.py` | 14 | __init__のみ。NSGA2Selection は novelty_laneとセットだが未配線。 |
| `peer_evaluation.py` | 14 | mating/coevolution_governance のみ。後者も未配線。 |
| `self_adaptive.py` | 14 | llive_variant_extras経由のみ。本体 loop には届かない。 |
| `meta_mutation.py` | 10 | llive_variant_extras経由のみ。 |
| `persona_survival.py` | 16 | persona_extended経由のみ。 |
| `persona_corpus_loader.py` | 19 | __init__のみ。PersonaCorpusLoader は未使用。 |
| `persona_import.py` | 26 | __init__のみ。PersonaImportAlgorithm は未使用。 |
| `real_pressures.py` | 9 | scripts のみ (run_persona_evolution_long / poc_orchestra)。Stage2後半実LLM。開発中。 |
| `island_model.py` | 17 | __init__のみ。 |
| `expert_council.py` | 20 | expert_evolution経由のみ。 |
| `expert_evolution.py` | 22 | persona_survival経由のみ。 |
| `coevolution_governance.py` | 28 | __init__のみ。skeleton stage。 |
| `cross_substrate.py` | 37 | substrate_adapters経由のみ。 |
| `recursion_depth.py` | 30 | __init__のみ。 |
| `meta_chromosome.py` | 29 | genome_3d + experiments/poc のみ。 |

### テスト依存が重い (隔離コスト大: 慎重)

| モジュール | テスト数 | 隔離コメント |
|---|---|---|
| `cma_es.py` | 63 | テスト豊富。scripts/evolve等では直接使われていない。隔離時はテスト移動必須。 |
| `duplication.py` | 43 | llive_variant_extras経由のみ。frozen_gene/parallel_mutationとセット。 |
| `frozen_gene.py` | 49 | cma_es_diversity経由のみ。 |
| `cma_es_diversity.py` | 21 | テスト + frozen_registry/frozen_gene使用。CMA-ES系ひとまとめ。 |
| `phylogeny.py` | 45 | experiments/phylogeny_svg_demo のみ使用。可視化特化。 |

---

## 4. 補助モジュール (frozen候補外・保留)

配線はスクリプトのみで本体 loop からは呼ばれないが、開発継続中のため隔離保留。

| モジュール | 理由 |
|---|---|
| `svg_render.py` | scripts/render_evolution_svg.py から利用。可視化ユーティリティとして有用。 |
| `fitness_llm.py` | scripts/run_persona_evolution_long.py + テスト群。Stage2実LLM評価の準備層。 |
| `llive_variant_extras.py` | subprocess_scheduler + self_adaptive + meta_strategy の補助。開発継続中。 |
| `subprocess_scheduler.py` | VariantSubprocessScheduler。llive_variant実行補助。 |
| `novelty_lane.py` | MultiObjectiveSelector/NoveltyDescriptor。novelty拡張のインターフェース層。 |

---

## 5. 分類サマリ

| カテゴリ | 本数 |
|---|---|
| **コア** (進化エンジン + lldarwin v2 が直接依存) | **24 本** |
| **補助** (scripts/開発継続中/周辺hook) | **5 本** |
| **frozen候補 (テスト軽: 優先隔離)** | **12 本** |
| **frozen候補 (テスト中程度: 要テスト移動)** | **16 本** |
| **frozen候補 (テスト重: 慎重)** | **5 本** |
| `__init__.py` (re-export集約) | 1 本 |
| **合計** | **63 本** (含 `__init__`) |

frozen 候補の合計: **33 本** (テスト軽12 + 中16 + 重5)

---

## 6. 主要な依存チェーン (コア実行経路)

```
run_persona_evolution (persona_evolution.py)
├── Genome / Genome3D / Individual / Population
├── EvolutionLoop (loop.py)
│   ├── selection: TournamentSelection (default) | MultiPressureSelector (lldarwin)
│   │   └── MultiPressureSelector (lldarwin.py)
│   │       ├── LexicaseSelection (mating.py)
│   │       ├── NoveltyScorer (diversity.py)
│   │       ├── FactorSubspaceNovelty (quality_diversity.py)
│   │       └── AdaptivePercentileGate (pressures.py)
│   ├── crossover: UniformCrossover | Genome3DCrossover
│   └── mutation: GaussianMutation + ChainedMutation | Genome3DMutation
├── LineageReservoir (lineage_reservoir.py) [lazy, opt-in]
├── MAPElitesGrid (quality_diversity.py) [lazy, opt-in]
└── write_winners_jsonl + lineage (lineage.py)

lldarwin_v2.py
└── build_lldarwin_v2_selector()
    ├── MultiPressureSelector (lldarwin.py)
    ├── AdaptivePercentileGate (pressures.py)
    └── FactorSubspaceNovelty (quality_diversity.py) [factor_subspace_qd=True]
```
