# llive 要件定義 v0.F Addendum — Genome Diversity Operators (CMA-ES + GraphRAG factor-strength bridge)

**Drafted:** 2026-05-23 (genome multi-source diversity 選別セッション)
**Status:** **要件登録 (addendum)** — v0.F (genome two-layer + novelty) への追補。
**Type:** Diversity search-operator extension — 既存 13 多様性機構の **extend のみ**。
**Branch:** `optimize/core-2026-05-20`
**Prefix:** `DIV` (DIVersity, premap §3.2 で 0-hit 確認済)

> **本 addendum の位置づけ — 作業名 "v0.J" を畳む宣言**
>
> 当初 "v0.J" として後学習 (PT) / reasoning operators (RSN) / diversity (DIV) /
> drift (DFT) の 4 テーマを 1 つの新 top-level doc に起こす構想があった。
> しかし [[SPEC_COHERENCE_v0.J_premap]] の監査で **4 テーマのうち価値があり破綻
> リスクの無いのは DIV (多様性) のみ** と判明したため、**新 top-level doc を増やさず**
> 本 addendum (v0.F の追補) に DIV を畳む。PT は付録 note 1 段落、RSN/DFT は
> 「あえて採用しなかった候補」section に理由を残す。これにより doc 数膨張を防ぎ、
> diversity 概念が EV/CE/DIV の 3 系列に分裂する最大の破綻リスク (premap §0-3) を
> 「DIV は extend のみ」原則で封じる。
>
> **大原則: 網羅でなく選別。単なる模倣はせず、価値ある仕組みだけを既存資産に接続する。**

---

## 0. 選別結果サマリ (採用 / 削減 / 不採用)

| テーマ | prefix | 判定 | 形態 |
|---|---|---|---|
| 多様性 search operator (CMA-ES / GraphRAG) | **DIV** | **KEEP** | 本文要件 DIV-01〜03 (既存 13 機構の extend) |
| 後学習 (DPO/GRPO/ORPO) | (PT) | **TRIM** | 付録 note 1 段落のみ (要件化しない) |
| reasoning operators first-class 化 | (RSN) | **EXCLUDE** | 「あえて採用しなかった候補」に理由記載 |
| drift monitoring (llive 内) | (DFT) | **EXCLUDE** | 同上 (lleval 管轄 / 模倣性) |

選別の根拠は premap §4 (extends マッピング) と §5 (破綻リスク) に対応。
DIV を採る理由は「今日 skeleton 着地済の CMA-ES + GraphRAG が、既存の
NoveltyScorer / MAP-Elites / MultiObjectiveSelector に **接続できる実体**を
持ち、かつ GraphRAG factor-strength bridge は llive 独自 (4 層メモリ × factor 進化)
だから」。

---

## 1. 破綻防止ガード (premap §6 — 本 addendum 全 DIV 要件が継承)

本 addendum の全要件は以下を **無条件継承**する。違反は spec 破綻とみなす。

1. **新 prefix は `DIV` のみ。`EV` / `CE` の再利用禁止** (premap §3.1: EV-40 / CE-34 まで連番予約済)。
2. **dimensionality に 4 つ目を足さない**。19-dim flat (v0.C) / 38-dim σ-augmented 派生 view (v0.D SR-01) / 40-dim factor matrix (v0.F) の 3 表現を尊重。CMA-ES は **`c_factors` の 40-dim continuous サブ空間専用** (premap §2.3-2)。
3. **DIV は §1 premap の実装済 13 機構を extend のみ、redefine 厳禁** (premap §0-3, §5-1)。NoveltyScorer / MAPElitesGrid / SpeciationLayer 等を新 API で再実装しない。
4. **frozen ethics gene / Approval Bus / on-prem 測定純度 を必須継承** (premap §5-5,§5-7)。CMA-ES / GraphRAG operator は `FrozenGene` (`frozen_gene.py:109`) で freeze された gene を **mutate してはならない**。評価 run は cloud LLM 混在禁止 ([[feedback_llive_measurement_purity]])。
5. **実装が doc を追い越している箇所は実装現状を canonical とする** (premap §6-8)。`Genome3D.c_factors` は doc「統合は別段階」記述に反して field 統合済 (`genome_3d.py:98`) — 本 addendum は統合済を前提に書く。

---

## 2. DIV 要件本文

各要件は v0.I 書式 (ID + 1 行要約 + 形式化 or データ構造 + 既存 extend 点 + 実装着地状況) に合わせる。
**形式化は意味がある箇所のみ** 付す。

### DIV-01 — CMA-ES operator (c_factors 40-dim continuous 専用)

**1 行要約**: `CMAESAdapter` を `Genome3D.c_factors` の 40-dim continuous サブ空間
**専用**の新 search operator として、既存 NoveltyScorer / MAPElitesGrid /
MultiObjectiveSelector に接続する。離散 / bitmask dim は既存 GA operator のまま。

**部分空間定義 (形式化が意味を持つ箇所)**:

```
Genome3D = (c_impl, c_prompt, c_meta, c_factors)

c_factors ∈ ℝ^{10×4}, 各要素 ∈ [0,1]
  (ThoughtFactorPerLayerChromosome: NUM_THOUGHT_FACTORS=10 × NUM_MEMORY_LAYERS=4)

CMA-ES 対象部分空間 X_cma:
  x = c_factors.as_array().flatten()  ∈ ℝ^40   (thought_factor_per_layer.py:228)
  X_cma = [0,1]^40                              (continuous box)

CMA-ES 非対象 (既存 GA operator のまま):
  c_impl の backend_id / kv_quant_id (離散)
  c_prompt.persona_set                (bitmask)
  c_meta                              (meta chromosome)
  → これらに CMA-ES を適用しない (premap §2.2 / §2.3-2)

operator interface (duck-typing, cma_es.py):
  ask()                 -> np.ndarray (λ × 40)    候補サンプル生成 (cma_es.py:224)
  tell(xs, fitnesses)   -> None                   共分散行列 / step-size 更新 (cma_es.py:261)
  sample_neighborhood(x, n) -> ndarray            既存 mutation operator 互換 (cma_es.py:378)
  state_dict / load_state_dict                     checkpoint 互換 (cma_es.py:437,465)
```

**既存 extend 点**:
- `NoveltyScorer` (`diversity.py:93`) / `compute_novelty_scores()` (`novelty_lane.py:125`):
  CMA-ES の `ask()` 候補に対して novelty を計算し、`tell()` に渡す fitness を
  fitness+novelty 多目的に拡張 (`MultiObjectiveSelector` `novelty_lane.py:209` 経由)。
- `MAPElitesGrid` (`quality_diversity.py:156`): CMA-ES 候補を `default_thought_features`
  (`quality_diversity.py:365`) で behavior descriptor 化し grid に投入。CMA-ES は
  **既存 grid の cell を埋める search operator**であり、grid 自体を再定義しない。
- `SelfAdaptiveGaussianMutation` (`self_adaptive.py:48`) との違い: 後者は個体ごとの
  σ を進化させるが因子間相関なし。CMA-ES は集団レベルで共分散行列を学習し
  **因子間 / 層間相関**を捕捉する (cma_es.py header §既存実装との対比)。両者は併存し、
  operator selection で切替可能とする (DIV-03 の版管理と整合)。

**実装着地状況**: **skeleton 着地 (wiring 残)**。`CMAESAdapter` 本体 (μ_w, λ CMA-ES +
state_dict + sample_neighborhood adapter) は `cma_es.py` に着地済。EvolutionLoop /
NoveltyScorer / MAPElitesGrid への配線は **未実装** (BIPOP / restart / boundary
handling も skeleton 段階)。次フェーズ (Step 2) で wiring。

**ガード継承**: c_factors 40-dim 専用 (新 dim を足さない / §1-2)。`FrozenGene` で
freeze 対象に含まれる factor 要素があれば CMA-ES の `ask()` 出力をその index で
固定値に clip し mutate しない (§1-4)。

---

### DIV-02 — GraphRAG factor-strength bridge (llive 独自)

**1 行要約**: `src/llive/memory/graph_rag/` の Node / Edge / GraphRAGStore を
`ThoughtFactorPerLayerChromosome` の **層別 factor strength** に写像する **bridge**
として add する。新 chromosome は作らない。**4 層メモリ × factor 進化を結ぶ llive 独自の発想**。

**データ構造 (bridge 写像)**:

```
GraphRAG 側 (実装済, src/llive/memory/graph_rag/):
  Node(id, payload, embedding)                    node.py:39
  Edge(src, dst, relation, weight)                edge.py:45  (relation 例: derived_from / contradicts / generalizes)
  GraphRAGStore(alpha, hop_decay)                 store.py:55  (hybrid: cosine + graph proximity)

bridge 写像 factor_strength: (factor, layer) -> ℝ
  各 memory layer に属する Node 集合 N_layer を取り、
  thought-factor タグ (payload 内) ごとに edge weight を集約:
    s(f, L) = Σ_{e ∈ Edges(N_L), tag(e)=f} e.weight · hop_decay^{hop(e)}
  正規化して c_factors[f, L] への bias / prior として供給。

接続先 (既存 chromosome, 再定義しない):
  ThoughtFactorPerLayerChromosome.factor_weights  shape (10, 4), 各値 ∈ [0,1]
                                                  thought_factor_per_layer.py:99,115
  → bridge は factor_weights の初期化 prior / mutation bias を供給するのみ。
    chromosome の shape / 意味は不変 (40-dim を維持, §1-2)。
```

**既存 extend 点**:
- `ThoughtFactorPerLayerChromosome.from_array()` (`thought_factor_per_layer.py:171`):
  bridge が算出した strength prior を初期集団生成の bias として渡す (LHS init
  `latin_hypercube_population()` `diversity.py:41` と併用可)。
- `GraphRAGStore.neighbors()` (`store.py:103`): hop_decay ベースの proximity を
  factor strength 集約の重みに転用。新 retrieval API を足さない。

**独自性 (premap には無い llive 固有の発想)**: 既存の進化アルゴリズム文献は genome を
ベクトルとしてのみ扱うが、本 bridge は **4 層メモリの知識グラフ構造を factor 進化の
prior に直結**する。memory (記憶) と genome (進化) の層を結ぶこの写像は mainstream
GA / CMA-ES / NEAT のいずれにも存在しない llive 独自の構造。

**実装着地状況**: **skeleton 着地 (wiring 残)**。GraphRAG Node / Edge / GraphRAGStore
は実装済。`ThoughtFactorPerLayerChromosome` も実装済。両者を結ぶ `factor_strength`
bridge 関数は **未実装**。次フェーズ (Step 2) で bridge を add。

**ガード継承**: 新 chromosome 化しない / 40-dim を維持 (§1-2,§1-3)。bridge が読む
peer / memory data は Approval Bus / on-prem 純度の制約下 (§1-4)。frozen factor は
bridge の prior で上書きしない。

---

### DIV-03 — GENOME_VERSION 版管理 (新 dim を足さない版タグ)

**1 行要約**: 19-dim flat (v0.C) / 38-dim σ-augmented 派生 view (v0.D) /
40-dim factor matrix (v0.F) の 3 表現を `GENOME_VERSION` 定数で版タグ管理し、
混在集団を許す。**新 dim を一切足さない** — 既存 3 表現にラベルを付けるだけ。

**データ構造 (版タグ定数, 提案 — premap §2.3-1 の実行)**:

```python
# 提案する定数 (実装は Step 2)。新 dim は導入しない。
GENOME_V1_FLAT    = "v0.C-19"      # 19-dim flat scalar (canonical, llive_variant.py:73 assert==19)
GENOME_V2_SIGMA   = "v0.D-38-view" # 19-dim object + 19 σ の派生 view (self_adaptive.py:142, 2n)
GENOME_FACTORS    = "v0.F-40"      # 10×4 factor matrix (thought_factor_per_layer.py)
GENOME_VERSION    = GENOME_FACTORS # 現行 default

# 不変条件 (assertion で守る):
#   len(flat genome)        == 19   (既存 assert を canonical として保持)
#   pack_self_adaptive_bounds(19)   -> 38  (汎用 2n 関数の結果。固定 canonical ではない)
#   c_factors.flatten().size == 40
#   いずれの表現にも 4 つ目の独立 dim を追加しない (premap §5-2)
```

**既存 extend 点**:
- v0.F 柱 C `genome_v2` migration と整合: 版タグで混在集団 (旧 19-dim flat と
  新 40-dim factor) の世代交代を追跡し、CMA-ES (DIV-01) は `GENOME_FACTORS` タグの
  個体のみを対象とする operator dispatch 条件に使う。
- 38-dim は **独立 genome ではなく 19-dim の派生 view** (premap §2.2)。
  `GENOME_V2_SIGMA` は固定 canonical を意味せず「19 を渡した時の self-adaptive 表現」の
  タグ。これを doc に明記し、誤って「38-dim canonical」と再解釈する破綻を防ぐ。

**実装着地状況**: **未実装 (提案)**。`GENOME_VERSION` 定数は現状 grep 0-hit (premap §2.3)。
Step 2 で定数導入 + dispatch 配線。本 addendum では版タグ体系の **提案**に留め、
実装は次フェーズ。

**ガード継承**: 新 dim を足さない (§1-2) を体系として固定するのが本要件の主目的。

---

## 3. 「被り / 独自 / あえて不採用」比較表 (必須セクション)

mainstream 手法を llive でどう扱うかの分類。将来のアルゴリズム調査記事
([[project_ai_algorithms_taxonomy]] / `docs/algorithms_for_ai_development.md`) の素材を兼ねる。
分類軸: **被り(extend)** = 既存資産に接続 / **独自** = mainstream に無い llive 固有 /
**不採用** = 価値薄 or 破綻リスクで採らない。

| mainstream 手法 | llive での扱い | 被り(extend) / 独自 / 不採用 |
|---|---|---|
| CMA-ES (Hansen 2016) | `c_factors` 40-dim continuous 専用 operator として NoveltyScorer/MAP-Elites に接続 (DIV-01) | **被り(extend)** — 既存 SelfAdaptiveGaussianMutation の上位互換として add |
| Novelty Search (Lehman/Stanley) | `NoveltyScorer` (`diversity.py:93`) 実装済 | **被り(extend)** — 再定義せず CMA-ES の fitness 軸に流用 |
| MAP-Elites / QD (Mouret/Clune) | `MAPElitesGrid` (`quality_diversity.py:156`) 実装済 | **被り(extend)** — CMA-ES 候補を投入する grid として流用 |
| NSGA-II / Lexicase / Speciation | `nsga2.py` / `mating.py:139` / `speciation.py:66` 実装済 | **被り(extend)** — 既存選択器をそのまま使用 |
| GraphRAG (知識グラフ retrieval) | Node/Edge/Store を **4 層メモリ × factor strength** bridge に転用 (DIV-02) | **独自** — memory 構造を factor 進化 prior に直結する写像は mainstream GA に無い |
| 思考因子 × メモリ層 40-dim matrix | `ThoughtFactorPerLayerChromosome` (実装済) を genome 化 | **独自** — 10 思考因子 × 4 層の 2D matrix genome は llive 固有 |
| 派生集団進化 + peer fitness matrix | Population + peer fitness (`CE-01〜03`) が GRPO group reward と shape 一致 | **独自** — variant-eval ≈ GRPO 一致は llive 構造から自然に出る発見 (§4 付録) |
| GENOME_VERSION 版管理 | 3 表現に版タグを付け混在集団を許す (DIV-03) | **被り(extend)** — schema versioning の素直な適用 (新 dim は足さない) |
| 後学習 trainer (DPO/GRPO/ORPO) | 移植せず。reward path の構造一致のみ note (§4) | **不採用 (TRIM)** — backend 依存で cross-substrate 矛盾 / GPU・credential block / 模倣性 |
| reasoning operators (ToT/Reflexion enum 追加) | PromptChromosome に tree_of_thought/debate/socratic 既存 + RecursionDepthGene 実装済 | **不採用 (RSN)** — 実装済概念に mainstream ラベルを足すだけ = 低価値模倣 (§5) |
| 評価指標 drift monitoring | lleval 管轄 (リポ外)。llive 内 drift は責務二重化 | **不採用 (DFT)** — 標準 MLOps 監視の模倣で独自性薄 (§5) |

(11 行)

---

## 4. 付録 note — 後学習 (PT) の TRIM 判定 (1 段落)

llive の variant-eval (`Population` + peer fitness matrix, v0.E `CE-01〜03`) は、
GRPO (Group Relative Policy Optimization) の group reward と **shape が一致する**という
構造的発見がある。GRPO が「1 prompt から複数サンプルを引き、group 内相対 reward で
advantage を計算する」のに対し、llive は既に「1 lliv から複数 variant を派生させ、
peer fitness matrix で相対評価する」(premap §4: GRPO group = 既存 Population)。
ただし DPO / GRPO / ORPO trainer の **移植は要件化しない** — 理由: (a) backend 固有
runtime 前提で v0.I cross-substrate と矛盾 (premap §5-6)、(b) 実 RL 訓練は GPU /
credential block ([[feedback_llive_measurement_purity]])、(c) 既存 trainer の単純移植は
模倣性が高い。**将来 backend-agnostic な reward path として、peer fitness matrix を
reward signal に転用する余地は残す** (premap §4 PT 行) が、本フェーズではスコープ外。

---

## 5. あえて採用しなかった候補 (蒸し返し防止)

後で「これも入れよう」と再燃しないよう、不採用の理由を明記する。

### RSN — reasoning operators first-class 化 (不採用)

- **状況**: `CPromptChromosome.prompt_template_id` に `chain_of_thought` /
  `tree_of_thought` / `debate` / `socratic` が **既存** (v0F-persona)。
  `RecursionDepthGene` (`recursion_depth.py:132`) + `RefineStrategy` enum も実装済。
- **不採用理由**: ToT / Reflexion / GoT / Self-Consistency を enum 値として足すのは
  「**実装済概念に mainstream ラベルを貼るだけ**」であり、新たな能力を生まない低価値模倣。
  RecursionDepthGene を新規作成するのは premap §5-4 で明示禁止 (実装済の再定義になる)。
- **再燃時の対応**: もし将来 enum 追加が必要になっても、それは v0F-persona doc の
  既存 `prompt_template_id` への **enum 値追加** (新 prefix 不要) として扱い、
  独立要件 (RSN-xx) は起こさない。

### DFT — drift monitoring (不採用)

- **状況**: 評価指標 drift は **lleval 管轄** (llive リポ外、`src/llive/lleval/` は不在、
  v0.C doc `:198` が `lleval.HonestDisclosureAnalyzer` を外部参照)。llive 内には
  既に `DiversityMonitor` (`diversity.py:284`) + OBS-02 metric が存在。
- **不採用理由**: llive 内に汎用 drift detector を足すと (a) 標準 MLOps 監視の模倣で
  独自性が薄く、(b) lleval との責務二重化を招く (premap §4.1 / §5-8)。
- **境界の明記**: llive 集団内の per-generation metric drift が必要になった場合は
  `DiversityMonitor` の時系列拡張として扱い、評価指標自体の drift / honest disclosure
  5+1 因子分解は **lleval (v0.F 柱 E E-3) に委譲**する。新 prefix DFT は起こさない。

---

## 6. spec 破綻リスク自己評価

本 addendum は (a) 新 prefix を `DIV` のみに限定し EV/CE 連番衝突を回避、
(b) 19/38/40 の 3 表現を尊重し 4 つ目の dim を導入せず CMA-ES を c_factors 40-dim
専用に閉じ込め、(c) DIV-01/02 を既存 13 機構の extend に限定 (redefine 無し)、
(d) frozen gene / Approval Bus / on-prem 純度を全要件に継承させたため、
premap §5 が挙げる 8 破綻リスクのいずれも残さない。**残存リスクなし**。

---

## 関連

- pre-map (起草ガード): `docs/SPEC_COHERENCE_v0.J_premap.md`
- 親 doc: `docs/requirements_v0.F_genome_two_layer_and_novelty.md` / `docs/requirements_v0F_persona_prompt_resources.md`
- 関連要件: `docs/requirements_v0.I_meta_evolution_and_cross_substrate.md` (frozen gene / cross-substrate)
- 出典 taxonomy: `docs/algorithms_for_ai_development.md`
- 実装: `src/llive/perf/evolutionary/` (cma_es / thought_factor_per_layer / genome_3d /
  diversity / novelty_lane / quality_diversity / self_adaptive / frozen_gene) +
  `src/llive/memory/graph_rag/` (node / edge / store)
- memory: [[project_llive_genome_two_layer]] / [[project_llive_thought_factor_per_layer]] /
  [[feedback_llive_measurement_purity]] / [[project_ai_algorithms_taxonomy]]
