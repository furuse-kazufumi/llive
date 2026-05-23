# SPEC Coherence Pre-Map — v0.J 起草前の矛盾防止分析

> **目的**: 新要件 doc v0.J (後学習 / reasoning operators first-class 化 /
> ゲノム多様性確保 / drift monitoring) を起草する **前** に、既存 18 要件 doc
> (220+ ID) との矛盾・重複・ID 衝突・dimensionality 不整合を洗い出す **読み取り専用**
> 分析 map。**本 doc は要件を書かない** — v0.J 起草 agent のガードレールを提供する。
>
> **Drafted:** 2026-05-23 (spec coherence 監査セッション)
> **Status:** 分析 map (premap)。実 file + file:line で全根拠を確認済み。
> **Scope:** v0.B/C/D/E/F/F-persona/I + `.planning/REQUIREMENTS.md` + 実装
> `src/llive/perf/evolutionary/` を横断確認。

---

## 0. エグゼクティブサマリ (最重要 3 点)

1. **dimensionality の真相 (19/38/40)**: 3 つは **食い違いではなく別物の重ね合わせ**。
   - **19-dim** = canonical flat scalar genome (`Genome` / `LIVE_VARIANT_GENOME_BOUNDS`、
     `assert len == 19`、5 segment)。**現行の唯一の "flat genome" canonical**。
   - **38-dim** = 19-dim object に **σ を同伴** (self-adaptive ES, SR-01)。
     ハードコード定数ではなく `pack_self_adaptive_bounds(bounds)` が返す `2n` 汎用表現
     (19 → 38)。**独立した genome ではなく 19-dim の派生 view**。
   - **40-dim** = 10 思考因子 × 4 メモリ層の **2D matrix** chromosome
     (`ThoughtFactorPerLayerChromosome`、今日着地)。`Genome3D.c_factors` として既に
     **field 統合済**。CMA-ES (`CMAESAdapter`) はこの 40-dim flatten を対象にする
     設計 (`cma_es.py:10,89`)。
   - → v0.J は **「4 つ目の次元数を黙って足さない」**。3 表現は別レイヤ。版管理は
     `GENOME_VERSION` 定数導入で明示する (§2)。

2. **提案 prefix 4 件 (全て未使用を grep 確認済)**: 後学習=**PT**、reasoning=**RSN**、
   diversity=**DIV**、drift=**DFT**。既存 53 prefix のいずれとも衝突しない (§3)。
   特に **`EV-XX` は使い回し禁止** — v0.B(EV-01〜11) / v0.F(EV-13〜20) / v0.I(EV-21〜40)
   で連番が EV-40 まで予約済。diversity を `EV-41` に足すと v0.I 拡張と将来衝突する。

3. **最大の破綻リスク**: **v0.J 「diversity」テーマと既存 v0.F 柱 B/D + v0.E CE-24〜34
   との二重定義**。Novelty Search / MAP-Elites / Speciation / NSGA-II / Lexicase /
   LHS init / DiversityMonitor は **doc 定義済 + 実装済**。v0.J で「多様性確保」を
   新規 redefine すると、同一概念が EV/CE/DIV の 3 系列で別 ID 化され spec が崩壊する。
   → v0.J diversity は **既存機構の extend のみ** (CMA-ES / GraphRAG を新 operator
   として add)、**redefine 禁止**。

---

## 1. 既存の多様性機構インベントリ (実装済み公開 API)

v0.J が **redefine してはいけない / extend のみ可** な既存資産。すべて
`src/llive/perf/evolutionary/` に着地済 (file:line + signature)。

| 機構 | class / function | file:line | 対応既存要件 |
|---|---|---|---|
| Novelty score (k-NN behavior 距離) | `NoveltyScorer` | `diversity.py:93` | v0.E CE-27, v0.F 柱 B-1 |
| Novelty descriptor + score | `NoveltyDescriptor` / `NoveltyScore` / `compute_novelty_scores()` | `novelty_lane.py:48,72,125` | v0.F EV-15/17 |
| 多目的 (fitness+novelty) 選択 | `MultiObjectiveSelector` | `novelty_lane.py:209` | v0.F EV-16, 柱 B |
| MAP-Elites grid (QD) | `MAPElitesGrid` / `MAPElitesCell` | `quality_diversity.py:156,138` | v0.E CE-26, v0.F |
| MAP-Elites feature 既定 | `default_persona_features` / `default_thought_features` / `default_map_elites_features` | `quality_diversity.py:347,365,385` | v0.E CE-26 |
| Persona overlap penalty | `PersonaOverlapPenalty` | `quality_diversity.py:58` | v0.E CE-25 |
| Speciation (NEAT 流) | `SpeciationLayer` / `Species` / `SpeciatedTournamentSelection` | `speciation.py:66,41,186` | v0.E CE-32 |
| NSGA-II Pareto | `non_dominated_sort()` / `crowding_distance()` / `NSGA2Selection` | `nsga2.py:70,146,192` | v0.E CE-31 |
| Selection 3 種 | `TournamentSelection` / `RouletteSelection` / `ElitismSelection` | `selection.py:19,37,63` | v0.B EV-03 |
| Lexicase / mutual-score mating | `LexicaseSelection` / `MutualScorePairSelector` | `mating.py:139,44` | v0.E CE-34/CE-30 |
| Self-adaptive σ mutation | `SelfAdaptiveGaussianMutation` / `pack_self_adaptive_bounds()` / `initial_sigma_values()` | `self_adaptive.py:48,142,182` | v0.D SR-01 |
| LHS 初期集団 | `latin_hypercube_population()` | `diversity.py:41` | v0.E CE-28 |
| Diversity reject + monitor | `DiversityPreservingBreedFilter` / `DiversityMetrics` / `DiversityMonitor` | `diversity.py:162,260,284` | v0.E CE-24/CE-29, v0.F 柱 D/E |
| Island migration | `island_model.py` (`IslandModel` 系) | `island_model.py` | v0.E CE-33 |

**境界明示**: v0.J「diversity」テーマは上記 13 機構を **新規 API で再実装しない**。
CMA-ES (`CMAESAdapter`, `cma_es.py:82`) と GraphRAG (`src/llive/memory/graph_rag/`
node/edge/store 実装済) を **既存 NoveltyScorer / MAPElitesGrid に接続する新 operator
として add する** のみ。

---

## 2. genome dimensionality 整合 (最重要)

### 2.1 実数の確認結果

| 表現 | 実数 | 実体 | file:line (実装) | doc 出典 |
|---|---|---|---|---|
| **flat scalar genome (canonical)** | **19-dim** | 思考因子10 + memtier3 + backend1 + sampler3 + proactive2 | `llive_variant.py:73` (`assert len(...)==19`) + `:108` 5 segment | v0.C §1 |
| **σ-augmented (self-adaptive)** | **38-dim** | 19 object + 19 σ。**汎用 `2n` 関数の結果** | `self_adaptive.py:142,169-171` (`2n dim`) | v0.D SR-01 |
| **思考因子 × 層 matrix** | **40-dim** | 10 因子 × 4 層 (`NUM_THOUGHT_FACTORS=10` × `NUM_MEMORY_LAYERS=4`) | `thought_factor_per_layer.py:79,86,98` | 2026-05-23 着地, v0.F 接続 |
| **3 階建て aggregate** | (構造) | `c_impl` + `c_prompt` + `c_meta` + `c_factors` | `genome_3d.py:70,88-98` | v0.F (2 層) → v0.I (3 層) |

### 2.2 なぜ食い違って見えるか (真相)

- **19 vs 38**: 38 は 19 の上に **σ を同伴した self-adaptive ES の作業表現**。
  `pack_self_adaptive_bounds` は任意 n を `2n` にする汎用関数で、38 は
  「19-dim を渡した時の結果」に過ぎない。**38-dim という固定 canonical は存在しない**。
  v0.D doc が「19 dim を 38 dim に拡張」と書いたのは object+σ の意味。
- **19 vs 40**: 完全に **別レイヤ**。19 は flat scalar (LlivVariantGenome の旧 path)、
  40 は 2D matrix chromosome (Genome3D の c_factors)。`thought_factor_per_layer.py`
  doc header (`:28-33`) が「Genome (19 dim) と Genome3D は別。本 module はその 4 つ目」
  と明記。**実装は doc より先行し、`Genome3D.c_factors` field に既に統合済**
  (`genome_3d.py:98`) — doc の「統合は別段階」記述は実装に追い越されている (注意)。
- **CMA-ES の対象**: `c_factors` の 40-dim flatten **のみ** (continuous 部分空間)。
  19-dim の離散 dim (backend_id / kv_quant_id) や bitmask (persona_set) は CMA-ES 対象外。

### 2.3 v0.J への整合提案 (黙って 4 つ目を足さない)

1. **`GENOME_VERSION` 定数を導入** (監査 doc §E-7 推奨の実行)。例:
   `GENOME_V1_FLAT = "v0.C-19"` / `GENOME_V3_LAYERED = "v0.I-3chrom"` /
   `GENOME_FACTORS = "v0.F-40"`。各表現に版タグを付け、混在集団を許す
   (v0.F 柱 C `genome_v2` migration と整合)。
2. **CMA-ES は `c_factors` 40-dim continuous サブ空間専用** と明記。
   離散 / bitmask dim は GA operator (既存 segment crossover / bitmask mutation) のまま。
3. **v0.J の §3 (diversity: CMA-ES/GraphRAG) は新 dim を導入しない**。
   既存 `c_factors` (40) と `c_prompt.persona_set` (bitmask) に対する operator 追加に留める。
4. **GraphRAG factor strength** は `src/llive/memory/graph_rag/` の既存 node/edge を
   `ThoughtFactorPerLayerChromosome` の層別 strength に写像する **bridge** として add
   (新 chromosome 化しない)。

---

## 3. ID prefix 衝突回避

### 3.1 既使用 prefix 全列挙 (grep 実確認、53 種)

```
AC BC BIZ CABT CE CONC CORE CREAT DB EP ER EV EVO FR GEN GROW HEALTH IND
INT LE LEG LG LLIVE LLW LV LX MATH MEM MESH MNG MR NFR NMG OBS OKA OPP ORG
PROC REP RTR RUST SEC SHA SPM SR SU TECH TRIZ VLM VRB
```
(CIFAR は EV-21 説明文中の dataset 名で要件 ID ではない)

連番が膨張し **再利用厳禁** の prefix:
- **EV**: v0.B(EV-01〜11) / v0.F(EV-13〜20) / v0.I(EV-21〜40)。**EV-41 以降は v0.I 拡張で予約とみなす**。
- **CE**: v0.E で CE-01〜34 まで連続使用済。
- **MEM / OBS / EVO / TRIZ / COG**: `.planning/REQUIREMENTS.md` の GSD 正典 ID。

### 3.2 v0.J 用 提案 prefix 4 件 (全て 0 hit を grep 確認)

| テーマ | 提案 prefix | grep 確認 | 採番例 |
|---|---|---|---|
| 後学習 (DPO/GRPO/ORPO/KTO/SimPO) | **PT** (Post-Training) | 0 hits (docs/.planning/src) | PT-01〜PT-NN |
| reasoning operators first-class 化 | **RSN** (ReaSoNing) | 0 hits | RSN-01〜 |
| ゲノム多様性確保 | **DIV** (DIVersity) | 0 hits | DIV-01〜 |
| drift monitoring | **DFT** (DriFT) | 0 hits | DFT-01〜 |

予備 (上記が将来衝突した場合): POST / REASON / DRIFT / QD も全て 0 hit。
**`GEN` は既使用** (LV-GEN-* と GEN-* 混在の恐れ) なので genome 系には使わないこと。

---

## 4. extends マッピング (矛盾チェック)

各テーマが **どの既存要件を extends するか** / **contradiction はないか**。

| v0.J テーマ | extends する既存 | 接続方法 (extend) | contradiction チェック |
|---|---|---|---|
| **後学習 (PT)** | v0.B EV-02 (Fitness 抽象) / v0.C LV-03 (mock variant fitness) / v0.E CE-01〜03 (peer fitness matrix) / v0.D SU-01 (LLM surrogate) | GRPO の group sampling = 既存 `Population` の variant 集団と shape 一致 → **新 reward path** として fitness 軸に add。peer matrix を reward signal に転用 | **NO contradiction**。ただし「on-prem only」(`feedback_llive_measurement_purity`) と「Approval Bus 経由」(v0.D LX-02 安全要件) を必須継承。実 RL 訓練は credential / GPU 待機 (v0.D Phase 同等扱い) |
| **reasoning operators (RSN)** | v0F-persona `CPromptChromosome.prompt_template_id` (`chain_of_thought`/`tree_of_thought`/`debate`/`socratic` 既存) / `RecursionDepthGene` (`recursion_depth.py:132`, `RefineStrategy` enum `:96`) | ToT/Reflexion/GoT/Self-Consistency を PromptChromosome の template **enum 拡張**で first-class 化。RecursionDepthGene を L2 adaptive scaling として **昇格** (既存 gene を再定義しない) | **重複定義リスク中**。`prompt_template_id` に既に tree_of_thought/debate がある → **新 enum 値追加で済む**。RecursionDepthGene 新規作成は **禁止** (実装済) |
| **diversity (DIV)** | §1 の 13 機構全部 (NoveltyScorer / MAPElitesGrid / SpeciationLayer / NSGA2 / DiversityMonitor 等) | CMA-ES (`CMAESAdapter`) を `c_factors` 40-dim の新 search operator として add。GraphRAG を factor strength bridge として add。既存 Novelty/MAP-Elites と **接続のみ** | **二重定義リスク最大** (§0-3)。v0.F 柱 B/D + v0.E CE-24〜34 が同概念。**redefine 厳禁、extend のみ** |
| **drift (DFT)** | `.planning` OBS-02 (forgetting/pollution/route_entropy metrics, 実装済) / v0.F 柱 E (eval 継続更新) / lleval HonestDisclosure (リポ外) | drift = honest disclosure の 6 番目軸候補。OBS metric 系列に **時系列 drift detector を add** | **境界判断要** (§5)。lleval 管轄 vs llive 管轄の切り分けが曖昧 |

### 4.1 drift の管轄境界判断 (重要)

- **HonestDisclosureAnalyzer は lleval 管轄** (llive リポ外。v0.C doc `:198` が
  `lleval.HonestDisclosureAnalyzer` と外部参照、`src/llive/lleval/` は存在しない)。
- **llive 内に置くべき drift**: 進化集団の **per-generation metric drift** =
  既存 `DiversityMonitor` (`diversity.py:284`) + OBS-02 metric の **時系列監視拡張**。
- **lleval に委ねるべき drift**: ベンチ評価指標自体の drift / honest disclosure の
  5+1 因子分解。v0.J DFT は **「llive 集団内 metric drift」に限定**し、評価指標の
  drift は lleval 連携 (v0.F 柱 E E-3) に委譲する境界を明記すること。

---

## 5. 破綻リスク箇所リスト

「ここを間違えると spec が壊れる」箇所。優先度順。

1. **【最大】diversity の二重定義** — v0.J DIV が v0.F 柱 B/D + v0.E CE-24〜34 +
   実装済 13 機構を再定義 → 同概念が 3 ID 系列に分裂。**必ず §1 表を参照し extend に限定**。
2. **dimensionality に 4 つ目を足す** — 19/38/40 を理解せず「v0.J で 50-dim に拡張」等を
   書くと canonical 崩壊。38 は派生 view、40 は別レイヤ。新 dim 導入は禁止 (§2)。
3. **EV prefix 再利用** — diversity を EV-41 等に採番すると v0.I EV-40 連番と衝突。DIV を使う。
4. **RecursionDepthGene / PromptChromosome template の再定義** — 実装済
   (`recursion_depth.py` / `prompt_chromosome.py`)。RSN は enum 値追加 / gene 昇格に限定。
5. **frozen ethics gene との干渉** — v0.I 案 D `FrozenGene` (`frozen_gene.py` /
   `frozen_registry.py` 実装済) は「外部送信 / Approval bypass / peer data 無断 read」を
   freeze。後学習 (PT) の reward path や reasoning (RSN) の自己改変が **frozen gene を
   mutate しないこと**を v0.J で明示。Approval Bus 経由を必須継承。
6. **backend interface 干渉** — v0.I cross-substrate (`cross_substrate.py` /
   `substrate_adapters.py` / `mcp_substrate_adapter.py` 実装済) + Mamba/RWKV backend。
   後学習が backend 固有 (GRPO は特定 runtime 前提) になると substrate 非依存と矛盾。
   PT は **backend-agnostic な reward path** として設計させる。
7. **on-prem 測定純度** — `feedback_llive_measurement_purity` (cloud LLM 混在禁止)。
   PT/RSN/DIV/DFT の評価 run は全て on-prem。cloud surrogate 混在を禁止。
8. **lleval / llive の eval 境界曖昧** (§4.1)。drift の置き場を誤ると責務が二重化。

---

## 6. v0.J 起草への推奨ガード (次 agent briefing 用)

1. **新 prefix は PT / RSN / DIV / DFT を使う**。EV / CE は再利用禁止 (連番衝突)。
   各 ID は `PT-01` 形式、採番開始は -01 から。
2. **dimensionality は 19/38/40 の 3 表現を尊重し、新 dim を足さない**。
   CMA-ES は `c_factors` 40-dim continuous 専用、`GENOME_VERSION` 定数で版管理を提案する。
3. **diversity (DIV) は §1 の実装済 13 機構を extend するのみ**。NoveltyScorer /
   MAPElitesGrid / SpeciationLayer 等を **再定義しない**。CMA-ES + GraphRAG を新 operator
   として接続する形で書く。
4. **reasoning (RSN) は PromptChromosome template enum 拡張 + RecursionDepthGene 昇格**。
   既存 gene/template を新規作成しない (実装済)。
5. **後学習 (PT) は既存 fitness/peer-matrix を reward path に転用**。GRPO group =
   既存 Population。実 RL 訓練は credential/GPU 待機扱い。backend-agnostic に書く。
6. **drift (DFT) は llive 集団内 metric drift に限定**。評価指標の drift / honest
   disclosure は lleval 管轄として委譲。`DiversityMonitor` + OBS-02 を extend。
7. **frozen ethics gene / Approval Bus / on-prem 純度を全テーマで必須継承**。
   PT の reward 自己改変・RSN の自己改変が frozen gene を mutate しないこと。
8. **実装が doc を追い越している箇所に注意** (`c_factors` は doc「統合は別段階」に
   反して `Genome3D` field 統合済)。v0.J は **実装現状を canonical** とし、doc 記述の
   古い部分を上書きする前提で書く。

---

## 関連

- 既存要件: `docs/requirements_v0.B〜v0.I*.md` + `docs/requirements_v0F_persona_prompt_resources.md`
- 監査俯瞰: `docs/REQUIREMENTS_AUDIT_2026-05-22.md` (§D-7 dimensionality 既知問題)
- GSD 正典: `.planning/REQUIREMENTS.md`
- 実装: `src/llive/perf/evolutionary/` (genome / cma_es / thought_factor_per_layer /
  diversity / novelty_lane / quality_diversity / speciation / nsga2 / self_adaptive /
  recursion_depth / frozen_gene / genome_3d) + `src/llive/memory/graph_rag/`
- 出典 taxonomy: `docs/algorithms_for_ai_development.md` (v0.J テーマの由来)
