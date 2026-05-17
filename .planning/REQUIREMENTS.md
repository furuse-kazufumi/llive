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
| MATH-01 | Phase 10 | Pending | **1st** |
| MATH-02 | Phase 10 | **Implemented** (2026-05-17) | **2nd** |

**MATH-02 実装ノート (2026-05-17)**: `src/llive/math/verifier.py` に `MathVerifier`
+ `VerificationResult` を新規実装。3 メソッド (check_equivalence / check_implication
/ check_satisfiable) を提供し、Sympy で代数等価、Z3 で含意・SAT/UNSAT を決定論的に
検証。**トレーサビリティ重視設計**: `MathVerifier(ledger=...)` で attach すると
全 check が ledger に `math_verified` event として自動記録、`BriefLedger.trace_graph()`
の `evidence_chain` に `kind="math"` (+ `check_kind`) として COG-03 と統合される。
sympy>=1.12, z3-solver>=4.13 を required dependency に昇格。テスト 16 件追加
(verifier 12 + traceability 4)、1034 → 1052 PASS / 回帰ゼロ。
| MATH-05 | Phase 10 | Pending | **3rd** |
| MATH-08 | Phase 10 | Pending | **4th (差別化)** |
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
- Mapped to phases: 100 / 100 ✓

*Requirements defined: 2026-05-13*
*Last updated: 2026-05-17 — v2.0-core ORG-FX (Originality Framework, Qwen 依存からの離脱 5 段階)*
