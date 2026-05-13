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

**Coverage:**
- v1 (Phase 1) requirements: 16 total
- v2 (Phase 2) requirements: 9 total
- v3 (Phase 3) requirements: 12 total
- v4 (Phase 4) requirements: 9 total
- Mapped to phases: 46 / 46 ✓

---
*Requirements defined: 2026-05-13*
*Last updated: 2026-05-13 after initialization*
