# Requirements: llive

**Defined:** 2026-05-13
**Core Value:** コア重みを再学習せず、新しい能力を安全に追加し続けられる LLM 基盤

> このファイルは `.planning/PROJECT.md` の Requirements セクションを **REQ-ID 化** + **トレーサビリティ**付きで整理したもの。
> 詳細な FR-XX 仕様は `docs/requirements_v0.[1234]*.md` を参照（こちらは GSD ワークフロー用の編成）。
> v0.4 で **LLM Wiki パターン (Karpathy 2026-04)** との対応関係を整理し、LLW-01〜08 を追加。

## v1 Requirements (Phase 1 MVR スコープ)

### Core Model

- [ ] **CORE-01**: HuggingFace 系 Decoder-only LLM を `BaseModelAdapter` でロードして `generate(prompt)` できる (FR-01)
- [ ] **CORE-02**: tokenizer / context length / precision / device map の差異を抽象 I/F で吸収できる (FR-01)

### Block Container

- [ ] **BC-01**: ContainerSpec YAML を読み込んで sub-block を順序実行できる (FR-02)
- [ ] **BC-02**: 5 種類以上の sub-block (`pre_norm`, `causal_attention` or `grouped_query_attention`, `memory_read`, `ffn_swiglu`, `memory_write`) が `SubBlockRegistry` から動的ロードできる (FR-03)
- [ ] **BC-03**: ContainerSpec / SubBlockSpec / CandidateDiff の JSON Schema 検証 (Draft 2020-12) を pass する (FR-02, FR-03, FR-07)

### Memory

- [ ] **MEM-01**: Semantic memory (vector search backend) で `write(content, embedding)` と `query(text, top_k)` が動く (FR-05)
- [ ] **MEM-02**: Episodic memory (時系列 append-only) で `write(event)` と `query(time_range)` が動く (FR-05)
- [ ] **MEM-03**: 全 memory write に `provenance` (source_type / source_id / signed_by / signature / derived_from / confidence) を必須付与する (FR-06)
- [ ] **MEM-04**: surprise-gated write が動作する（θ 閾値で write or skip） (FR-06)

### Router

- [ ] **RTR-01**: rule-based router で 2 経路以上の `BlockContainer` 選択ができる (FR-04)
- [ ] **RTR-02**: router の判断理由を explanation log (JSON) として出力する (FR-04)

### Evolution

- [ ] **EVO-01**: CandidateDiff YAML を読み込んで baseline → candidate の A/B ベンチ評価が走る (FR-07)
- [ ] **EVO-02**: ChangeOp (`insert_subblock` / `replace_subblock` / `remove_subblock` / `reorder_subblocks`) の apply / invert が機械的に動作する (FR-07)

### Observability

- [ ] **OBS-01**: route trace と memory link を構造化 JSON で出力できる (FR-09, FR-10)
- [ ] **OBS-02**: forgetting / pollution / latency / route_entropy / dead_block_rate の基本メトリクスを取得できる (FR-08)

### TRIZ リソース整備

- [ ] **TRIZ-01**: 40 原理 + 39×39 マトリクス + 39+11 特性 を `specs/resources/` から読み込んで内蔵リソース化できる (FR-24)

## v2 Requirements (Phase 2 — Adaptive Modular System)

### Memory 拡張

- [ ] **MEM-05**: Structural memory (graph backend, Kùzu / Neo4j) で `MemoryNode` + `MemoryEdge` 操作 (FR-05)
- [ ] **MEM-06**: Parameter memory (adapter store) で AdapterProfile の管理 (FR-05)
- [ ] **MEM-07**: surprise score を Bayesian (mean + variance) として扱う (FR-21)
- [ ] **MEM-08**: episodic → semantic への consolidation サイクル (FR-12)
- [ ] **MEM-09**: episodic → semantic → archive → erase の phase transition (FR-16)

### Block Container 拡張

- [ ] **BC-04**: `adapter` / `lora_switch` sub-block の動作 (FR-03, FR-18)
- [ ] **BC-05**: nested_container (条件付き入れ子) の対応 (FR-02)

### llove HITL 最小

- [ ] **OBS-03**: llove TUI で route trace と memory link viz を表示 (FR-10, llove F11/F15 連携)
- [ ] **OBS-04**: forgetting score (BWT) のリアルタイム表示

## v3 Requirements (Phase 3 — Controlled Self-Evolution)

### Evolution 自動化

- [ ] **EVO-03**: AI による candidate diff の自動生成 (FR-07, EP-04: llm_generated / template / population)
- [ ] **EVO-04**: Static Verifier (Lean / Z3 / TLA+) で candidate の構造的不変量検証 (FR-13)
- [ ] **EVO-05**: Multi-precision shadow evaluation (INT8 / 4bit) (FR-14)
- [ ] **EVO-06**: Failed-Candidate Reservoir への保存と mutation policy 学習 (FR-15)
- [ ] **EVO-07**: Reverse-Evolution Monitor で forgetting 悪化方向を自動 rollback (FR-22)
- [ ] **EVO-08**: Population-based search による多目的 Pareto 探索 (EP-04)

### TRIZ 内蔵

- [ ] **TRIZ-02**: Contradiction Detector がメトリクスから矛盾ペアを自動抽出 (FR-23)
- [ ] **TRIZ-03**: TRIZ Principle Mapper が矛盾 → 40 原理を引ける (FR-24)
- [ ] **TRIZ-04**: RAD-Backed Idea Generator が CandidateDiff を生成 (FR-25)
- [ ] **TRIZ-05**: 9-Window System Operator が時間軸 × 階層軸の発想を生成 (FR-26)
- [ ] **TRIZ-06**: ARIZ Pipeline が 9 ステップを自動実行 (FR-27)
- [ ] **TRIZ-07**: Self-Reflection モード (定期 cron で自走) が動作

## v4 Requirements (Phase 4 — Multimodal / Production PoC)

### Security

- [ ] **SEC-01**: Quarantined Memory Zone の cross-zone read で署名検証必須 (FR-17)
- [ ] **SEC-02**: Signed Adapter Marketplace (Ed25519 + SBOM CycloneDX) (FR-18)
- [ ] **SEC-03**: 監査ログを append-only sqlite + SHA-256 chain で保持
- [ ] **SEC-04**: mTLS / OIDC による外部接続 auth

### llmesh / llove 統合

- [ ] **INT-01**: llmesh sensor stream (MQTT / OPC-UA) を episodic memory に直接書込 (FR-19)
- [ ] **INT-02**: llmesh の MTEngine / XbarRChart / CUSUM で memory access SPC モニタ
- [ ] **INT-03**: llove F16 マルチゲームアリーナで candidate vs candidate 継続学習対局 (FR-20)
- [ ] **INT-04**: llmesh-suite メタパッケージへ `llmesh-llive` を追加

### Production

- [ ] **EVO-09**: 30 日連続稼働 + 人手介入ゼロ + forgetting 悪化ゼロ
- [ ] **EVO-10**: HITL UI で日 50 件 candidate を捌ける UX

## v0.4 Requirements (LLM Wiki integration — Phase 2〜4 に分配実装)

詳細は `docs/requirements_v0.4_llm_wiki.md` を参照。Karpathy の LLM Wiki パターン (2026-04) と llive memory fabric の構造的同型を活用し、設計の説明可能性と外向き位置づけを強化する。

### Wiki Page 構造化 (Phase 2)

- [ ] **LLW-01**: ConceptPage を第一級表現として導入 (concept_id / title / summary / linked_entries / linked_concepts / provenance / schema_version)
- [ ] **LLW-02**: Hippocampal Consolidation Scheduler を Wiki Compiler として再定義 (FR-12 拡張)
- [ ] **LLW-03**: ConceptPage の page_type 別 JSON Schema (`specs/wiki_schemas/`)
- [ ] **LLW-06**: 外部生ソース ingest CLI (`llive wiki ingest`)

### Wiki 矛盾検出と履歴 (Phase 3)

- [ ] **LLW-04**: Contradiction Detector が ConceptPage 内容からも矛盾抽出 (FR-23 拡張)
- [ ] **LLW-05**: Wiki diff (add_concept / merge / split) を ChangeOp に追加 (EVO-02 拡張)

### Wiki UI と RAG 連携 (Phase 4)

- [ ] **LLW-07**: llove TUI で ConceptPage 閲覧 + グラフ viz + HITL 編集 (OBS-03 拡張)
- [ ] **LLW-08**: RAG (memory_read) が Wiki 層を優先 query、概念単位で context 返す

## v0.7 Requirements (Rust acceleration — Phase 5 以降に分配実装)

詳細は `docs/requirements_v0.7_rust_acceleration.md` を参照。早期最適化禁止、Phase 5 で意味論凍結後に PyO3 経由でドロップイン置換。

### Native extension 基盤 (Phase 5)

- [ ] **RUST-01**: PyO3 + maturin による Rust extension skeleton + 自動 fallback
- [ ] **RUST-12**: GitHub Actions による wheel cross-build (Linux/macOS/Windows、x86_64/arm64)
- [ ] **RUST-13**: Rust ⇄ Python parity test (Hypothesis + proptest、bit-exact < 1e-6)
- [ ] **RUST-14**: pytest-benchmark + criterion による退行検出ハーネス (5× ゲート)

### Numeric / memory hotspot (Phase 5)

- [ ] **RUST-02**: Bayesian surprise kernel (rust-numpy + ndarray + rayon、5ms 目標 / 100k 行)
- [ ] **RUST-03**: Edge weight bulk decay (rayon 並列 + Kùzu bulk transaction、目標 8s → 600ms)
- [ ] **RUST-04**: Jaccard / cosine kernel library (set-of-ids u32 化、10-30× 高速)
- [ ] **RUST-05**: jsonschema-rs によるバリデータ差し替え (10-50× 高速)
- [ ] **RUST-06**: JSONL audit sink (crossbeam-channel + writer-thread、GIL 解放)
- [ ] **RUST-10**: TRIZ matrix lookup を phf で静的化 (起動時 0ms)

### Formal verification 接合 (Phase 6)

- [ ] **RUST-07**: ChangeOp engine の Rust 移植 (Z3 verifier との統合、proptest parity 100k 件)
- [ ] **RUST-11**: Z3 SMT bridge (`z3.rs` ラッパー、Static Verifier の本格運用基盤)
- [ ] **RUST-08**: ANN backend (hora / arroy) を optional 化、Faiss-CPU 依存緩和

### Concurrency reimagined (Phase 7)

- [ ] **RUST-09**: tokio + pyo3-async-runtimes による Concurrent Pipeline 再実装

## Out of Scope

| Feature | Reason |
|---|---|
| 基盤モデル本体の大規模事前学習 | 既存 LLM 利用前提、コア再学習はやらない |
| 大規模 GPU クラスタスケジューラ独自開発 | llmesh + 外部 (k8s / Ray) で代替 |
| 完全自律 (HITL なし) の本番構造変更 | promote は必ず HITL or 形式検証 gate 経由 |
| マルチモーダル LLM 自前学習 | encoder bridge で外部モデル接続のみ |
| Mobile / Web UI 単独実装 | llove TUI で代替、別 UI は v2+ 検討 |
| 単一 LLM の deep fine-tune 自動化 | アダプタ + 外部記憶で吸収する設計に集約 |

## Traceability

| Requirement | Phase | Status |
|---|---|---|
| CORE-01 | Phase 1 | Validated (Phase 1) |
| CORE-02 | Phase 1 | Validated (Phase 1) |
| BC-01 | Phase 1 | Validated (Phase 1) |
| BC-02 | Phase 1 | Validated (Phase 1) |
| BC-03 | Phase 1 | Validated (Phase 1) |
| MEM-01 | Phase 1 | Validated (Phase 1) |
| MEM-02 | Phase 1 | Validated (Phase 1) |
| MEM-03 | Phase 1 | Validated (Phase 1) |
| MEM-04 | Phase 1 | Validated (Phase 1) |
| RTR-01 | Phase 1 | Validated (Phase 1) |
| RTR-02 | Phase 1 | Validated (Phase 1) |
| EVO-01 | Phase 1 | Validated (Phase 1) |
| EVO-02 | Phase 1 | Validated (Phase 1) |
| OBS-01 | Phase 1 | Validated (Phase 1) |
| OBS-02 | Phase 1 | Validated (Phase 1) |
| TRIZ-01 | Phase 1 | Validated (Phase 1) |
| MEM-05 | Phase 2 | Pending |
| MEM-06 | Phase 2 | Pending |
| MEM-07 | Phase 2 | Pending |
| MEM-08 | Phase 2 | Pending |
| MEM-09 | Phase 2 | Pending |
| BC-04 | Phase 2 | Pending |
| BC-05 | Phase 2 | Pending |
| OBS-03 | Phase 2 | Pending |
| OBS-04 | Phase 2 | Pending |
| EVO-03 | Phase 3 | Pending |
| EVO-04 | Phase 3 | Pending |
| EVO-05 | Phase 3 | Pending |
| EVO-06 | Phase 3 | Pending |
| EVO-07 | Phase 3 | Pending |
| EVO-08 | Phase 3 | Pending |
| TRIZ-02 | Phase 3 | Pending |
| TRIZ-03 | Phase 3 | Pending |
| TRIZ-04 | Phase 3 | Pending |
| TRIZ-05 | Phase 3 | Pending |
| TRIZ-06 | Phase 3 | Pending |
| TRIZ-07 | Phase 3 | Pending |
| SEC-01 | Phase 4 | Pending |
| SEC-02 | Phase 4 | Pending |
| SEC-03 | Phase 4 | Pending |
| SEC-04 | Phase 4 | Pending |
| INT-01 | Phase 4 | Pending |
| INT-02 | Phase 4 | Pending |
| INT-03 | Phase 4 | Pending |
| INT-04 | Phase 4 | Pending |
| EVO-09 | Phase 4 | Pending |
| EVO-10 | Phase 4 | Pending |
| LLW-01 | Phase 2 | Pending |
| LLW-02 | Phase 2 | Pending |
| LLW-03 | Phase 2 | Pending |
| LLW-06 | Phase 2 | Pending |
| LLW-04 | Phase 3 | Pending |
| LLW-05 | Phase 3 | Pending |
| LLW-07 | Phase 4 | Pending |
| LLW-08 | Phase 4 | Pending |
| RUST-01 | Phase 5 | Pending |
| RUST-02 | Phase 5 | Pending |
| RUST-03 | Phase 5 | Pending |
| RUST-04 | Phase 5 | Pending |
| RUST-05 | Phase 5 | Pending |
| RUST-06 | Phase 5 | Pending |
| RUST-10 | Phase 5 | Pending |
| RUST-12 | Phase 5 | Pending |
| RUST-13 | Phase 5 | Pending |
| RUST-14 | Phase 5 | Pending |
| RUST-07 | Phase 6 | Pending |
| RUST-08 | Phase 6 | Pending |
| RUST-11 | Phase 6 | Pending |
| RUST-09 | Phase 7 | Pending |

**Coverage:**
- v1 (Phase 1) requirements: 16 total ✅ Validated (Phase 1)
- v2 (Phase 2) requirements: 9 + 4 LLW = 13 total
- v3 (Phase 3) requirements: 12 + 2 LLW = 14 total
- v4 (Phase 4) requirements: 9 + 2 LLW = 11 total
- v0.7 (Phase 5-7) Rust acceleration: 14 total (10 P5 + 3 P6 + 1 P7)
- v0.8 (Phase 8) Cognitive-aware Transformer Block (CABT): 7 total (CABT-01〜07)
- Mapped to phases: 75 / 75 ✓

---

## v0.8 — Cognitive-aware Transformer Block (CABT) 群 (2026-05-17 追加)

**動機:** LLMBackend を素の OSS LLM 依存にせず、llive の FullSense 6-stage
loop と親和性の高い「思考層対応 Transformer ブロック」を内製化する。スパイ
ラル開発で各 FR を「最小試作 → Brief API 経由で評価 → 次イテレーション」
のサイクルで回す。

### 関連設計パターン

- **Mediator** (TRIZ 原理 24) — Attention は値を直接混ぜず、参照ポインタを介す
- **Bridge** (GoF) — token-id (abstraction) と data + metadata (implementation) の分離
- **Provenance** (DDD) — 各データに source / confidence / timestamp / trust_score を付随
- **Strategy** (GoF) — Stage ごとに異なる block 構成を切り替え可能

### 要件詳細

| FR | 名前 | 概要 | 親和層 | RAD 裏付け候補 |
|---|---|---|---|---|
| CABT-01 | **Reference-based Attention with Metadata** | 値で並べ替えていた箇所を参照 (id ポインタ) ベースに置換。並べ替え対象データに metadata (provenance / trust / epistemic_type / timestamp / source domain) を貼り付け、attention は参照を選択した後に metadata を集約 | KAR / Provenance | pointer_networks / memorizing_transformers / retrieval_augmented |
| CABT-02 | **Stage-aware Block Routing** | FullSense 6 stage (salience / curiosity / thought / ego/altruism / plan / output) ごとに異なる block 構成を活性化 (Strategy + Soft-MoE 風 routing) | Loop / APO | mixture_of_experts / soft_moe / mixture_of_depths |
| CABT-03 | **Epistemic-typed Token Pool** | 各 token に `EpistemicType` (FACTUAL / EMPIRICAL / NORMATIVE / INTERPRETIVE / PRAGMATIC / RESERVED_*) を付与し、同 type 優先 attention bias を加える (Multi-track Filter Architecture A-1.5 の token 化) | DTKR / Filter Track | dialogue_filter / multi_track_reasoning |
| CABT-04 | **Salience-gated Attention** | Token-level surprise score (FR-21 と連携) で attention 強度を変える。surprise 低い token は MLP のみ通過、高い token は full attention に | APO / FR-21 | bayesian_surprise / hippocampal_consolidation / sparse_attention |
| CABT-05 | **TRIZ-conditioned Head Selection** | Brief で検出された TRIZ 原理 (BriefGrounder の triz citation) に応じて attention head の一部を bias / mask | TRIZ / FR-25 | head_pruning / triz_principles |
| CABT-06 | **Approval-gated Decoding** | 出力 token sequence を Approval Bus が検査。policy 違反候補は generation 段階で reject (post-attention の前段ゲート) | Approval Bus / SIL | constitutional_ai / decoding_constraints |
| CABT-07 | **Memory-augmented Residual** | 各層 residual path に 4 層メモリ (semantic / episodic / structural / parameter) の埋め込みを加算。surprise gate で 4 層別の write 経路と双対化 | MEM / FR-12〜16 | memorizing_transformers / retro / longmem |

### スパイラル開発のイテレーション計画

| Iter | スコープ | 評価 | リスク |
|---|---|---|---|
| **S1** | BriefGrounder (L1 grounding 層, 2026-05-17 実装) — Reference-based の「外側」原型 | Brief API ledger の citation 完全性 | 低 (CPU only, 既存) |
| **S2** | CABT-01 prototype — HF transformers forward hook で attention に metadata column を注入 | Brief × {grounded, ungrounded} 比較ベンチ | 中 (HF 内部依存) |
| **S3** | CABT-03 + CABT-04 — EpistemicType embedding + Salience gate を hook で追加 | A/B with token-level surprise log | 中 (学習が必要なら LoRA) |
| **S4** | CABT-02 — Stage-aware routing 試作。Soft-MoE 風の lightweight gate | per-stage benchmark | 高 (アーキ変更幅大) |
| **S5** | CABT-05 + CABT-06 — TRIZ-conditioned head + Approval-gated decoding | safety bench (RPAR) | 高 (Approval Bus 性能影響) |
| **S6** | CABT-07 統合 — 4 層メモリ residual fusion | full progressive matrix (xs〜xl × 3 models × {plain, CABT}) | 高 (品質測定が困難) |

### CABT 要件のフェーズマッピング

| FR | Phase | Status |
|---|---|---|
| CABT-01 | Phase 8 | Pending |
| CABT-02 | Phase 8 | Pending |
| CABT-03 | Phase 8 | Pending |
| CABT-04 | Phase 8 | Pending |
| CABT-05 | Phase 8 | Pending |
| CABT-06 | Phase 8 | Pending |
| CABT-07 | Phase 8 | Pending |

---

## v0.9 — Creative Thinking Layer (CREAT) 群 (2026-05-17 追加)

**動機:** ユーザー観察「人間の思考の流れは KJ法 / MindMap / TRIZ 等を経て
要件定義に入る」。現状の FullSense 6-stage loop は input → decision の
**収束プロセス**だが、人間の創造性は **拡散 → 構造化 → 収束** の三段。
llive 思考層に「拡散層」を追加し、Brief Runner の前段に挟むことで「人間並み
の創造性」を独自の差別化軸として確立する。

### 関連設計パターン

- **Diverge-Converge** (Design Thinking) — IDEO Design Council Double Diamond
- **KJ法** (川喜田二郎, 1967) — 付箋拡散 → 親和図 → 構造化
- **MindMap** (Tony Buzan, 1974) — 中心テーマ → 放射状階層展開
- **TRIZ** (G. Altshuller) — 既存 FR-23〜27 で実装済 (収束的問題解決)
- **NM法 / Synectics** — 類比・連想による発想拡張
- **Six Thinking Hats** (de Bono) — 観点別マルチ-track filter

### 要件詳細

| FR | 名前 | 概要 | 思考層との接続 | RAD 裏付け候補 |
|---|---|---|---|---|
| **CREAT-01** | **KJ法ノード** | Brief を起点に拡散的にアイデア集合 (≥20 件) を LLM mixture sampling で生成し、embedding clustering で親和グループ化、グループ命名と関係線を ledger に記録 | Brief Runner 前段、grounder の次 | design_thinking / clustering / kj_method / affinity_diagram |
| **CREAT-02** | **MindMap ノード** | 中心テーマ → 階層的 sub-topic 展開 (DFS) を実行、tree 構造を ledger に保存。各枝は LLM の 1 呼び出しで分岐 | KJ ノードと並行 / 独立 | mind_map / tree_of_thought / dfs_planning |
| **CREAT-03** | **構造化変換** | KJ + MindMap + TRIZ (既存 FR-23〜27) の出力を統合し、要件 spec (REQUIREMENTS.md の Markdown 表) を自動生成 | 拡散層 → BriefRunner の goal 拡張 | requirements_engineering / synthesis |
| **CREAT-04** | **Six Hats Multi-track** | Brief を 6 観点 (factual / emotional / cautious / optimistic / creative / process) で多視点評価。各観点が独立した sub-Brief を発行 | 既存 EpistemicType の拡張、Multi-track Filter Architecture A-1.5 と統合 | six_hats / multi_track_reasoning / debate_dialogue |
| **CREAT-05** | **類比 (Synectics) エンジン** | RAD コーパスから「Brief と意味的に遠いが構造的に類似」な doc を取得し、TRIZ 原理に紐付けて発想資源化 (cross_domain_ideation skill と連携) | Brief Grounder の拡張、cross-domain RAD bridge | analogical_reasoning / case_based_reasoning / metaphor_processing |

### 人間の思考フローとの対応

```
[人間の思考]                          [llive の対応]
  Brief (問題定義)            ←→     Brief API (LLIVE-002, 実装済)
       ↓
  KJ法 (拡散 + 親和)          ←→     CREAT-01 KJ法ノード
       ↓
  MindMap (構造化)            ←→     CREAT-02 MindMap ノード
       ↓
  TRIZ (矛盾解決)             ←→     既存 FR-23〜27 + CREAT-05 類比
       ↓
  Six Hats (多視点検証)       ←→     CREAT-04 + EpistemicType
       ↓
  要件定義 (構造化変換)        ←→     CREAT-03 構造化変換
       ↓
  実装                          ←→    BriefRunner.submit → FullSenseLoop
```

### スパイラル開発のイテレーション計画 (v0.9 CREAT)

| Iter | スコープ | 評価 | リスク |
|---|---|---|---|
| **C1** | CREAT-01 KJ法ノード — 拡散 sampling + clustering 試作 | Brief 1 つに対する拡散アイデア数 + group の意味的一貫性 | 中 (LLM 呼出回数増) |
| **C2** | CREAT-02 MindMap ノード — DFS 展開、depth=3 | tree 構造の妥当性、leaf の具体性 | 中 (token コスト) |
| **C3** | CREAT-04 Six Hats — 6 sub-Brief 並列発行 | 観点間の独立性、結論の多様性 | 中 |
| **C4** | CREAT-05 類比エンジン — cross-domain RAD bridge | 類比の有用性 (人間評価) | 高 (semantic distance metric 設計) |
| **C5** | CREAT-03 構造化変換 — 4 種出力を要件 spec に合成 | spec の網羅性 + 矛盾検出 | 高 (出力品質測定が困難) |
| **C6** | 統合 — KJ → MindMap → TRIZ → Six Hats → 構造化変換 のフルパス | end-to-end Brief → REQUIREMENTS.md 自動生成 | 高 (アーキ統合) |

### CREAT 要件のフェーズマッピング

| FR | Phase | Status |
|---|---|---|
| CREAT-01 | Phase 9 | Pending |
| CREAT-02 | Phase 9 | Pending |
| CREAT-03 | Phase 9 | Pending |
| CREAT-04 | Phase 9 | Pending |
| CREAT-05 | Phase 9 | Pending |

---

**Coverage (update):**
- v0.8 (Phase 8) CABT: 7 total
- v0.9 (Phase 9) CREAT: 5 total
- Mapped to phases: 80 / 80 ✓

*Requirements defined: 2026-05-13*
*Last updated: 2026-05-17 — v0.8 CABT (Cognitive-aware Transformer Block) + v0.9 CREAT (Creative Thinking Layer)*
