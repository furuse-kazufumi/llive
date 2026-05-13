# Phase 2: Adaptive Modular System - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 02-CONTEXT.md.

**Date:** 2026-05-13
**Phase:** 02-adaptive
**Mode:** `--auto` (Max plan autonomy)
**Areas discussed:** Graph backend / Parameter memory / Bayesian surprise / Consolidation / Phase transition / ConceptPage & Wiki Compiler / Ingest CLI / Block Container extensions / llove integration / Package + tests

---

## Graph Backend (MEM-05)

| Option | Description | Selected |
|---|---|---|
| Kùzu (embedded analytical) | OLAP 強い・ローカル単一ファイル・Cypher サブセット | ✓ |
| Neo4j | 機能豊富、Server 必須・依存重 | |
| NetworkX + SQLite | 軽量だが規模が出ない | |

**Selected:** Kùzu (D-01)
**Rationale:** STATE.md open question で既に推奨されており、依存軽量。Bipartite schema (MemoryNode + MemoryEdge) で Phase 2 開始。

---

## Parameter Memory Backend (MEM-06)

| Option | Description | Selected |
|---|---|---|
| Filesystem (.safetensors) + DuckDB index | 単純・SHA256 検証可能・llmesh ファミリーと統一感 | ✓ |
| Dedicated DB (e.g., Weaviate) | 高機能だが複雑 | |
| Pure DuckDB BLOB | クエリ重い、移行困難 | |

**Selected:** Hybrid filesystem + DuckDB index (D-04)
**Adapter formats:** Phase 2 で LoRA 優先、IA3 と prefix tuning は interface 予約 (D-05)
**API:** HuggingFace PEFT (`peft>=0.10`) を optional extra に追加 (D-07)

---

## Bayesian Surprise (MEM-07)

| Option | Description | Selected |
|---|---|---|
| Online running mean+var (Welford) | 軽量・interpretable・依存無し | ✓ |
| Particle filter | 高精度・実装重い | |
| Variational inference | 高精度・依存重 | |

**Selected:** Welford-based gate (D-08)
**Threshold:** EMA decay で `θ_t = μ + k·σ`, k=1.0 デフォルト (D-10)
**Phase 1 SurpriseGate は後方互換のため残す (D-09)**

---

## Consolidation Cycle (MEM-08, LLW-02)

| Option | Description | Selected |
|---|---|---|
| APScheduler + HDBSCAN + Anthropic Haiku | 安定 cron/interval、自動 cluster 数、コスト見通し済 | ✓ |
| Cron-style (system cron 連携) | OS 依存 | |
| 簡易 loop (`asyncio` task) | 永続化弱い | |

**Selected:** APScheduler + HDBSCAN + Claude Haiku (D-12, D-14, D-15)
**Cycle:** Replay Select (surprise-weighted sample, 200 events) → Cluster (HDBSCAN) → Compile (LLM 判定で Page CRUD) → Link (structural edges) → Provenance (D-13, D-16)

---

## Memory Phase Transition (MEM-09)

| Option | Description | Selected |
|---|---|---|
| 5 段階 (hot/warm/cold/archived/erased) + 時間ベース判定 | シンプル・cron で daily 評価 | ✓ |
| Access-frequency-based (LRU/LFU) | 高頻度参照に頑健、設計重い | |
| Hybrid (時間 + surprise) | 表現力高い、ルール複雑 | |

**Selected:** 5 段階 + 時間ベース + surprise 低い entry の archive 条件付き (D-17, D-18)
**GDPR 対応:** erased で payload + embedding 削除、metadata のみ残す (D-19)

---

## ConceptPage & Wiki Compiler (LLW-01, LLW-02, LLW-03)

| Option | Description | Selected |
|---|---|---|
| Structural memory の MemoryNode 拡張 (concept 種別) | 既存 graph 活用、エッジ自然 | ✓ |
| 別 table | 分離して見通し良いが、graph link が手間 | |
| In-place semantic memory 拡張 | 複雑、Phase 1 後方互換性が崩れる | |

**Selected:** MemoryNode(concept) 拡張 (D-21)
**Markdown export:** `D:/data/llive/wiki/<concept_id>.md` も並行生成 (D-22)
**page_type:** 4 種を Phase 2 で実装 (`domain_concept`, `experiment_record`, `failure_post_mortem`, `principle_application`), JSON Schema で検証 (D-23, D-24)

---

## External Source Ingest (LLW-06)

| Option | Description | Selected |
|---|---|---|
| typer subcommand + 5 type (text/markdown/pdf/arxiv/url) | 段階的に拡張可、core 依存最小 | ✓ |
| MCP server 経由 | 過大 | |
| llmesh I/O Bus 経由 | Phase 4 INT-01 と被る | |

**Selected:** CLI subcommand 直結 (D-25)
**Chunking:** 500 tokens / chunk、ingest 後に Wiki Compiler を非同期 trigger (D-26)
**Optional extras:** `[ingest]` (`pypdf`, `arxiv`, `readability-lxml`) を新規追加 (D-27)

---

## Block Container Extensions (BC-04, BC-05)

| Option | Description | Selected |
|---|---|---|
| HF PEFT 経由 adapter / lora_switch sub-block + nested_container 再帰展開 | PEFT 互換、最小実装 | ✓ |
| 自前 LoRA merge 実装 | 移植性低、メンテ重 | |
| ContainerSpec 設計大改修 | Phase 1 互換性が崩れる | |

**Selected:** HF PEFT thin wrapper (D-28, D-29)
**nested_container:** Phase 1 で schema 予約済を実行可能化、max depth=3、循環参照検出 (D-30, D-31)

---

## llove TUI Integration (OBS-03, OBS-04)

| Option | Description | Selected |
|---|---|---|
| JSONL ファイル経由 + (optional) Phase 4 で IPC | 段階的・llove リリース速度に独立 | ✓ |
| UNIX socket realtime push (Phase 2 から) | 複雑、Phase 2 範囲広がる | |
| 直接 Python import 結合 | 双方向結合で疎結合崩れる | |

**Selected:** JSONL ファイル → llove tail viewer (D-32, D-34)
**llove 側責務:** RouteTraceViewer / MemoryLinkVizPanel / BWTDashboard を llove リポジトリで実装 (D-33)
**BWT:** 連続タスク学習中の擬似 BWT を実装、厳密 GEM/A-GEM 風は Phase 3 (D-35)

---

## Package + Tests

| Option | Description | Selected |
|---|---|---|
| 既存 8 層に memory/wiki 拡張 + 新規 cli/wiki + integration test 重視 | 後方互換、testing_strategy 整合 | ✓ |
| 別パッケージ (`llive-wiki`) として切出 | family fragmentation のリスク | |
| ConceptPage を別 microservice | Phase 2 では過剰 | |

**Selected:** 既存ツリー内拡張 (D-36)
**Dependencies:** core +2, `[torch]` +2, `[ingest]` +3, `[llm]` +1 (D-37)
**後方互換:** Phase 1 Pipeline / Executor / 各 backend 変更なし (D-38)
**Tests:** Integration 重点、Anthropic 無くても CI で mock 強制 (D-39, D-40)

---

## Claude's Discretion

- Kùzu Cypher 文法 / schema 命名
- DuckDB adapter_index index 戦略
- APScheduler trigger persistence backend
- HF PEFT 経由 vs 自前 LoRA merge の最終判断
- Wiki Markdown export テンプレート
- pyproject.toml dependency 最小バージョン
- テスト fixture / mock 細部

## Deferred (Phase 2 スコープ外)

40+ 項目を 02-CONTEXT.md `<deferred>` セクション参照。代表：
- Particle filter / variational inference Bayesian (Phase 3+)
- AI candidate generation / Static Verifier / shadow eval (Phase 3)
- TRIZ 自動推論 / ConceptPage 矛盾検出 (Phase 3)
- Wiki diff as ChangeOp (Phase 3 LLW-05)
- Signed adapter / Quarantine zone / llmesh sensor (Phase 4)
- llove F16 Candidate Arena (Phase 4)
