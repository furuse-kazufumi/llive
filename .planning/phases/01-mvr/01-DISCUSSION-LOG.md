# Phase 1: MVR - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 01-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 01-mvr
**Mode:** `--auto` (Max plan autonomy — recommended defaults auto-selected)
**Areas discussed:** Base Model / Schema Validation / Block Container Engine / Memory Backends / Routing / Candidate Evaluation / Observability / TRIZ Resource / CLI Framework / Testing Strategy

---

## Base Model & Inference Adapter

| Option | Description | Selected |
|---|---|---|
| HF transformers only | `transformers.AutoModelForCausalLM` 単独ラッパー、最小依存 | ✓ |
| HF + vLLM Adapter | vLLM 並走で高速推論、依存追加 | |
| HF + TGI Adapter | TGI 連携、サーバ前提 | |

**Selected:** HF only (D-01)
**Notes:** vLLM / TGI は interface 予約のみ、実装は Phase 2+。Phase 1 は "動くこと" が最優先のため依存最小化。

| Option | Description | Selected |
|---|---|---|
| Qwen2.5-0.5B (dev default) + Phi-3.5-mini | CPU で動く軽量モデルで CI 高速化 | ✓ |
| TinyLlama 1.1B | CI 軽量だが性能弱い | |
| Qwen2.5-7B 即採用 | GPU 制約厳しい | |

**Selected:** Qwen2.5-0.5B + Phi-3.5-mini (D-02)
**Notes:** STATE.md の Open Question で推奨されていた構成を採用。7B 系テンプレートは specs/templates/ に維持して将来動作確認可能性を残す。

---

## Schema Validation Library

| Option | Description | Selected |
|---|---|---|
| jsonschema + pydantic v2 | JSON Schema source of truth + pydantic で type-safe | ✓ |
| pydantic v2 only | コード集中、JSON Schema は generate | |
| fastjsonschema | 高速だが Draft 2020-12 対応不完全 | |

**Selected:** jsonschema + pydantic v2 (D-05, D-06)
**Notes:** docs/yaml_schemas.md が Draft 2020-12 を前提に設計されているため jsonschema 必須。pydantic は内部 model 構築用。

---

## Block Container Engine

| Option | Description | Selected |
|---|---|---|
| Pipes & Filters + Chain of Responsibility | docs/architecture.md §3 と整合 | ✓ |
| 単純 list iteration | 簡単だが拡張時に CoR 化が必要 | |
| プラグイン executor (各 sub-block が自前 next 呼び出し) | 過度に分散 | |

**Selected:** Pipes & Filters + CoR (D-08)
**Notes:** ConditionSpec の Phase 1 サポートは `surprise_gt` のみ。他は schema 予約。

**Sub-block 実装範囲:**
- pre_norm / causal_attention / memory_read / ffn_swiglu / memory_write (5 種) — BC-02 最低要件達成 (D-09)

**Plugin registry:**
- entry-points + 動的 import 両対応、Phase 1 は組み込みのみ登録 (D-10)

---

## Memory Backends

### Semantic memory

| Option | Description | Selected |
|---|---|---|
| Faiss + JSONL row store | ローカル軽量、永続化要件薄 | ✓ |
| Qdrant | 永続化・REST API、依存重い | |
| pgvector | PostgreSQL 前提、Phase 1 では過大 | |
| Chroma | persistent client が安定、依存中 | |

**Selected:** Faiss (D-11)
**Notes:** Phase 2 で Qdrant 追加を STATE.md で推奨されている。

### Episodic memory

| Option | Description | Selected |
|---|---|---|
| DuckDB | 列指向 + JSON 列 + 時系列クエリ強い | ✓ |
| SQLite | 標準、JSON 弱い | |
| JSONL append-only | 軽量だが解析弱 | |
| Parquet | 解析強いが追記弱 | |

**Selected:** DuckDB (D-12)
**Notes:** ROADMAP P1.3 で示唆済。

### Embedding model

| Option | Description | Selected |
|---|---|---|
| sentence-transformers all-MiniLM-L6-v2 | ローカル 80MB / 384 dim / 安定 | ✓ |
| OpenAI text-embedding-3-small | API 依存・コスト発生 | |
| BGE-small-en | 性能良いが依存追加 | |
| 主 LLM hidden state 再利用 | 性能不安定 | |

**Selected:** all-MiniLM-L6-v2 (D-13)

### Provenance

| Option | Description | Selected |
|---|---|---|
| 各 row の JSON column に埋め込む | join 不要、シンプル | ✓ |
| 別 provenance table を join | 正規化、Phase 1 では過大 | |
| Sidecar JSONL | 整合性保証弱い | |

**Selected:** Inline JSON column (D-14)
**Notes:** signed_by / signature は Phase 4 SEC-02 で実装、Phase 1 は空文字許容。

### Surprise gate

| Option | Description | Selected |
|---|---|---|
| Embedding nearest-neighbor cosine distance | 単純・動作確実 | ✓ |
| Perplexity baseline | LLM 呼び出しコスト高 | |
| 学習済み surprise head | 学習が必要、Phase 3+ | |

**Selected:** Cosine distance (D-15)
**Notes:** Bayesian (mean+variance) 化は Phase 2 MEM-07。Phase 1 のデフォルト θ = 0.3。

---

## Routing

| Option | Description | Selected |
|---|---|---|
| YAML 宣言 (specs/routes/) | ContainerSpec と同じ declarative 方針 | ✓ |
| Python decorator | コード集中、再起動必須 | |
| dict-based config | 柔軟だが検証薄い | |

**Selected:** YAML (D-16)

**2 経路実装:** `fast_path_v1` + `adaptive_reasoning_v1` (D-17)
**Explanation log:** `D:/data/llive/logs/router.jsonl` に JSON 1 行 / request (D-18)

---

## Candidate Evaluation

| Option | Description | Selected |
|---|---|---|
| 4 ChangeOp (insert/remove/replace/reorder) | 機械的 apply/invert で構造変更最小セット | ✓ |
| 7 ChangeOp 全て実装 | 過大、Phase 1 では不要 | |
| 1〜2 ChangeOp のみ | Success Criteria 5 を満たせない | |

**Selected:** 4 ChangeOp (D-20)
**Notes:** add_routing_tag / set_adapter / set_memory_policy は schema 予約のみ。

| Option | Description | Selected |
|---|---|---|
| 内蔵 toy dataset (10〜50 prompts) | Phase 1 "動くこと" 重視、依存軽い | ✓ |
| lm-evaluation-harness 一部 | 依存重く Phase 1 を阻害 | |
| HellaSwag / GSM8K | 評価コスト高 | |

**Selected:** Toy dataset (D-21)

---

## Observability

| Option | Description | Selected |
|---|---|---|
| structlog + JSON formatter | 軽量・context binding 標準 | ✓ |
| loguru | 良いが context binding 弱い | |
| stdlib logging + JSON | DIY 必要 | |
| OpenTelemetry | 過大、Phase 4 | |

**Selected:** structlog (D-23)

**Metrics:** forgetting_proxy / pollution_rate / latency_p50_p95 / route_entropy / dead_subblock_rate を DuckDB に append (D-25)

---

## TRIZ Resource

| Option | Description | Selected |
|---|---|---|
| YAML lazy load API | 既存 specs/resources を素直に読む | ✓ |
| YAML eager load on import | import 重くなる | |
| SQLite embedded | データ整形コスト高、検索要件薄 | |

**Selected:** Lazy load (D-26)
**Notes:** Phase 1 は read-only API のみ。Phase 3 で Contradiction Detector / Principle Mapper 等を実装。

---

## CLI Framework & Package Structure

| Option | Description | Selected |
|---|---|---|
| typer | 型ヒント自然・llmesh ファミリーで採用 | ✓ |
| click | 成熟だが型対応薄 | |
| argparse | 標準だが UX 弱 | |
| cyclopts | 新興 | |

**Selected:** typer (D-27)

**Subcommand 体系:** run / bench / memory / schema / route / triz (D-27)

**Package 構成:** 8 層対応 flat package (`src/llive/{cli,orchestration,core,container,memory,evolution,observability,schema,triz}/`) (D-28)

---

## Testing Strategy

| Option | Description | Selected |
|---|---|---|
| pytest + pytest-cov + hypothesis | testing_strategy.md の Phase 1 重点と整合 | ✓ |
| unittest | 標準だが property-based 不在 | |

**Selected:** pytest + pytest-cov + hypothesis (D-30)

**Conformance test:** sub-block 5 種に対してのみ強制 (D-31)

---

## Claude's Discretion

以下は実装中に Claude が判断（CONTEXT.md には固定しない）：

- 各 sub-block の具体的な tensor 操作実装（HF 内蔵を呼ぶ vs 自前 RMSNorm 等）
- DuckDB / Faiss の index タイプ・ファイル分割戦略
- logging の verbose レベル細部
- pyproject.toml の dependency 最小集合
- テストの fixtures 構造 / mock 実装

---

## Deferred Ideas

実装中に Phase 1 スコープ外と判断したアイデア（将来 phase へ）：

- vLLM / TGI Adapter — Phase 2 以降
- adapter / lora_switch sub-block — Phase 2 (BC-04)
- nested_container — Phase 2 (BC-05)
- Structural memory (graph) — Phase 2 (MEM-05)
- Parameter memory (adapter store) — Phase 2 (MEM-06)
- Consolidation cycle — Phase 2 (MEM-08)
- llove TUI 連携 — Phase 2 (OBS-03)
- AI candidate generation — Phase 3 (EVO-03)
- Static Verifier (Z3/Lean) — Phase 3 (EVO-04)
- lm-evaluation-harness 連携 — Phase 2+
- OpenTelemetry / 分散トレース — Phase 4
- Ed25519 signing / signed adapter — Phase 4 (SEC-02)
- TRIZ 自動推論 (Contradiction Detector / Principle Mapper / 9-Window / ARIZ) — Phase 3 (TRIZ-02〜06)
