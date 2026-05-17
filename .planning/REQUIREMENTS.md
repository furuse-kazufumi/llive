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
- v0.7-vertical (Phase 10) MATH: 7 total
- Mapped to phases: 87 / 87 ✓

---

## v0.7-vertical — Math & Units Specialisation (MATH) 群 (2026-05-17 追加)

**ユーザー指示 (2026-05-17)**: 「llive は先ずは数学や単位に強い AI に育てたい」。

**動機**: llive の構造化思考層 + 形式検証 + provenance ledger が最も活きる
**最初の specialised vertical** として「数学・単位」を選ぶ。汎用 LLM が苦手
とする (a) 記号操作の幻覚, (b) 単位次元の取り違え, (c) 数値計算の error
propagation, (d) 公理体系の遵守 を llive 既存資産で克服する。Phase 8 (CABT)
や Phase 9 (CREAT) より優先して **v0.7 系列で先行着手** する。

### なぜ「数学・単位」が llive 最初の vertical に適しているか

| 観点 | 汎用 LLM の弱点 | llive 既存資産との合致 |
|---|---|---|
| 記号操作の幻覚 | "x² + x = 2x³" のような誤等式を生成 | EVO-04 Z3 静的検証で gate |
| 単位次元の取り違え | "5 m/s + 3 s = 8" | SI 次元解析エンジン (MATH-01) |
| 数値精度 | float 演算誤差を無視 | error propagation tracking (MATH-04) |
| 公理体系 | 暗黙の前提を混入 | EpistemicType=FACTUAL の strict track |
| 引用の信頼性 | "CODATA value is X" と適当に答える | RAD math/metrology + provenance (KAR) |

### 関連設計パターン

- **Specification by Example** (Adzic) — 数学要件は反例で記述
- **Dimensional Analysis** (Buckingham, 1914) — 次元の代数学
- **Static Verification Gate** — Z3 / Lean / Coq による事前検証
- **Provenance Chain** (DDD) — 引用源 → 検証 → 信頼度

### 要件詳細

| FR | 名前 | 概要 | 関連 RAD / 既存 | 優先度 |
|---|---|---|---|---|
| **MATH-01** | **SI 単位次元解析エンジン** | 7 基本単位 (m / kg / s / A / K / mol / cd) + 派生単位の dimensional analysis。`5 m/s + 3 s` を unit-mismatch として検出 | metrology / physics | **HIGH (1st)** |
| **MATH-02** | **Z3 / Sympy 統合検証層** | LLM 出力の数式を Z3 / Sympy で再検算し、不整合を flag。EVO-04 の数式版 | formal_methods (既存 EVO-04) | **HIGH (2nd)** |
| **MATH-03** | **数式構文解析** | LaTeX, MathML, Mathematica, AsciiMath, Python sympy 構文の相互変換と AST 化 | math_typesetting | MED |
| **MATH-04** | **数値計算精度トラッキング** | float64 / IEEE 754 の error propagation を演算ごとに追跡。significant digits の自動算出 | numerical_analysis | MED |
| **MATH-05** | **物理定数・単位辞書** | CODATA 2022 (現行) + NIST 単位定義の grounded 辞書。RAD math/metrology の sub-corpus として配置 | metrology (既存 math_hints.py 拡張) | **HIGH (3rd)** |
| **MATH-06** | **単位変換・無次元化** | 単位変換 (km/h ↔ m/s 等) と Buckingham π 定理による無次元化 | metrology / physics | MED |
| **MATH-07** | **MATHEMATICAL EpistemicType** | 既存 `EpistemicType` 列挙 (FACTUAL/EMPIRICAL/...) に **MATHEMATICAL** を加え (現状 RESERVED_1 を割り当て可)、数学 Brief 専用の filter chain を選択可能化 | DTKR / Multi-track Filter | MED |
| **MATH-08** | **内蔵計算エンジン (差別化軸)** | LLM に「数値計算をさせない」設計。算術 / 三角関数 / 行列演算 / FFT / 微積分 / 線形ソルバ / 統計を **決定論的に llive 側で実行**、LLM はクエリ生成と結果解釈のみ。Brief Runner の前段で式抽出 → 計算 → 結果を Stimulus に grounded 注入。Wolfram Alpha 風だが完全 on-prem | numerical_analysis / scipy / sympy / mpmath | **HIGH (4th, 差別化最大)** |

### llive 既存資産との接続

- `src/llive/memory/rad/math_hints.py` — 既存。数式 hint loader を MATH-03 のエントリポイントに
- `src/llive/evolution/` — EVO-04 で既に Z3 を使用 (構造的不変量検証)。MATH-02 はその数式版
- `src/llive/fullsense/types.py::EpistemicType` — `RESERVED_1` を `MATHEMATICAL` に格上げ (MATH-07)
- `src/llive/memory/provenance.py` — 数学的引用 (定理名 + 出典 doc_id) を強化
- RAD `mathematics` / `formal_methods` / `physics` / `metrology` — 各分野コーパスを grounding 源として活用

### スパイラル開発のイテレーション計画 (v0.7-vertical MATH)

| Iter | スコープ | 評価 (data) | リスク |
|---|---|---|---|
| **M1** | MATH-01 SI dimensional analysis のコア — Pint ライブラリ統合 + 7 基本単位 | unit-mismatch detection 100% on test corpus | 低 (Pint 成熟) |
| **M2** | MATH-05 CODATA + NIST 辞書を RAD `metrology` に append、grounding 用に整備 | 100 定数 / 単位の正引可 | 低 |
| **M3** | **MATH-08 内蔵計算エンジン (差別化軸)** — Brief 前段で式抽出 → sympy/scipy/numpy 計算 → 結果を grounded Stimulus に注入 | 算術 100 件で LLM 直接回答との誤差を測定、llive 計算側は誤差 0 を保証 | 中 (式抽出 LLM 依存) |
| **M4** | MATH-02 Sympy 検算層 — LLM 数式出力を AST 化して Sympy で simplify、差分を flag | 数式幻覚検出率 (人手評価 ≥80%) | 中 |
| **M5** | MATH-07 MATHEMATICAL EpistemicType + Brief filter chain 統合 | 数学 Brief × {plain, MATH track} A/B | 中 |
| **M6** | MATH-06 単位変換 + 無次元化 | 物理問題 100 件で π 群が正しく抽出 | 中 |
| **M7** | MATH-04 error propagation tracking | significant digits の自動算出が IEEE 754 規格と一致 | 高 |
| **M8** | MATH-03 multi-syntax 解析 (LaTeX/MathML/Mathematica/Sympy) | 100 数式の往復変換で意味保存 | 高 |

### 評価ベンチマーク (vertical 専用)

- **MMLU math** subset
- **GSM8K / MATH** dataset
- **PhysicsBench** (物理単位問題)
- **DimSafe**: llive 独自テストセット — 単位次元誤りを含む 1000 件で recall ≥99%, precision ≥95%

### MATH 要件のフェーズマッピング (Phase 10、ただし v0.7 系列で先行着手)

| FR | Phase | Status | Priority |
|---|---|---|---|
| MATH-01 | Phase 10 | **Implemented + Brief grounding 配線済** (2026-05-17, internal: `src/llive/math/units.py` + `BriefGrounder._lookup_units` + `UnitCitation` ledger 記録, minimal scope: 個別 Quantity 識別まで、cross-quantity 次元演算チェックは次イテレーション) | **1st** |
| MATH-02 | Phase 10 | **Implemented** (2026-05-17) | **2nd** |

**MATH-02 実装ノート (2026-05-17)**: `src/llive/math/verifier.py` に `MathVerifier`
+ `VerificationResult` を新規実装。3 メソッド (check_equivalence / check_implication
/ check_satisfiable) を提供し、Sympy で代数等価、Z3 で含意・SAT/UNSAT を決定論的に
検証。**トレーサビリティ重視設計**: `MathVerifier(ledger=...)` で attach すると
全 check が ledger に `math_verified` event として自動記録、`BriefLedger.trace_graph()`
の `evidence_chain` に `kind="math"` (+ `check_kind`) として COG-03 と統合される。
sympy>=1.12, z3-solver>=4.13 を required dependency に昇格。テスト 16 件追加
(verifier 12 + traceability 4)、1034 → 1052 PASS / 回帰ゼロ。
| MATH-05 | Phase 10 | **Implemented** (2026-05-17, internal: `src/llive/math/constants.py` CODATA 2022 + NIST、**未配線**: Brief grounding 統合は次イテレーション) | **3rd** |
| MATH-08 | Phase 10 | **Implemented** (2026-05-17, internal: `src/llive/math/calculator.py` + Brief grounding 配線完成: `BriefGrounder._lookup_calc` + `CalcCitation` ledger 記録) | **4th (差別化)** |
| MATH-03 | Phase 10 | Pending | MED |
| MATH-04 | Phase 10 | Pending | MED |
| MATH-06 | Phase 10 | Pending | MED |
| MATH-07 | Phase 10 | Pending | MED |

**Coverage (final):**
- v0.7-vertical (Phase 10) MATH: 8 total (内 MATH-08 が差別化軸)
- v0.8 (Phase 8) CABT: 7 total
- v0.9 (Phase 9) CREAT: 5 total
- v1.0-frame (cross-cutting) COG-FX: 10 因子マッピング + 不足 4 件
- Mapped to phases: 92 / 92 ✓

---

## v1.0-frame — Cognitive Factor Framework (COG-FX) 2026-05-17 追加

**動機 (ユーザー提示の 10 因子セット)**: 人間が AI 開発を駆動する深層心理から
**再利用可能な「思考因子」**を抽出し、LLM の推論・計画・自己改善・エージェント
設計に組み込める形へ変換する。llive の既存実装と新規要件 (MATH/CABT/CREAT) を
**統一語彙で説明できる横断フレームワーク**として位置付ける。

**実装方針**: 単一巨大プロンプトに埋め込まず、**役割別 policy に分解**
(planner / memory / critic / evolution / trace policy)。個別に A/B 比較し
改善可能にする。

### 10 因子 ↔ llive 既存・新規 FR マッピング

| # | 因子 | LLM 役割 | llive 既存 FR (実装済) | llive 新規 FR (計画) | COG-FX 追加 |
|---|---|---|---|---|---|
| 1 | **構造化** | 課題を分解 | Brief constraints, Salience+Curiosity gate (Phase 1) | CREAT-02 MindMap (DFS), MATH-01 dimensional analysis | — |
| 2 | **再構成** | 代替案生成 | FR-23〜27 TRIZ (40 原理 + 矛盾 + ARIZ + 9 画法), EVO-03 Candidate generator | CREAT-01 KJ法ノード, CREAT-05 類比エンジン | — |
| 3 | **閉ループ** | 検証計画を伴う | BriefRunner submit→plan→approval→tool→outcome (LLIVE-002 実装済) | CABT-06 Approval-gated decoding | — |
| 4 | **自己拡張** | 外部資源を使う | 4 層メモリ (MEM-01〜09), RAD 49 分野, BriefTools whitelist, RPA (RPAR 軸) | MATH-08 計算エンジン, CABT-07 memory-augmented residual | — |
| 5 | **不確実性** | 仮説と事実を分離 | FR-21 BayesianSurpriseGate, EpistemicType A-1.5, SEC-01 Quarantined Zone | CABT-04 Salience-gated attention | **COG-01** Confidence/Assumption/Missing-Evidence 三重出力 |
| 6 | **探索** | 未踏案を試す | EVO-* (Z3 検証 + Failed Reservoir + Reverse-Evo Monitor) | CREAT-04 Six Hats 並列発行, CABT-02 Stage routing | — |
| 7 | **整合** | 全体制約で再評価 | C-1 Approval Bus + Policy, EVO-04 Z3 形式検証, SEC-03 hash chain | MATH-02 Sympy 検算, CABT-05 TRIZ-conditioned head | **COG-02** Governance scoring layer (usefulness/feasibility/safety/traceability) |
| 8 | **来歴** | 判断履歴を残す | Provenance (memory/provenance.py), SqliteLedger, BriefLedger, SEC-03 SHA-256 chain | MATH 全 FR で計算 citation を ledger に固定 | **COG-03** Evidence/Tool/Decision chain の三層 trace graph |
| 9 | **多視点** | 評価関数を分離 | Multi-track Filter Architecture A-1.5 (5 EpistemicType + 5 RESERVED) | CREAT-04 Six Hats, CABT-03 Epistemic-typed token pool | **COG-04** Role-based agents (architect / critic / executor / auditor) |
| 10 | **現実接続** | 実環境制約を扱う | INT-01〜04 llmesh sensor bridge (MQTT/OPC-UA, FR-19) | (Phase 4 production で実装) | — |

### 優先順位 (v1.0 安定リリース必須の 5 因子)

ユーザー観察: 「探索 / 再構成を強化する前に、構造化 / 不確実性 / 閉ループ /
整合 / 来歴 の土台が必要」。これは llive の **v1.0 リリース必須** 5 因子と
位置付ける:

```
土台 (v1.0 must-have)         発展 (v1.0+ で順次)
─────────────────────         ──────────────────
1. 構造化  ✅ 既存             2. 再構成  (TRIZ 既存 + CREAT 計画)
3. 閉ループ ✅ Brief API         6. 探索    (EVO 既存)
5. 不確実性 ✅ Surprise Gate     9. 多視点  (Multi-track 既存 + COG-04)
7. 整合    ✅ Approval Bus      10. 現実接続 (INT 計画)
8. 来歴    ✅ Ledger
```

土台 5 因子は **2026-05-17 時点ですべて実装済**。これは llive が「面白い案を
出す前に、誤差・暴走・非再現性を防ぐ土台」を備えていることを意味する。

### 新規 COG-FX 要件詳細

| FR | 名前 | 概要 | 関連既存 FR | 優先 |
|---|---|---|---|---|
| **COG-01** | Confidence/Assumption/Missing-Evidence Triple Output | 各 BriefResult に (confidence, assumptions, missing_evidence) の 3 列を追加。不確実性を必ず分離して保持 | FR-21 SurpriseGate, A-1.5 EpistemicType | MED |
| **COG-02** | Governance Scoring Layer | 候補案を usefulness だけでなく feasibility / safety / traceability / governance で再採点。Approval Bus 前段に scoring policy を挟む | C-1 Approval Bus, SEC-03 audit chain | HIGH |
| **COG-03** | Trace Graph (Evidence / Tool / Decision の 3 層) | BriefLedger を拡張し、(a) evidence_chain (b) tool_chain (c) decision_chain の 3 グラフを構築。デバッグ・自己改善・失敗分析の基盤 | BriefLedger, SqliteLedger | MED |
| **COG-04** | Role-based Agents | architect / critic / executor / auditor の 4 ロールに評価関数を分離。Brief 1 件に対し 4 ロールが独立評価 | Multi-track Filter A-1.5 | LOW (v0.9 CREAT の後で十分) |

### 因子別 metadata schema (横断仕様)

各メモリ・各 ledger entry に以下の attribute を持たせる:

```python
# 例: SemanticMemory 1 件、BriefLedger 1 行、Stimulus 1 個 ...
{
    "factor": "uncertainty",         # 10 因子のどれか
    "uncertainty": 0.23,              # 0〜1
    "dependency": ["evidence:doc#42", "tool:sympy.simplify"],
    "evidence_source": "doc#42",
    "applicable_scope": "math:dimensional",
    "promotion_status": "candidate"   # draft/candidate/promoted/archived
}
```

これは LLM の自然言語ルールに依存せず、後段システム (llove TUI, audit
agent, evolution scheduler) が機械的に消費できる。

### COG-FX 要件のフェーズマッピング

| FR | Phase | Status | Priority |
|---|---|---|---|
| COG-01 | Phase 4 (v1.0) | **Implemented** (2026-05-17) | MED |
| COG-02 | Phase 4 (v1.0) | **Implemented** (2026-05-17) | **HIGH** |
| COG-03 | Phase 4 (v1.0) | **Implemented** (2026-05-17) | MED |
| COG-04 | Phase 9 (CREAT 後) | **Implemented** (2026-05-17, with CREAT-04) | LOW |
| CREAT-04 | Phase 9 | **Implemented** (2026-05-17, with COG-04) | — |
| CREAT-01 | Phase 9 | **Implemented** (2026-05-17) | — |
| CREAT-02 | Phase 9 | **Implemented** (2026-05-17) | — |
| CREAT-03 | Phase 9 | **Implemented** (2026-05-17) | — |
| CREAT-05 | Phase 9 | **Implemented** (2026-05-17) | — |

**COG-04 + CREAT-04 統合実装ノート (2026-05-17)**: 「4 roles (architect/critic/
executor/auditor) × 6 hats (white/red/black/yellow/green/blue) = 10 視点」を
直交軸として 1 つの `RoleBasedMultiTrack` に集約。`src/llive/brief/roles.py`
に deterministic heuristic で 10 lens を実装し、`PerspectiveLens` Protocol で
後段 LLM-as-judge / 並列 sub-Brief に Strategy 差し替え可能。Approval は行わず
scoring 専念 (Governance と同じ責務分離)。Runner に opt-in 注入、`perspectives_observed`
ledger event + `BriefResult.perspectives` / `perspective_summary` 拡張。
`MultiTrackSummary.consensus_recommendation` で `proceed` / `review` / `hold`
の short verdict を出すが gating ではなく示唆。テスト 20 件追加、1014 → 1034 PASS。

**Coverage (final):**
- v0.7-vertical (Phase 10) MATH: 8 total
- v0.8 (Phase 8) CABT: 7 total
- v0.9 (Phase 9) CREAT: 5 total
- v1.0-frame COG-FX: 4 新規 + 10 因子マッピング (横断)
- v2.0-core (Phase 11) ORG-FX: 8 件 (LLM コア独自化)
- Mapped to phases: 100 / 100 ✓

---

## v2.0-core — ORG-FX (Originality Framework) 2026-05-17 追加

**ユーザー指示 (2026-05-17 終盤)**: 「Qwen の設計思想から徐々に離れて独自路線を
突っ走るのが理想。差別化されていないと研究の価値がない。普及している AI を
使った方がマシってなりそう。」

**動機**: 現状 (v0.6) の llive は周辺認知 OS としては独自だが、**LLM コア
自体は Qwen / Llama / Mistral に依存**。中長期的に研究としての価値を保つ
ためには、コア自体を独自化する経路を要件化しておく必要がある。

### 「Qwen から離れる」5 段階ロードマップ

```
段階              | 期間      | 内容
──────────────────┼───────────┼──────────────────────────────
Stage A (短期)    | 〜3 ヶ月  | LLM コアは凍結、周辺の差別化を最大化
                  |           | (CABT forward hook / MATH / CREAT)
Stage B (中期 1)  | 3〜6 ヶ月 | LoRA で llive 用 specialised adapter
                  |           | 訓練、attention に memory bias 注入
Stage C (中期 2)  | 6〜12 ヶ月| Distillation で小型 specialised model
                  |           | (qwen2.5:14b → llive-7b 蒸留)
Stage D (長期 1)  | 1〜2 年   | Transformer block を memory-coupled
                  |           | architecture に置換 (CABT-07 の本実装)
Stage E (長期 2)  | 2〜3 年   | Transformer 以外の LLM コア (Mamba /
                  |           | RWKV / Hyena 系 + llive 思考層 native)
```

### 関連設計パターン

- **Composite** (TRIZ 原理 40) — LLM コア = Transformer + Memory + Multi-track の合成
- **Strategy** (GoF) — コア architecture を差し替え可能に
- **Mediator** (TRIZ 原理 24) — Memory を attention に参照経由で持ち込む
- **Local Quality** (TRIZ 原理 3) — Stage 別に異なる sub-network を活性化

### 要件詳細

| FR | 名前 | 概要 | ロードマップ Stage | 関連既存 FR |
|---|---|---|---|---|
| **ORG-01** | **Cognitive Block Replacement** | Transformer ブロックを llive 思考層と同期した構造に置換。salience / curiosity を直接 attention に持ち込む | Stage D | CABT-01〜07 (Phase 8) の本実装版 |
| **ORG-02** | **Memory-coupled inference** | LLM 推論時に 4 層メモリを直接参照 (Memorizing Transformer の発展)。inference 中に memory write も発生 | Stage C/D | MEM-01〜09 |
| **ORG-03** | **Multi-track sub-network** | EpistemicType ごとに別の sub-network を持つ MoE の認知版。FACTUAL / NORMATIVE / INTERPRETIVE で異なる weights | Stage C | A-1.5 Multi-track Filter |
| **ORG-04** | **TRIZ-guided architecture search** | LLM コア自体を TRIZ 矛盾解決で自己改良。AutoML-Zero + TRIZ ハイブリッド | Stage D | FR-23〜27 + EVO-04 |
| **ORG-05** | **Surprise-native pretraining** | Bayesian Surprise を loss に組み込んだ事前学習。novelty / saliency を内在化 | Stage E | FR-21 BayesianSurpriseGate |
| **ORG-06** | **Provenance-aware tokens** | 各 token に metadata 列 (provenance / trust / epistemic_type) を持たせ attention で参照 | Stage B/D | CABT-01, CABT-03, CABT-07 の統合 |
| **ORG-07** | **Approval-native decoding** | 出力 token sequence を decoder 内で Approval policy が検査。constitutional AI の architectural 版 | Stage C/D | CABT-06, COG-02 |
| **ORG-08** | **llive-specialized small model distillation** | qwen2.5:14b → llive-7b 蒸留。学習データは RAD コーパス + ledger 成功例 + TRIZ 出力 | Stage C | Phase 5 RUST extensions, Phase 9 CREAT |

### なぜこの順序か

- **Stage A (LLM 凍結)** = 既存 OSS LLM の更新 (Qwen 2.6 / Llama 4 等) を直接取り込める利点を保ったまま差別化
- **Stage B (LoRA)** = リスク中、GPU は RTX 3090 級で可、コア重みは触らない
- **Stage C (蒸留)** = 小型化することで on-prem 普及性が上がり、かつ llive 専用化
- **Stage D (block 置換)** = 学習やり直しになるが、研究としての独自性が確立
- **Stage E (Transformer 以外)** = 完全な独自路線、Mamba / RWKV 系の学術成果を取り込む

### ORG-FX 要件のフェーズマッピング

| FR | Phase | Stage | Status | Priority |
|---|---|---|---|---|
| ORG-06 | Phase 8 拡張 | B+D | Pending | HIGH (CABT-01〜07 の統合) |
| ORG-02 | Phase 11 | C/D | Pending | HIGH |
| ORG-03 | Phase 11 | C | Pending | MED |
| ORG-08 | Phase 11 | C | Pending | MED (GPU 投資要) |
| ORG-07 | Phase 11 | C/D | Pending | MED |
| ORG-01 | Phase 11 | D | Pending | LOW (長期) |
| ORG-04 | Phase 12 | D | Pending | LOW |
| ORG-05 | Phase 12 | E | Pending | LOW (要 GPU クラスタ) |

### 評価指標

「Qwen との距離」を測る metric を導入:

- **Architectural Originality Score** = Σ (差別化 FR 実装数) / 全 FR 数
- **LLM Core Independence Ratio** = (llive 専用 inference path) / (全 inference path)
- **Replaceability Test** = qwen を抜いて llive-only で動作するか (Stage C 以降)

### Phase Dependencies

```
Phase 8 (CABT) → ORG-06 (Provenance-aware tokens)
Phase 9 (CREAT) → ORG-03 (Multi-track sub-network) との連携
Phase 4 (Production) → ORG-07 (Approval-native decoding) の前提
Phase 11 (ORG-FX core) → Phase 12 (full independence)
```

**Coverage (final final):**
- v0.7-vertical (Phase 10) MATH: 8 total
- v0.8 (Phase 8) CABT: 7 total
- v0.9 (Phase 9) CREAT: 5 total
- v1.0-frame COG-FX: 4 + 10 因子マッピング
- v2.0-core (Phase 11) ORG-FX: 8 total
- v0.7-vertical+OKA (Phase 10) OKA-FX: 10 total
- Mapped to phases: 110 / 110 ✓

---

## v0.7-vertical+OKA — OKA-FX (Framework inspired by Prof. Oka Kiyoshi) 2026-05-17 追加

**経緯 (2026-05-17 5 回目)**: 「岡潔先生の視点に学ばせていただいた数学 LLM
進化提案」として、情緒・行き詰まり・文章化・国語力という先生のお考えを
**設計の 4 観点** として参照させていただき、最小アーキテクチャ + フェーズ
別実装プランを記述した要件群。

> ⚠️ **重要 (敬意の表明)**: 本 framework は、岡潔先生 (1901-1978、奈良女子大学
> 名誉教授、文化勲章) のお考えそのものを実装したと主張するものではあり
> ません。先生が遺された豊かな思索のうち、エンジニアリング言語として
> 参照させていただける 4 観点に着目し、それを **触発源** としてモジュール
> 設計に活かしたものです。先生の思想は本来、計算機実装には収まらない
> 深さを持ちます。命名にはその敬意を込めています。

**動機**: MATH-01〜MATH-08 が「LLM が数式を間違えない」軸 (defensive) なのに対し、
OKA-FX は「LLM が数学的に発見する」軸 (offensive)。岡潔先生のお考えに学ぶ
ことで、正答率中心主義から **insight / reframing / explanation** を同時
最適化する系へ拡張する。MATH との関係:

* **MATH** = 計算の正確さ (deterministic verifier, units, calculator)
* **OKA** = 思考の質 (essence framing, strategy switching, reflective notebook, explanation)

両者は補強関係 — MATH が「黒板の正しさ」、OKA が「数学者の思考プロセス」。

### 中核仮説 → 設計マッピング

| 学ばせていただいた観点 | 先生の言葉 (出典) | こちらの設計が触発を受けた実装上の切り口 |
|---|---|---|
| 情緒はヒューリスティクス | 「数学は情緒である」(岡潔『春宵十話』毎日新聞社, 1963 他) | OKA-08 美的選好スコア (弱教師あり報酬) |
| 行き詰まりはモード転換信号 | 「発見の前に一度行き詰まる」(岡潔『春風夏雨』毎日新聞社, 1965 他) | OKA-03 戦略切替 + 停滞検知 |
| 文章化は補助記憶 | 「文章を書くことなしには思索を進められない」(岡潔の随筆群) | OKA-04 ReflectiveNotebook (推論ログ + 失敗記録) |
| 国語力は抽象化基盤 | 「国語が数学を育む」(岡潔の講話・随筆) | OKA-05 再定式化コーパス + 言い換え訓練 |

> ※ 上記出典の対応は、Perplexity / 公開資料を介して参照させていただいた
> 範囲のものです。先生の原典に厳密に当たり直す機会は別途設けたく、誤読
> がある場合は本要件側を訂正する方針です。

### 要件詳細

| FR | 名前 | 概要 | 優先度 |
|---|---|---|---|
| **OKA-01** | **Problem Framing Layer** | 入力問題から「何が不思議か / 保存量 / 対称性」を自然言語で抽出。複数視点で核心を記述、解法候補の初期分布を整える | **HIGH (1st)** |
| **OKA-02** | Core Essence Extractor | OKA-01 の中核 — 「核心メモ」(N 文以内) を deterministic mock + LLM で生成。Brief grounding に injectable | **HIGH (1st)** |
| **OKA-03** | Strategy Orchestrator | 複数解法ファミリーを並列保持、停滞検知で切替 (記号計算 / 具体例 / 反例 / 図形 / コード) | **HIGH (2nd)** |
| **OKA-04** | Reflective Notebook Memory | 中間式 / 失敗試行 / 気づき / 未解決疑問を JSON ノートで長期保持。同系列問題で再利用 | **HIGH (2nd)** |
| **OKA-05** | Reformulation Corpus | 同一問題の言い換え / 比喩 / 図形化記述を集めた corpus、抽象化と転移性能向上 | MED |
| **OKA-06** | Explanation Alignment Layer | 解答+「なぜその見方が自然か」を出力、納得感/美しさを人間評価で報酬化 | MED |
| **OKA-07** | Insight Score 評価軸 | 解法の核心を短く本質的に言語化できたか — 評価フレームワーク | MED |
| **OKA-08** | Aesthetic Preference Score | 数学者評価者の「美しい/冗長」選好を報酬として学習 | LOW |
| **OKA-09** | Pedagogical Resonance Score | 学習者が説明を読んで納得できたか — 教育的評価 | LOW |
| **OKA-10** | Notebook Utility Score | 途中ノートが別問題で再利用できたかの A/B 検証 | LOW |

### 設計原則 (REQUIREMENTS にロックイン)

1. **正答率中心主義からの離脱** — insight / reframing / explanation を同時最適化
2. **複合系として扱う** — 解答生成器ではなく「問題理解器 / 戦略管理器 / 研究ノート器 / 説明器」の合成
3. **失敗ログを捨てない** — 探索履歴として再利用 (OKA-04 + COG-08 来歴と整合)
4. **数式 ↔ 自然言語 ↔ コード ↔ 図的記述の往復** — 単一表現に縛らない
5. **主観的評価を弱教師ありの報酬信号として活用** — OKA-08 / OKA-09

### llive 既存資産との接続

- **COG-03 trace_graph** — OKA-04 ReflectiveNotebook はこの evidence_chain の上位層
- **COG-08 来歴** — failure log は SEC-03 hash chain と同じ audit 性質
- **MATH-02 MathVerifier** — OKA-03 戦略の中で「数式書き換え後の等価性」を即時検証
- **CREAT-01 KJ法** + **CREAT-04 Six Hats** — OKA-01 Framing と相補
- **FR-23〜27 TRIZ** — OKA-03 戦略切替時の「矛盾解消パターン」として再利用
- **RAD `mathematics` / `metrology` / `physics`** — OKA-05 再定式化 corpus の源

### フェーズマッピング

| FR | Phase | Status | Priority |
|---|---|---|---|
| OKA-01/02 | Phase 10 (v0.7+OKA) | **Implemented (minimal prototype, 2026-05-17)** | HIGH |
| OKA-03 | Phase 10 拡張 | **Implemented (minimal prototype, 2026-05-17)** | HIGH |
| OKA-04 | Phase 10 拡張 | **Implemented (minimal prototype, 2026-05-17)** | HIGH |
| OKA-05/06 | Phase 11 | Pending | MED |
| OKA-07〜10 | Phase 12 (評価フレームワーク) | Pending | MED/LOW |

### OKA-01〜04 最小プロトタイプ実装ノート (2026-05-17)

* `src/llive/oka/essence.py` — `CoreEssenceExtractor` (deterministic heuristic + LLM Strategy 差し替え可能)
* `src/llive/oka/notebook.py` — `ReflectiveNotebook` (JSON 永続、失敗記録、cross-Brief 再利用 API)
* `src/llive/oka/orchestrator.py` — `StrategyOrchestrator` (戦略ファミリー登録、停滞検知で切替)
* BriefLedger と連動 — `oka_essence_extracted` / `oka_notebook_appended` / `oka_strategy_switched` event
* テスト群追加、トレーサビリティを COG-03 trace_graph に統合

### OKA + BriefRunner 自動統合 (2026-05-17 続)

* `BriefRunner(essence_extractor=, notebook=, strategy_orchestrator=)` で 3 components を opt-in
* submit 開始時に CoreEssence 自動抽出 → `BriefResult.essence` + outcome event 複製
* loop.process 失敗時に `failed_attempt` note を自動 append (next Brief で `related_to()` 再利用可)
* tests/component/test_cog_fx_e2e.py に 11 因子 (9 COG + OKA-01/02/04 + MATH-02) 一括 E2E ハーネス追加

---

## v0.8-meta — VRB-FX (Verbalization Framework) 2026-05-17 追加

**ユーザー指示 (2026-05-17 6 回目)**: 「Local LLM 研究開発向け言語化支援基盤 提案メモ」
として、グロービス『MBA 言語化トレーニング』を Local LLM 研究開発基盤に写像した
8 機能 + 中間表現 + 段階導入案を提示。「採用可否の判断は任せます」。

**判定**: 既存資産で **大半カバー済み**。新規実装は 4 件のみ。

### 既存実装との対応マッピング

| VRB 提案機能 | 既存対応 | 状態 |
|---|---|---|
| 1. IntentSpec Builder | `Brief` (goal/constraints/success_criteria/...) | **Already implemented** |
| 2. Prompt / Requirement Lint | 部分 (`GovernanceScorer.feasibility`)、曖昧語検出は未実装 | **VRB-02 新規** |
| 3. Evidence Map | `TraceGraph.evidence_chain` (6 kind: triz/rad/calc/math/oka_essence/oka_note) | **Already implemented** |
| 4. Premortem / Counterfactual Review | 部分 (`BlackHatLens` / `CriticLens`)、formal premortem は未実装 | **VRB-04 新規** |
| 5. Eval Spec Editor | `Brief.success_criteria` あり、metrics registry / stop_conditions は未実装 | **VRB-05 新規** |
| 6. Dual Spec Writer | 未実装 — Human / Model Contract / Eval Contract / Manifest / Note 切替 | **VRB-06 新規** |
| 7. Lesson Capture / Decision Log | `ReflectiveNotebook` (insight / failed_attempt / reframing / ...) | **Already implemented** |
| 8. Audience Switch / Granularity Switch | 未実装 (VRB-06 と統合可能) | **VRB-06 と統合** |

### 新規要件 (4 件のみ)

| FR | 名前 | 概要 | 優先度 |
|---|---|---|---|
| **VRB-02** | Prompt / Requirement Lint | Brief.goal / constraints / success_criteria を走査し、曖昧語 (高性能/堅牢/使いやすく)・評価不能語・比較軸不足・対象読者不明を検出 → `lint_findings` event | **HIGH (1st)** |
| **VRB-04** | Premortem Generator | 採用前の Brief に「失敗シナリオ」を deterministic に生成 (BlackHat lens + 危険語 + 制約矛盾) → `premortem_generated` event。Approval Bus の payload に伝達 | MED → **Implemented (2026-05-17)** |
| **VRB-05** | Eval Spec Editor (Metrics Registry + Stop Conditions) | Brief に `metrics_registry` (name → unit → threshold) と `stop_conditions` を追加できる軽量レイヤ。後段で BriefResult との突合 | MED → **Implemented (2026-05-17)** |
| **VRB-06** | Dual Spec Writer (Audience Switch 込) | 同一 Brief を Human Brief / Model Prompt Contract / Eval Contract / Execution Manifest / Research Note の 5 出力モードで render | LOW → **Implemented (2026-05-17)** |

### 既に達成されている設計原則

| VRB 原則 | 既存実装 |
|---|---|
| Traceability First | SEC-03 SHA-256 chain + COG-03 trace_graph + 全 `bind_ledger()` pattern |
| Extensibility by Schema | dataclass(frozen) + JSON-friendly payload + ledger append-only |
| Model-Agnostic Core | `LLMBackend` Protocol (ollama / anthropic / mock / future Mamba/RWKV) |
| Human-in-the-Loop by Default | Approval Bus + HatPerspective.RED + ReflectiveNotebook |
| Research Reproducibility | BriefLedger replay + deterministic lens/extractor/verifier |

### VRB-02 PromptLint 最小プロト実装ノート (2026-05-17 続々)

* `src/llive/brief/prompt_lint.py` — `PromptLinter` + `LintFinding`
* deterministic lexical scan で 5 カテゴリ検出:
  vague_term / unmeasurable_claim / missing_audience / missing_comparison / undefined_constraint
* `bind_ledger()` で BriefLedger に attach → `lint_findings_recorded` event
* COG-03 trace_graph evidence_chain に `kind="lint"` として統合
* テスト追加、回帰ゼロ

---

## IND-FX — Independence Principle (FullSense 設計原則、2026-05-17 追加)

**ユーザー指示 (2026-05-17 8 回目末、LinkedIn フィードバック転載)**:
> 「llive の記憶層が llove の交互データに依存し、llove がまた llmesh の接続能力に
> 依存しているなら、その中の一つだけを使う価値は半減します。理想的なのは、各層が
> 独立して価値を提供でき、組み合わせることで効果が積み上がる設計であり、全部
> 揃えないと動かないという状況は避けるべきです。」

これを設計原則として locked-in:

### IND-01 各層独立性 (Independence)

* **llive** は llove / llmesh に runtime 依存してはならない (single-package install で
  全機能が動く)
* **llove** は llive / llmesh に runtime 依存してはならない
* **llmesh** は llive / llove に runtime 依存してはならない
* 連携 (MCP / OPC-UA / sensor bridge / TUI bridge) は **optional dependency** として
  `pyproject [project.optional-dependencies]` に隔離

### IND-02 組合せ価値積み上げ (Additive Composition)

* 各層単独 = ベースライン価値を提供
* llive + llove = ベース + 視覚化 + IDE 統合価値
* llive + llmesh = ベース + センサ / 製造現場価値
* 3 つ揃い = フル価値 (ベース + 視覚化 + センサ)
* どの組合せでも「壊れない / 機能消失しない」ことが必須

### IND-03 監査の機械化

* `scripts/audit_independence.py` で AST スキャン:
  - hard import (`import llove`) → leak (exit 1)
  - try/except ラップされた optional import → soft (exit 0)
* 結果は `docs/audits/independence-YYYY-MM-DD.md` に出力
* **2026-05-17 監査結果**: 171 ファイル中 hard leak 0 件 / soft 0 件 = clean
* CI 候補 (将来 GHA で各 PR 時に走らせる)

### 既存実装での担保

* すべての llive component が **opt-in / Strategy 注入** で構築済み
  (Grounder / Governance / Perspectives / MathVerifier / Essence / Notebook /
  Orchestrator / PromptLinter — どれも None 可)
* `bind_ledger()` パターンで ledger も optional
* 連携機能 (mcp / vlm / torch / ingest) はすべて `[project.optional-dependencies]` で
  隔離済み (pyproject.toml line 44〜)

### 違反した場合の対応

1. CI で audit_independence.py が exit 1 → ブロック
2. 既存コードを try/except ImportError でラップ
3. 機能本体は optional 化、デフォルトは ImportError fallback で機能停止のみ
4. 単体テストで「optional 依存無しでもコアテストが通る」ことを確認

### IND-04 Annotation Channel — 独立性を保ったまま組合せ価値を出す

**ユーザー提案 (2026-05-17 8 回目末)**: 「応答にアノテーションを用意すれば独立性を
保ちながら組み合わせでの効果も得られるのでは？」

**設計**: llive の全主要応答型 (`BriefResult`, `CoreEssence`, `LintReport`,
`PremortemReport`, `EvalReport`, `MindMapTree`, `RequirementDraft`, etc.) に
optional な `annotations: AnnotationBundle` フィールドを追加。各 component が
**自然なヒントを emit** するだけで、消費側 (llove TUI / llmesh visualizer /
別 agent) は任意で読み取って付加価値を提供する。

#### Annotation 型

```python
@dataclass(frozen=True)
class Annotation:
    namespace: str          # "vrb" / "oka" / "cog" / "math" / "creat" / "core"
    key: str                # "lint_score" / "essence_card" / "consensus" / ...
    value: Any              # JSON-friendly
    target_layer: str | None = None   # "llove" / "llmesh" / "any"
```

#### 設計原則

1. **emit-side は consumer を知らない** — llive は「これは可視化可能だよ」とヒントを
   出すだけ、llove が来なくても動作不変
2. **consumer-side は emit を要求しない** — annotation 無しでも fall back で動く
3. **namespace を必須にする** — `vrb.lint_score` と `oka.essence_card` が衝突しない
4. **JSON-friendly のみ** — 直接 MCP / HTTP に流せる
5. **bind_ledger() と同じ哲学** — optional / strategy / no coupling

#### 期待される consumer

- **llove TUI**: `core.renderable=true` を見て自動でカード表示
- **llmesh visualizer**: `math.constant_used` を見て計装グラフに highlight
- **別 agent (MCP 経由)**: `oka.failed_attempt_relevant=true` を見て過去ノート参照を提案
- **CI / audit**: `cog.consensus=hold` を見て自動 block

#### 実装フェーズ

- v0.8-meta (本セッション): `Annotation` 型 + `BriefResult.annotations` + 4〜5 component の自然な emit
- 後段: 残り応答型へ展開、consumer-side helper (llove 側で読み取る utility)

---

### 次に着手するなら

1. **VRB-04 Premortem Generator** — BlackHatLens を拡張、failure scenarios を tabular 出力
2. **VRB-05 Eval Spec Editor** — Brief に optional `metrics_registry` フィールド追加
3. **VRB-06 Dual Spec Writer** — `BriefRenderer` (5 modes) を別モジュールで

---

## ORG-FX 追補 — Qwen 商用障壁とロードマップ加速 (2026-05-17 9 回目)

**ユーザー指示**: 「qwen 依存からの脱却のための要件定義も追々進めたいですね。
商用利用の障壁になりそうなので。」

### Qwen 依存の商用利用障壁 (具体化)

1. **ライセンス変更リスク** — Qwen2.5 系は現在 Apache 2.0 ベースだが、Qwen3 系で
   ライセンス変更の可能性。長期商用契約では将来コミットメントが取れない
2. **配布権利の不確実性** — エンタープライズ on-prem 配信時に Qwen バイナリ同梱
   の権利・サポート範囲が不明瞭。法務リスク
3. **地政学的調達リスク** — Alibaba 開発元への依存は一部企業の調達ポリシー
   (中国製 AI モデル禁止条項) に抵触する可能性
4. **品質ドリフト** — `vs_other_llms.json` で実測: qwen2.5:7b は日本語 Brief に
   中国語で応答する事例 → 商用品質保証が困難
5. **on-prem 性能の天井** — qwen2.5:14b でも cloud (Claude Haiku) に品質速度
   両面で劣る (`vs_cloud.json`: 75s/0.37 vs 3s/0.65)

### ORG-FX ロードマップの再優先付け (商用障壁解消視点)

| Stage | 元優先度 | 改訂優先度 | 理由 |
|---|---|---|---|
| Stage A (LLM 凍結、周辺差別化) | 短期 | 維持 | 既に達成済 |
| **Stage B (LoRA specialised adapter)** | 中期 1 | **昇格 HIGH** | 「Qwen を素材として使うが、配布物は llive 専用 adapter」と切り分けることで商用契約上のリスクを限定可能 |
| **Stage C (Distillation で小型化)** | 中期 2 | **昇格 HIGH** | qwen2.5:14b → llive-7b 蒸留すると配布物は llive 独自モデル。Qwen 系列名から完全切り離し |
| Stage D (Transformer block 置換) | 長期 1 | 維持 | 学術的差別化、商用は B/C で先に解決 |
| Stage E (Mamba/RWKV 系) | 長期 2 | 維持 | 学術ロードマップ、商用契約には Stage C で十分 |

### 追加要件 ORG-09 / 10 (2026-05-17 9 回目)

| FR | 名前 | 概要 | 優先度 |
|---|---|---|---|
| **ORG-09** | **License Audit Pipeline** | 使用 OSS LLM すべてのライセンス・配布権利・redistribution 範囲を機械監査。pyproject に license metadata 必須、CI で逸脱検出 | **HIGH** |
| **ORG-10** | **Model Abstraction Boundary** | LLMBackend Protocol を「Qwen 固有挙動に依存しない」よう契約強化。tokenizer 差異・stop sequence 差異を吸収。Mistral / Llama / Gemma / 自前モデルへ即時 swap 可能 | **HIGH** |
| **ORG-11** | **Rule-based → llive-native LLM 進化パス** | 現状の rule-based fallback (`Observation about X — novel territory` 等のテンプレ) を、段階的に「on-prem 想定の llive 独自 LLM」へ昇格させる経路 (下記参照) | **MED (長期)** |

### ORG-11 Rule-based → llive-native LLM 5 段階進化

**ユーザー指示 (2026-05-17)**: 「rule-based をいつか on-premise を想定した独自
LLM みたいな形に出来るようにしたいです。」

| Step | 名称 | 概要 | サイズ目安 |
|---|---|---|---|
| **R0** | Rule-based template (現状) | `FullSenseLoop` の LLM 無し時のテンプレ生成 | 0 params |
| **R1** | Embedding-only LM | 1〜100M params の小型 embedding/classifier。decision 分類 / confidence 推定のみ | 1〜100M |
| **R2** | Tiny generative LM | 100M〜1B params。OKA essence 抽出 / TRIZ 候補列挙の deterministic 強化 | 100M〜1B |
| **R3** | Llive-distilled 7B | qwen2.5:14b → llive-7b 蒸留 (ORG-08)、教師 = OKA/COG/VRB の構造化出力 | 7B |
| **R4** | Llive-native architecture | Transformer block 置換 / Mamba / RWKV (ORG-01, ORG-05)。完全独自 | 任意 |

### ORG-11 設計原則

1. **どの step でも上位互換** — R0 で動いていた Brief が R3 でも動く (LLMBackend Protocol 維持)
2. **配布物の clean separation** — R3 以降は配布物に Qwen weights を含めない (ORG-09 license audit と整合)
3. **rule-based を捨てない** — R4 でも rule-based fallback は残す (CI / 単体テスト / debug)
4. **R1 で 1 度成果** — embedding-only でも 「LLM 不在時の decision 品質」を改善でき
   る部分があるので、ここで一度商用リリース候補 (on-prem 完全独自 mini-llive)
5. **R3 がメイン商用エディション** — qwen 由来であることは認めるが、配布物は llive 独自
   = 商用契約障壁を最小化 (Stage C の本命)

### ORG-11 評価指標

- **R0 baseline coverage** = 0.567 (現状実測、`vs_cloud.json` の echo 効果込)
- **R1 target**: coverage ≥0.50 / latency < 50ms / weight < 100 MB
- **R2 target**: coverage ≥0.55 / latency < 200ms / weight < 1 GB
- **R3 target**: coverage ≥0.60 / latency < 5 s / weight < 8 GB (cloud Haiku の 80% に到達)
- **R4 target**: coverage ≥0.65 / 独自 architecture / 配布物完全 OSS

### 評価指標 (Qwen 依存度の計測)

- **Vendor Lock-in Score** = (Qwen 固有 API 呼び出し数) / (全 LLM 呼び出し数)
- **Replaceability Test** = Mistral 7B / Llama 3.1 8B / Gemma 2 9B などで同じ Brief を動かし、coverage が ±15% 内に収まるか
- **Distribution Cleanness** = 配布物 (PyPI / wheel) に Qwen weights / tokenizer が含まれない (verified by `audit_independence` の拡張)

→ **Stage C 完了時点で「llive は Qwen 由来であることは認めるが、配布物は llive 独自」と
言える状態**を目指す。これで商用契約の障壁を最小化。

---

## VLM-FX — Vision Language Model Framework (将来要件、2026-05-17 9 回目)

**ユーザー指示**: 「私の専門は画像処理や三次元計測なので、将来的に VLM としての
機能も増やしたいです。その際は簡単な図形の判断などからテストが必要でしょうね。」

**動機**: ユーザーの専門領域 (画像処理 / 三次元計測) を活かす差別化軸。MCP-3D
プロジェクトとの統合先候補。既存資産との接続:

* `AnthropicBackend.supports_vlm = True` (画像入力対応済)
* `OllamaBackend` で `llama3.2-vision` / `llava:7b` が利用可 (`ollama list` 確認済)
* `mcp-3d` (別プロジェクト) に SH-VQ tokenizer などの実装あり

### 要件 VLM-01〜10 (将来実装、Phase 5+)

| FR | 名前 | 優先度 |
|---|---|---|
| **VLM-01** | Visual Stimulus 型 — `Stimulus.image_refs` (URI / bytes / numpy array) を追加 | HIGH |
| **VLM-02** | Shape Recognition Bench — 簡単な図形 (○△□ / 立方体 / 球) の判定精度テストハーネス | HIGH (テストから着手) |
| **VLM-03** | 3D Geometry Brief — point cloud / depth map を Brief 経由で処理 | MED |
| **VLM-04** | VLM Verifier (MathVerifier の VLM 版) — 「画像内のオブジェクトを deterministic に grade」できる検証層 | MED |
| **VLM-05** | mcp-3d 統合 — SH-VQ tokenizer + Gaussian Splatting weights を Stimulus に embed | MED |
| **VLM-06** | Spatial Reasoning Brief — 「物体 A は物体 B の左にあるか」等の空間推論ベンチ | MED |
| **VLM-07** | Camera Calibration Brief — 内部・外部パラメータの推定 / 検証 | MED |
| **VLM-08** | Surface Reconstruction Brief — 点群 → メッシュ生成の品質評価 | LOW |
| **VLM-09** | Multi-modal Notebook — OKA-04 ReflectiveNotebook に画像エビデンス保存 | LOW |
| **VLM-10** | VLM Annotation Channel — Annotation.value に image_uri を含められる拡張 | LOW |

### 着手戦略 (実装ではなく要件のみ)

1. **VLM-02 (Shape Recognition Bench) を最初に作る** — 簡単な図形画像 (matplotlib で生成)
   を Claude Haiku / Llava / Llama-vision で判定させ deterministic に grade
2. このベンチを **正答率指標** として、VLM-01 Visual Stimulus 型実装時の回帰検出に使う
3. mcp-3d 統合 (VLM-05) は別プロジェクト依存度が高いので、IND-FX 原則に従い
   optional dependency として隔離
4. ユーザー専門領域 (三次元計測) を強みとして、VLM-06 / VLM-07 で
   **Claude / GPT-4V も難しい spatial reasoning 領域**を狙う差別化

### 評価指標

- Shape Recognition Accuracy: ○△□ など 10 種類で正答率 ≥80%
- Spatial Reasoning F1: 「左/右/前/後」判定で F1 ≥0.7
- 3D Reconstruction RMSE: 既知形状で表面誤差 < 1 mm

---

*Requirements defined: 2026-05-13*
*Last updated: 2026-05-17 — ORG-09/10 (Qwen 商用障壁解消) + VLM-FX (VLM 将来要件 10 件、ユーザー専門領域 画像処理/三次元計測)*
