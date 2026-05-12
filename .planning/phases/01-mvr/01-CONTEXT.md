# Phase 1: Minimal Viable Research Platform (MVR) - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning
**Mode:** `--auto` (Max plan autonomy — Claude が gray area を抽出して推奨デフォルトを採用)

<domain>
## Phase Boundary

Phase 1 が delivery するもの = **CLI 1 本で完結する最小研究基盤**：

1. `llive run --template specs/templates/qwen2_5_0_5b.yaml --prompt "..."` が動く
2. 1 つの ContainerSpec を読み込み、5 種類以上の sub-block を順序実行できる
3. semantic + episodic memory に provenance 付きで read/write できる
4. rule-based router が 2 経路以上を選択し explanation log を JSON で出力する
5. CandidateDiff を読み込んで baseline vs candidate の A/B ベンチが回る
6. route trace + memory link を構造化 JSON で取得できる

**この phase に含まれないもの**（roadmap 上の他 phase へ）：
- structural memory (graph) / parameter memory (adapter store) — Phase 2
- consolidation cycle / memory phase transition — Phase 2
- llove TUI 連携 — Phase 2
- AI candidate generation / Static Verifier / shadow eval — Phase 3
- TRIZ 自動推論 (Contradiction Detector / Principle Mapper / ARIZ) — Phase 3
- security / signed adapter / quarantine zone — Phase 4
- llmesh sensor bridge / production PoC — Phase 4

</domain>

<decisions>
## Implementation Decisions

### D-Base: Base Model & Inference Adapter (CORE-01, CORE-02)

- **D-01:** **`BaseModelAdapter`** は HuggingFace `transformers.AutoModelForCausalLM` をラップする `HFAdapter` を MVR の唯一実装とする。vLLM / TGI Adapter は interface のみ予約、実装は Phase 2+ に倒す。
- **D-02:** 開発・CI 用デフォルトモデルは **`Qwen/Qwen2.5-0.5B`**（高速 iteration / CPU でも動く）。中性能テストは `microsoft/Phi-3.5-mini-instruct`。7B 系 (`Qwen2.5-7B`, `Llama-3.1-8B`, `Mistral-7B-v0.3`) のテンプレートは `specs/templates/` に維持するが Phase 1 では実機実行を必須化しない（GPU 制約のため）。
- **D-03:** `BaseModelAdapter` の I/F は `generate(prompt: str, max_new_tokens: int, **kwargs) -> GenerationResult` を最小公約数とし、`hidden_states` / `attentions` の取り出しは optional kwargs (`return_hidden_states=True`) で expose する（memory write/router が hidden state を使うため）。
- **D-04:** tokenizer / context_length / dtype / device_map の差異は `AdapterConfig` dataclass に集約。テンプレート YAML の `model:` セクションを 1 対 1 で mapping。

### D-Schema: YAML / JSON Schema 検証 (BC-03)

- **D-05:** Schema validation は **`jsonschema` ライブラリ**（PyPI `jsonschema>=4.21`、Draft 2020-12 完全対応）を採用。`docs/yaml_schemas.md` で定義済の 3 schema (`container-spec.v1`, `subblock-spec.v1`, `candidate-diff.v1`) を `specs/schemas/*.json` に展開する。
- **D-06:** Python 内部表現は **`pydantic v2`** dataclass — YAML → jsonschema validate → pydantic model 構築の 2 段。pydantic で type-safe な実装を保証しつつ、source of truth は JSON Schema (外部ツールから検証可能)。
- **D-07:** schema バージョン互換性は `schema_version: 1` のみを Phase 1 でサポート。`llive schema migrate` コマンドは骨格のみ用意して Phase 3+ で本格実装。

### D-BC: Block Container Engine (BC-01, BC-02)

- **D-08:** `BlockContainerExecutor` は **Pipes & Filters + Chain of Responsibility** で実装（`docs/architecture.md` §3 に整合）。`ExecutionPlan` (sub-block 順序 + config) → `execute(input_state) -> output_state` の単純フロー。条件付き分岐 (`ConditionSpec`) は Phase 1 では `surprise_gt` のみ実装。`task_tag` / `route_depth_lt` / `all_of` / `any_of` は schema レベルで予約のみ。
- **D-09:** **Phase 1 で実装する sub-block 5 種**（BC-02 の最低要件）：
  1. `pre_norm` — RMSNorm（pytorch.nn.functional.rms_norm）
  2. `causal_attention` — HF model の internal attention を呼ぶラッパー（再実装はしない）
  3. `memory_read` — semantic + episodic を query して top_k 取得
  4. `ffn_swiglu` — HF model 内蔵 FFN を呼ぶラッパー
  5. `memory_write` — surprise gate を通って write
- **D-10:** sub-block plugin registry は **entry-points based** （`pyproject.toml` の `[project.entry-points."llive.subblocks"]`）+ 動的 import 両対応。Phase 1 は組み込み 5 種類を `llive.subblocks.builtin` から `register()` で登録する。外部 plugin discovery は Phase 2+。

### D-Mem: Memory Backends (MEM-01, MEM-02, MEM-03, MEM-04)

- **D-11:** **Semantic memory** backend は **Faiss (`faiss-cpu`)** + JSONL row store のハイブリッド。Faiss IndexFlat (cosine 用に L2-normalize) + 各 row を `D:/data/llive/memory/semantic/rows.jsonl` (provenance 含む) に append。理由: 永続化要件薄 / 依存最軽量 / Phase 2 で Qdrant 追加が容易。
- **D-12:** **Episodic memory** backend は **DuckDB**（ROADMAP P1.3 で示唆済）。`D:/data/llive/memory/episodic.duckdb` に `events` テーブル: `(event_id PK, ts TIMESTAMP, content TEXT, metadata JSON, provenance JSON, embedding BLOB)`. 時系列クエリ / SQL ad-hoc 解析 / JSON 列が強い。
- **D-13:** **Embedding model** は **`sentence-transformers/all-MiniLM-L6-v2`** (384 dim, ローカル, 80MB, 数十 ms/sentence)。HF model の hidden state 再利用案は性能不安定なので Phase 2+ に倒す。embedding 計算は `MemoryEncoder` クラスに分離（差し替え可能）。
- **D-14:** **Provenance** は dataclass `Provenance(source_type, source_id, signed_by, signature, derived_from, confidence, created_at)` を作り、JSON 化して各 memory row の `provenance` 列に埋め込む。`signed_by` / `signature` は Phase 1 では **空文字を許容**（Phase 4 SEC-02 で Ed25519 を実装）。
- **D-15:** **Surprise gate (MEM-04)** は **embedding nearest-neighbor cosine distance** ベース。`surprise = 1 - max(cosine_sim(new, existing))` で 0〜1 normalized score。Phase 1 の閾値 θ はデフォルト `0.3` (config 可変)。Bayesian (mean+variance) 化は Phase 2 MEM-07。

### D-Router: Routing (RTR-01, RTR-02)

- **D-16:** rule-based router は **YAML 宣言** (`specs/routes/default.yaml`) + Python `RouterEngine` クラス。最小スキーマ:
  ```yaml
  schema_version: 1
  routes:
    - container: fast_path_v1
      when: {prompt_length_lt: 256}
    - container: memory_heavy_v1
      when: {task_tag: long_context}
    - container: adaptive_reasoning_v1   # fallback
  ```
- **D-17:** Phase 1 で実装する **2 経路**は `fast_path_v1` (短プロンプト, sub-block: pre_norm→causal_attention→ffn_swiglu) と `adaptive_reasoning_v1` (memory_read + memory_write 入り)。`docs/architecture.md` §2 の例を踏襲。
- **D-18:** Router の **explanation log** は JSON 1 行 per request:
  ```json
  {"request_id":"...","timestamp":"...","selected_container":"...","matched_rule":"...","candidates":[{"container":"...","matched":true|false,"reason":"..."}],"prompt_features":{"length":N,"task_tag":"..."}}
  ```
  ログ出力先は `D:/data/llive/logs/router.jsonl` (append-only)。

### D-Evo: Candidate Evaluation (EVO-01, EVO-02)

- **D-19:** **ChangeOp の apply / invert** は `docs/yaml_schemas.md` §5 の表を機械的に実装。各 ChangeOp class は `apply(container_spec) -> container_spec'` と `invert() -> ChangeOp` を持つ。`property-based test` (`hypothesis`) で apply→invert→apply 同一性を保証。
- **D-20:** Phase 1 で実装する ChangeOp は **4 種**（roadmap 上の最小セット）：`insert_subblock`, `remove_subblock`, `replace_subblock`, `reorder_subblocks`。`add_routing_tag` / `set_adapter` / `set_memory_policy` は schema 予約のみ・apply 実装は Phase 2+。
- **D-21:** **A/B ベンチ** は内蔵 toy dataset (`tests/data/mvr_bench/`、10〜50 prompts) で実行。メトリクス: (1) generation perplexity (baseline model) (2) memory hit rate (3) latency p50/p95 (4) route entropy。`lm-evaluation-harness` 連携は Phase 2+ に倒す（依存重く、Phase 1 の "動くこと" を阻害するため）。
- **D-22:** ベンチ runner CLI: `llive bench --baseline <container_id> --candidate <diff.yaml> --dataset <path>` → 結果を `D:/data/llive/bench/<timestamp>/results.json` に出力。

### D-Obs: Observability (OBS-01, OBS-02)

- **D-23:** ロギング・トレースは **`structlog`** + JSON formatter。`run_id` / `request_id` / `route_id` / `candidate_id` を context binding。`stdout` + `D:/data/llive/logs/structured.jsonl`。OpenTelemetry / span 化は Phase 4。
- **D-24:** route trace + memory link の構造化出力 schema（OBS-01）：
  ```json
  {
    "request_id":"...","container":"...",
    "subblocks":[{"name":"...","duration_ms":N,"output_shape":[..]}],
    "memory_accesses":[{"op":"read|write","layer":"semantic|episodic","hits":[{"id":"...","score":...}]}],
    "metrics":{"latency_ms":N,"surprise":...,"route_entropy":...}
  }
  ```
- **D-25:** 基本メトリクス (OBS-02): `forgetting_proxy` (Phase 1 では prompt-recall accuracy 単純実装) / `pollution_rate` (memory write が surprise gate を通った比率) / `latency_p50_p95` / `route_entropy` (Shannon) / `dead_subblock_rate` (実行されなかった sub-block 数 / 総数)。DuckDB の `metrics_db.duckdb` に append。

### D-TRIZ: TRIZ Resource (TRIZ-01)

- **D-26:** `specs/resources/triz_principles.yaml`, `triz_contradiction_matrix.yaml`, `triz_attributes.yaml` を **lazy load API** で expose: `llive.triz.load_principles() -> dict[int, Principle]` 等。Phase 1 は **読み込み + 単純 lookup** のみ提供（principle by id, matrix lookup by (improving, worsening) tuple）。Contradiction Detector / Principle Mapper / ARIZ は Phase 3。

### D-CLI: CLI Framework & Package Structure

- **D-27:** CLI フレームワークは **`typer`** （llmesh ファミリーと統一）。subcommand 階層:
  - `llive run` — 推論
  - `llive bench` — A/B 評価
  - `llive memory` — query / inspect (`query`, `stats`, `clear`)
  - `llive schema` — validate / show
  - `llive route` — explain / dry-run
  - `llive triz` — show principle / matrix lookup (Phase 1 は read-only)
- **D-28:** Python パッケージ構成（8 層対応 flat package）：
  ```
  src/llive/
    __init__.py
    cli/              # L1 (typer commands)
    orchestration/    # L2 (Pipeline, Router)
    core/             # L3 (BaseModelAdapter, HFAdapter)
    container/        # L4 (BlockContainerExecutor, sub-blocks)
    memory/           # L5 (Semantic/Episodic, Provenance, Surprise)
    evolution/        # L6 (ChangeOp, BenchHarness) — Phase 1 部分実装
    observability/    # L7 (structlog config, metrics)
    schema/           # YAML / JSON schema validators
    triz/             # TRIZ resource loaders
  ```
  Phase 1 で `hitl/` (L8) は作らない。
- **D-29:** パッケージ名: PyPI `llmesh-llive`、import 名 `llive`（既定方針、PROJECT.md 既決）。

### D-Test: Testing Strategy

- **D-30:** **pytest + pytest-cov + hypothesis** 構成。`testing_strategy.md` の Phase 1 重点 (Unit + Component + Snapshot) に従う。CI は GitHub Actions (ubuntu-latest + macos-latest + windows-latest) で Python 3.11 のみ。GPU テストはローカル only。
- **D-31:** **6 conformance test** (`testing_strategy.md` §3) は Phase 1 では sub-block 5 種に対してのみ強制。Property-based test は `ChangeOp.apply ∘ invert` 同一性のみ。

### Claude's Discretion

以下は実装中に Claude が判断（CONTEXT.md には固定しない）：

- 各 sub-block の具体的な tensor 操作実装（HF 内蔵を呼ぶ vs 自前 RMSNorm 等）
- DuckDB / Faiss の index タイプ・ファイル分割戦略
- logging の verbose レベル細部
- pyproject.toml の dependency 最小集合（jsonschema, pydantic, faiss-cpu, duckdb, sentence-transformers, structlog, typer, transformers, accelerate, hypothesis, pytest, pytest-cov）
- テストの fixtures 構造 / mock 実装

### Folded Todos

なし — `.claude-todo.json` 不在のため。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before planning or implementing.**

### Phase 0 設計文書（全て参照必須）

- `docs/requirements_v0.1.md` — 受領原文 + 設計パターン
- `docs/requirements_v0.2_addendum.md` — 8 層再構成 + llmesh I/O 統合
- `docs/requirements_v0.3_triz_self_evolution.md` — TRIZ 内蔵 FR-23〜27
- `docs/architecture.md` — 8 層構成 + Mermaid 図 + パターン適用マップ
- `docs/data_model.md` — Memory データモデル詳細
- `docs/yaml_schemas.md` — Container / SubBlock / CandidateDiff の正式 JSON Schema (Phase 1 はこれを忠実実装)
- `docs/evaluation_metrics.md` — forgetting / pollution / latency / route_entropy の定義
- `docs/observability_schema.md` — route trace + memory link の JSON 形式
- `docs/security_model.md` — provenance + signed_by の Phase 4 設計（Phase 1 は予約のみ）
- `docs/testing_strategy.md` — Test pyramid + CI gating + Phase 別優先度
- `docs/glossary.md` — 用語定義
- `docs/model_templates.md` — 公開 LLM テンプレート 4 種の説明
- `docs/family_integration.md` — llmesh / llove との API 互換性
- `docs/roadmap.md` — 詳細 Gantt（`.planning/ROADMAP.md` は GSD 用要約版）

### 既存資産

- `specs/templates/{qwen2_5_7b,llama_3_1_8b,mistral_7b_v0_3,phi_3_5_mini}.yaml` — モデルテンプレート（Phase 1 では `qwen2_5_0_5b.yaml` を追加で生成）
- `specs/subblocks/{common,attention,ffn,llive_extensions}.yaml` — 標準 SubBlockSpec
- `specs/resources/{triz_principles,triz_contradiction_matrix,triz_attributes}.yaml` — TRIZ 内蔵リソース
- `scripts/inspect_hf_model.py` — テンプレート vs HF config 整合性検証

### GSD 関連

- `.planning/PROJECT.md` — プロジェクト全体像
- `.planning/REQUIREMENTS.md` — 16 requirements (Phase 1 スコープ)
- `.planning/ROADMAP.md` — Phase 1 Success Criteria 6 項目

### 外部依存（採用ライブラリ）

- jsonschema: https://python-jsonschema.readthedocs.io/ (Draft 2020-12)
- pydantic v2: https://docs.pydantic.dev/latest/
- faiss-cpu: https://github.com/facebookresearch/faiss
- duckdb: https://duckdb.org/docs/api/python/overview
- sentence-transformers: https://www.sbert.net/
- structlog: https://www.structlog.org/
- typer: https://typer.tiangolo.com/
- transformers: https://huggingface.co/docs/transformers/index

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `specs/templates/*.yaml` — モデルテンプレート 4 種（Phase 1 では `qwen2_5_0_5b.yaml` を追加生成）
- `specs/subblocks/*.yaml` — SubBlockSpec ひな形（pre_norm, causal_attention, ffn_swiglu, memory_read, memory_write などを `common.yaml` / `attention.yaml` / `ffn.yaml` に分けて記載済）
- `specs/resources/triz_*.yaml` — TRIZ 内蔵リソース（読み込み API のみ実装すれば TRIZ-01 達成）
- `scripts/inspect_hf_model.py` — HF model の config 検査スクリプト（テスト fixture 生成に流用）

### Established Patterns

- **8 層アーキテクチャ** — `docs/architecture.md` で確定。Phase 1 は L1〜L7（L8 は除く）。
- **JSON Schema Draft 2020-12** — `docs/yaml_schemas.md` で 3 schema 確定。Phase 1 は忠実実装。
- **Python 3.11.x 固定** — memory `project_python_311_unification.md` 方針、`pyproject.toml` で `>=3.11,<3.12`。
- **D ドライブ運用** — memory `feedback_d_drive_preference.md`。生成データは `D:/data/llive/...` 配下。
- **llmesh ファミリー API 互換** — llmesh / llove と CLI / 設定スキーマ命名規則を揃える。

### Integration Points

- **llmesh I/O Bus** — Phase 4 で結線。Phase 1 では interface 予約のみ（`llive.io.bus` を空モジュールとして用意）。
- **llove TUI** — Phase 2 で結線。Phase 1 では `OBS-01` の JSON 出力を spec として確定すれば llove 側から読み込める。
- **raptor RAD コーパス** — `RAPTOR_CORPUS_DIR=C:/Users/puruy/raptor/.claude/skills/corpus` 経由。Phase 3 (RAD-Backed Idea Generator) で本格利用、Phase 1 では参照しない。

### Creative Options Constrained

- HF transformers の internal attention を直接呼ぶ方針（D-09） → llive の sub-block は thin wrapper として実装。重再実装は Phase 2+ で adapter / lora 系を入れる時に検討。
- 8 層 + 統一スキーマ方針が決まっているので、L4 (Container Engine) を中心に書けば他層は薄く済む。

</code_context>

<specifics>
## Specific Ideas / References

- ユーザは llmesh / llove と「API 互換」「命名規則統一」を強く意識している（PROJECT.md "Family compatibility" 制約）。CLI subcommand 体系・YAML スキーマ命名は両者を踏襲する。
- 「Phase 1 完了時点で v0.1.0 として PyPI 公開を検討」（SESSION_SUMMARY.md）。これは Phase 1 完了の追加 acceptance criterion として記録する：`pip install llmesh-llive==0.1.0` で動くこと。
- `feedback_d_drive_preference.md` に従い、生成データは `D:/data/llive/` 配下に置く（C ドライブ汚染を避ける）。
- ユーザは Max plan で自律運用しており、`--auto` / `--chain` フローを許容（feedback_max_plan_autonomy.md）。Phase 1 plan-phase / execute-phase も基本 auto。

</specifics>

<deferred>
## Deferred Ideas

実装中に Phase 1 スコープ外と判明したアイデア（将来 phase へ）：

- **vLLM / TGI Adapter** — Phase 2 以降。Phase 1 は HF のみ。
- **adapter / lora_switch sub-block** — Phase 2 (BC-04)。
- **nested_container (条件付き入れ子)** — Phase 2 (BC-05)。
- **Structural memory (graph)** — Phase 2 (MEM-05)。
- **Parameter memory (adapter store)** — Phase 2 (MEM-06)。
- **Consolidation cycle** — Phase 2 (MEM-08)。
- **llove TUI 連携** — Phase 2 (OBS-03)。
- **AI candidate generation** — Phase 3 (EVO-03)。
- **Static Verifier (Z3/Lean)** — Phase 3 (EVO-04)。
- **lm-evaluation-harness 連携** — Phase 2 以降。
- **OpenTelemetry / 分散トレース** — Phase 4。
- **Ed25519 signing / signed adapter** — Phase 4 (SEC-02)。
- **TRIZ 自動推論 (Contradiction Detector / Principle Mapper / 9-Window / ARIZ)** — Phase 3 (TRIZ-02〜06)。

### Reviewed Todos (not folded)

なし。

</deferred>

---

*Phase: 01-mvr*
*Context gathered: 2026-05-13*
*Generated under `--auto` mode (Max plan autonomy)*
