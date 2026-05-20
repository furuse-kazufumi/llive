# llive 要件定義 v0.C — llive 派生集団進化

**Drafted:** 2026-05-21
**Status:** **要件追加** (v0.B の上に層を重ねる. 同セッションで skeleton 着手)
**Type:** Evolutionary architecture — variant-level (1 llive = 1 個体)
**Trigger:** ユーザー指示 (2026-05-21) —

> 「完全に同時でなくても, 多くのランダムな llive 派生を作って比較の上で取捨選択
> していく形を取りたい」

---

## 0. 動機

### v0.B (既存) との関係

| 層 | 何を進化させるか | Genome 次元 |
|---|---|---|
| **v0.B** | hyperparameter (UCB c / sampler / backend / etc) | 3-5 dim |
| **v0.C (本要件)** | **llive instance 全体の構成** (思考因子 weight / memory tier / backend / proactive 等) | **~19 dim** |

v0.C は **「1 llive = 1 個体」** と見て集団化する. v0.B が *「1 個体内の variant
選択」*, v0.C が *「個体集団全体の構造探索」*. **両層は直交補完**.

ROS 歩行進化との対応:

| 物理ロボット | llive v0.C |
|---|---|
| 1 体のロボット | 1 個の llive instance |
| 脚の長さ / モータ配置 / 重心 / 関節周期 / etc | 思考因子 weight / memory tier / backend / sampler / proactive 等 |
| 歩行距離 / 転倒回数 / 消費エネルギー | Brief 完遂率 / 思考深さ / 5 軸合成 (latency/quality/stability/safety/honesty) |
| 100 体並列に歩かせる | **serial / segmented で OK** (本要件の核心) |
| 上位 N 体を残す | TournamentSelection + Elitism |
| 子孫を作る | BlendCrossover + GaussianMutation |

### 「完全に同時でなくても」の意図

ユーザー指示の核心 — **並列 (multiprocessing) 必須ではない**.

- **1 体ずつ serial 評価** でも世代は進む.
- **segmented (5 体ずつ batch)** でも世代は進む.
- 重要なのは「**多数のランダム派生 → 比較 → 取捨選択 → 子孫**」のループが
  途切れないこと.
- 並列化は **後付けの最適化** であって, ロジックの前提ではない.

これにより:
- credential / GPU / 外部 binary が無くても **mock baseline で世代が回る**
- 派生間の干渉 (memory backend / data_dir / port 番号) を **serial で確実に
  隔離** できる
- 失敗派生があっても他派生への影響なし

---

## 1. Genome レイアウト (~19 dim, v0.1)

### LV-GEN-01: 思考因子 weight (10 dim)

llive の 10 思考因子 ([[user-cognitive-mesh-model]] 由来) の weight:

| index | 因子 | range |
|---|---|---|
| 0 | 構造化 | 0.0 - 1.0 |
| 1 | 再構成 | 0.0 - 1.0 |
| 2 | 閉ループ | 0.0 - 1.0 |
| 3 | 自己拡張 | 0.0 - 1.0 |
| 4 | 不確実性 | 0.0 - 1.0 |
| 5 | 探索 | 0.0 - 1.0 |
| 6 | 整合 | 0.0 - 1.0 |
| 7 | 来歴 | 0.0 - 1.0 |
| 8 | 多視点 | 0.0 - 1.0 |
| 9 | 現実接続 | 0.0 - 1.0 |

### LV-GEN-02: memory tier 設定 (3 dim)

| index | 項目 | range |
|---|---|---|
| 10 | semantic write threshold (surprise) | 0.1 - 0.9 |
| 11 | episodic write threshold | 0.1 - 0.9 |
| 12 | structural edge weight decay | 0.5 - 1.0 |

### LV-GEN-03: backend 選択 (1 dim)

| index | 項目 | range |
|---|---|---|
| 13 | backend_id (0=mock 1=openai 2=anthropic 3=mamba 4=rwkv) | 0.0 - 4.99 |

### LV-GEN-04: sampler config (3 dim)

| index | 項目 | range |
|---|---|---|
| 14 | temperature | 0.0 - 1.5 |
| 15 | top_p | 0.5 - 1.0 |
| 16 | kv_quant_id (0=f16 1=q8_0 2=q4_0) | 0.0 - 2.99 |

### LV-GEN-05: proactive speaker config (2 dim)

| index | 項目 | range |
|---|---|---|
| 17 | gift_value_threshold | 0.3 - 0.9 |
| 18 | cooldown_minutes | 5 - 120 |

合計 **19 dim**. 将来 LV-GEN-06+ で拡張可能.

---

## 2. 要件 (LV-FX 系列)

### LV-01 (must) — LlivVariantGenome + 19 dim bounds

- `LlivVariantGenome` を `llive.perf.evolutionary` パッケージ内に新設.
- 19 dim の `GenomeBounds` を export.
- labels (`THOUGHT_FACTOR_LABELS` 等) を tuple で同梱.

### LV-02 (must) — LlivVariantBuilder

- `LlivVariantBuilder` — Genome → 構成 dict (`LlivVariantConfig`) に変換.
- **実 llive instance は spawn しない** (Phase 1 は dict のみ).
- 構成 dict は将来 `LlivKernel(config=...)` で実 instance を作る入口になる.

### LV-03 (must) — mock variant fitness

- `mock_variant_fitness_factory(LlivVariantConfig) -> FitnessReport`.
- 5 軸 (latency/quality/stability/safety/honesty) + 構成固有の 3 軸
  (factor_coverage / memory_efficiency / proactive_balance) = **8 軸合成**.
- 実 llive 評価は将来 (Phase 2+, credential 復旧後).

### LV-04 (must) — Serial / Segmented Scheduler

- **default は SerialScheduler** (`scheduler.serial_scheduler`).
- `SegmentedScheduler(segment_size=5)` を新規実装 — 1 segment ずつ serial 評価.
  segment 間で `time.sleep(grace_sec)` を任意で挟める ([[feedback-quiet-hours]]
  との相性).
- 並列 (MultiprocessingScheduler) は **opt-in**.

### LV-05 (must) — 派生間の隔離

- 各派生は **ephemeral data_dir** で動かす (Phase 2 実装):
  - `LLIVE_DATA_DIR=/tmp/llive-variants/<individual_id>/`
  - memory backend は per-individual.
- Phase 1 mock では data_dir 文字列を Genome に紐付けるだけ (実 ファイル I/O
  なし).

### LV-06 (should) — Reporter 拡張

- 既存 `EvolutionLoop` の `_write_generation` をそのまま使用.
- 派生固有 metadata (`variant_id` / `data_dir` / `backend_name`) を
  `FitnessReport.breakdown` に必ず含める.

### LV-07 (should) — `feedback_benchmark_honest_disclosure` 整合

- 5 軸 + 構成固有 3 軸の **breakdown** を必ず記録.
- runtime_metadata 6 SHA ([[feedback-llamacpp-tracking]]) も必須同梱.
- 異常 score の派生は内訳分解して `notes` に記録 (8 因子分解).

### LV-08 (could) — Tournament 結果の永続化

- 各世代の上位 N 体 (top_n) の Genome + score を `out/<run>/winners.jsonl`
  に永続化. 世代を跨いで「歴代上位」を追跡できる.

### LV-09 (could) — Phase 2: 実 llive instance spawn

- `LlivVariantBuilder.build(config) -> LlivKernel` で実 instance を作る.
- subprocess 経由 / in-process の両 transport を提供.
- credential 不要環境で動く mock 経路は Phase 1 で確立済 (本要件).

### LV-10 (could) — 派生集団の系統樹可視化

- generation × individual_id のラインを `out/<run>/lineage.mmd` (Mermaid)
  で書き出し. 「どの派生が生き残ったか」が一目で分かる.

---

## 3. 非要件 (Out of scope, v0.C)

- **実 LLM 派生評価** — credential 復旧後の Phase 2.
- **Genome の 19 dim を超える拡張** — 必要が確認できてから.
- **派生 instance の GPU memory 配分最適化** — 低スペック PC primary なので別話.

---

## 4. 段階 (Phase 1 → 3)

| Phase | 内容 | 同セッション着手 ? |
|---|---|---|
| 1 | LlivVariantGenome + Builder + mock fitness + SerialScheduler + SegmentedScheduler + 単体 test | **本セッション** |
| 2 | 実 LlivKernel spawn (subprocess 経由) + ephemeral data_dir + 隔離 memory backend | credential / 環境準備後 |
| 3 | lleval 統合 + asciinema 録画 + LV-10 系統樹 | Phase 2 後 |

---

## 5. 既存資産との接続点

| 既存 | v0.C 接続 |
|---|---|
| v0.B `EvolutionLoop` | そのまま使う. `fitness_fn = mock_variant_fitness_factory(...)` |
| v0.B `Population` / `Selection` / `Crossover` / `Mutation` | そのまま使う |
| v0.A `runtime_metadata` | mock 評価でも 6 SHA を同梱 |
| `lleval.HonestDisclosureAnalyzer` | Phase 3 で派生 fitness の anomaly 検出に使う |
| COG-MESH 10 因子 | LV-GEN-01 の weight として GA で進化対象に |
| ProactiveSpeaker / GiftValueEstimator | LV-GEN-05 で進化対象に |
| MemoryWriteBlock / SurpriseGate | LV-GEN-02 で進化対象に |

---

## 6. リスク

| リスク | 影響 | 緩和 |
|---|---|---|
| 19 dim genome の探索空間が広すぎる | 収束が遅い | 初期集団を **strategic seeding** (各 dim mid + 一部 random) で開始する option |
| 派生間で memory backend が干渉 | 評価が嘘になる | per-individual data_dir, in-memory ephemeral mode |
| 5 軸 + 3 軸 = 8 軸合成 weight が偏る | 局所最適 | weight を Pareto front で複数候補 |
| 1 派生評価が遅い (実 llive 起動) | 世代が回らない | Phase 1 は mock 評価で確認, Phase 2 で in-process spawn |
| 「同時でない」運用で世代が進まないリスク | バックログ蓄積 | SegmentedScheduler で 1 segment ずつ確実に進める |

---

## 7. 関連

- `docs/requirements_v0.B_evolutionary_optimization.md` — v0.B 本体
- `docs/requirements_v0.A_external_runtime_tracking.md` — runtime metadata
- `docs/requirements_v0.8_cognitive_mesh.md` — COG-MESH 10 因子
- portal `docs/spec/lleval_v0_1_implementation_notes.md`
- maintainer memory:
  - [[user-cognitive-mesh-model]] (10 思考因子の起源)
  - [[project-llive-v0B-evolutionary]]
  - [[feedback-marathon-lessons]] (mock baseline 重要性)
  - [[feedback-benchmark-honest-disclosure]]
- 比喩元: ROS 歩行進化 (NEAT, ES, CMA-ES の 1 体ずつ評価でも世代が進む特性)
