# llive 要件定義 v0.F — 2 階建てゲノム + Novelty Preservation

**Drafted:** 2026-05-22
**Status:** **要件登録 (構想)** — 実装は v0.E 完走後. v0.B (EvolutionLoop) / v0.C (subprocess 派生) / v0.D (self-adaptive meta-mutation) / v0.E (competitive coevolution) を継承する。
**Type:** Evolutionary architecture — genome structural extension + selection diversity
**Trigger:** ユーザー指摘 (2026-05-22):

> ゲノムに関しては、コーディングレベル (実装方法やアルゴリズムや並列実行や AGI やオーケストラや実装言語の違いも含む) とプロンプトレベルでの偉人の思想を取り込んだスキルやルールなども含めた構造になっていて、交配や突然変異が起こりやすい感じになっているといいでしょうね。あと、あまり多数決にこだわらずに独自進化の方向性があるものは生存しやすい環境を整えるのもありだと思います。

---

## 1. 背景 — v0.B〜v0.E ゲノムの現状と限界

| Phase | Genome 構造 | 染色体数 | 評価 |
|---|---|---|---|
| v0.B EV-01 | 19 dim scalar Genome (5 chromosome: hyperparam / cog_fx / mem / triz / loop) | 5 | scalar 限定 |
| v0.C | 同上 + subprocess 派生分離 | 5 | scalar 限定 |
| v0.D | self-adaptive σ + meta-mutation rate | 5 + meta | scalar 限定 |
| v0.E | + persona ontology / peer evaluation | 5 + meta + persona | 構造的だが「コード自体」「プロンプト自体」は触らない |

**限界 1**: ゲノムが「数値 + 列挙」のみ。実装方法・アルゴリズム選択・並列度・実装言語・オーケストレーション方式といった **構造的選択** が遺伝対象になっていない。「同じ実装方針を遺伝した個体集団」になり進化空間が狭い。

**限界 2**: プロンプト層 (思考因子の組合せ / 偉人ペルソナ / スキル選択) も列挙のみ。実際に呼び出すスキル text や偉人 prompt の組合せ自体が遺伝対象になっていない。

**限界 3**: 選択圧が fitness 単一目的に寄りがちで、Lehman & Stanley (2011) の "Abandoning Objectives" 系の **novelty search** が反映されていない。多数決的に top-N を残すと **局所最適 (fitness 高いが似た個体ばかり)** に陥り、Hillis Red Queen の効用も弱まる。

---

## 2. 設計柱

### 柱 A: 2 階建てゲノム (Two-Layer Genome)

ゲノムを「コード層染色体」と「プロンプト層染色体」の 2 層に拡張する。

#### A-1. コード層染色体 (`C-impl`)

実装的選択を遺伝対象とする:

| Gene | 値域 | 例 |
|---|---|---|
| `impl_language` | enum | python / rust / cython / typescript |
| `algorithm_family` | enum | greedy / genetic / mcts / bayesian / random-restart |
| `parallel_strategy` | enum | single / thread / process / asyncio / distributed |
| `agi_usage_ratio` | float [0,1] | 自律推論で AGI (LLM) に丸投げする比率 |
| `orchestration_mode` | enum | sequential / pipeline / pubsub / actor-model |
| `memory_backend` | enum | dict / sqlite / pickle / lmdb / redis |
| `selector_class` | enum | UCB1 / Thompson / EpsilonGreedy / SynapticSelector |
| `judge_model` | enum | self / peer / external / mixed |

#### A-2. プロンプト層染色体 (`C-prompt`)

偉人思想・スキル・ルールを遺伝対象とする:

| Gene | 値域 | 例 |
|---|---|---|
| `persona_set` | bitmask | { 岡潔, Polya, TRIZ, Six Hats, Bayesian, Feynman, 金子勇 } のサブセット |
| `skill_set` | bitmask | { structurize, recompose, loop, self_extend, uncertainty, explore, align, provenance, perspective, ground } |
| `rule_set` | bitmask | { fail_closed, honest_disclosure, no_local_path, ... } |
| `prompt_template_id` | enum | base / chain_of_thought / tree_of_thought / debate / socratic |
| `language_style` | enum | terse / verbose / formal / casual / academic |
| `historical_quote_density` | float [0,1] | persona 引用の密度 |

#### A-3. 交配・突然変異

- **層内 crossover (intra-layer)**: 同層内の遺伝子を mix (例: 親 A の `impl_language=rust` + 親 B の `parallel_strategy=asyncio`)
- **層間 crossover (cross-layer)**: 一方の親からコード層を、もう一方からプロンプト層を継承 (実装は新言語だが思想は古典系、など意外な組合せが生成される)
- **突然変異率**: 層別に独立
  - コード層 (`C-impl`): 低め (0.02〜0.05) — 実装が gradually shift する方が安定
  - プロンプト層 (`C-prompt`): 高め (0.10〜0.20) — 思想/persona 切替で表現力を確保
- **segment crossover** (v0.C 既存) を遺伝子レベルで拡張: 染色体内の gene segment を swap

### 柱 B: Novelty Preservation (独自進化保護)

多数決圧を抑え、「他個体と異なる方向性で進化する個体」を保護する。

#### B-1. 選択戦略の Multi-Objective 化

- `fitness_score`: 既存指標 (タスク性能)
- `novelty_score`: 他個体との振る舞い距離 (behavioral diversity)
  - 振る舞い記述子: (output text の embedding, 使用した persona set, 選択した algorithm_family, ...)
  - distance = k-NN 距離 (k=15 default) を population 内で計算
- selection は **(fitness top-N) + (novelty top-M)** のハイブリッド (N:M = 0.6:0.4 default)

#### B-2. 専用 Lane (Novelty Lane)

- novelty 高い個体は **dedicated subprocess lane** で評価
- CE-06 (共謀検出) や CE-10 (peer eval bias) が「異質個体は低評価」しがちなので、別 evaluator で評価して fitness と nov 別 metric を残す
- novelty lane の個体は通常 lane と **gene flow** (低頻度 migration) を行う — 完全分離ではない

#### B-3. 多数決抑制

- v0.E peer evaluation で「多数派評価」へ全個体が collapse しないよう、評価者 sampling で **同質個体の評価重複を下げる** (近傍 N 個 / 親個体 / 評価者は明示的に除外)
- ペナルティ: 評価が全体平均から大きく外れた評価者は immediate に無効化しない。novelty 評価者は独立 weight を持つ

### 柱 D: Similarity Quota — 類似個体の上限制 (Crowding / Niching)

ユーザー追加指摘 (2026-05-22):

> あまりに似すぎている個体は一定数を除き排除されるようなルールがあると進化の促進が進むかもしれません。

novelty preservation (柱 B) は「個別に独自進化を保護する」方向、本柱 D はその対になる「類似集中を解体する」方向。両者は補完関係。

#### D-1. Similarity Cluster Detection

- 全個体ペア間の **genome distance** + **behavioral distance** を計算
- 距離が閾値 `sim_threshold` 未満のペアを同一 cluster とみなす (Union-Find で連結成分化)
- 1 cluster 内の個体数を `cluster_size` とする

#### D-2. Quota Enforcement

- cluster ごとに上限 `cluster_quota` (default 4) を設定
- 上限超過時の処理:
  1. cluster 内を fitness 降順 sort
  2. 上位 `cluster_quota` 個体を残す
  3. 残り個体は **削除** または **強制突然変異** (確率 0.5 / 0.5)
- 削除は世代 step の selection 前に行い、空いたスロットを次世代生成枠として確保

#### D-3. Adaptive Threshold

- `sim_threshold` は固定でなく、世代経過に応じて **動的調整**:
  - 集団全体の avg pairwise distance が低い (集団が縮退) → threshold を上げて quota 強化
  - distance が高い (健全) → threshold を下げて quota 緩和
- 突然変異率 (柱 A-3) と連動: 類似が増えたら mutation rate も自動上昇

#### D-4. Novelty Lane との共存

- 柱 B Novelty Lane の個体は cluster_quota の **対象外** (絶滅候補にしない)
- 通常 lane のみに quota を適用 — novelty 候補が誤って淘汰されない設計

#### D-5. Honest Disclosure

- quota 適用ログ (どの cluster が何個体を削除したか / 強制突然変異したか) を ledger に記録
- v0.F EV-20 の 5+1 因子分解で「quota 効果 = 集団 entropy 向上量」を測定

### 柱 C: Genome Schema Versioning

- 既存 v0.B EV-01 の 19-dim Genome は **C-impl 部分集合** として保持 (互換)
- 新規 schema version `genome_v2` を導入し、`from_v1` / `to_v1` migration を提供
- evolution loop 内で **schema-version mixed population** を許可 (v1 個体と v2 個体が同居して交配可能、欠落 gene は default 値 + 突然変異で穴埋め)

---

## 3. 実装ロードマップ (要件のみ、実装は次フェーズ)

| ID | 内容 | 依存 |
|---|---|---|
| EV-13 | 2-layer Genome schema (`C-impl` / `C-prompt`) + v1↔v2 migration | v0.B EV-01 |
| EV-14 | Layer-aware crossover (intra/cross-layer) + per-layer mutation rate | EV-13 |
| EV-15 | Novelty score (behavior k-NN distance) | EV-13 |
| EV-16 | Multi-objective selection (fitness + novelty) | EV-15 |
| EV-17 | Novelty Lane (dedicated subprocess + gene migration) | EV-16, v0.C subprocess infra |
| EV-18 | Persona/Skill/Rule bitmask integration with COG-MESH | EV-13, COG-MESH-01..10 |
| EV-19 | A/B test: v0.E baseline vs v0.F two-layer + novelty | EV-13..18 |
| EV-20 | Honest disclosure metrics (5+1 因子 分解 over v0.F) | EV-19, lleval LE-01 |

---

## 4. 先行研究 / 参考

- **Lehman & Stanley (2011)** "Abandoning Objectives: Evolution Through the Search for Novelty Alone" — Novelty Search の理論的根拠
- **Hillis (1990)** — Red Queen effect, parasites による fitness 向上
- **Rosin & Belew (1997)** — competitive coevolution の理論整理
- **Mouret & Clune (2015)** — MAP-Elites (illumination over single best)
- **AlphaStar (2019)** — population-based training with diverse policies
- **Open-Ended Evolution (Soros 2017)** — genome schema 拡張による innovation 維持
- **田中 隆司 / TRIZ 系**: 矛盾マトリクスの遺伝子化 (既存 v0.3 TRIZ ChangeOp の延長)

---

## 5. リスクと honest disclosure

| リスク | 影響 | 対策 |
|---|---|---|
| 2-layer genome の探索空間爆発 | 収束遅延 | 突然変異率の per-layer 調整 + warm start from v0.E |
| novelty 評価の計算コスト (embedding distance) | run-time 増 | embedding cache + 近似 k-NN (HNSW) |
| プロンプト層遺伝で偉人引用が劣化コピーされる | 表面的な模倣 | persona ontology (CE-19) で正典文献に anchor |
| Novelty lane が degenerate 個体の温床に | 集団品質低下 | novelty floor (最低 fitness 閾値) を設定 |
| schema migration バグで v1 個体が壊れる | regression | v1↔v2 round-trip property test |

---

## 6. 連動 memory / docs

- `[[project_llive_genome_two_layer]]` — 本要件の memory side カウンタパート
- `[[project_llive_v0E_coevolution]]` — v0.E と本要件の接合
- `[[project_fullsense_ear_origin]]` — local 推論前提を維持 (cloud LLM 依存禁止)
- `requirements_v0.B_evolutionary_optimization.md` — 19-dim Genome の現状
- `requirements_v0.E_competitive_coevolution.md` — peer evaluation 設計

---

> Drafted by Claude (Opus 4.7) on 2026-05-22 in response to user feedback.
> 実装着手は v0.E EV-09 完走後 (現状 v0.E は 303 件 test + governance skeleton 着地済、EV-09 未着手)。
