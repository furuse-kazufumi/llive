# Phase 2: Adaptive Modular System - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning
**Mode:** `--auto` (Max plan autonomy)

<domain>
## Phase Boundary

Phase 2 が delivery するもの = **4 層メモリ + Bayesian surprise + consolidation cycle + llove TUI 最小可視化 + LLM Wiki layer 着工**。連続タスク学習で BWT ≥ -1% を達成する。

成功基準 (ROADMAP):
1. structural memory (graph) + parameter memory (adapter store) が動作
2. surprise score が Bayesian uncertainty として扱われ、write 閾値が動的化
3. consolidation サイクルが夜間 batch で走り、replay → semantic 凝集
4. memory phase transition (short → mid → long → archived → erased) が cron で動く
5. llove TUI で route trace + memory link viz が見られる
6. 連続 5 タスク学習で BWT ≥ -1%、route entropy が正常範囲
7. **(LLW-01〜03/06)** ConceptPage が第一級表現として動作し、Wiki Compiler が consolidation の出力として ConceptPage を更新できる、外部生ソース ingest CLI が使える

**Phase 2 に含まれないもの**：
- AI candidate generation (Phase 3 EVO-03)
- Static Verifier Z3/Lean (Phase 3 EVO-04)
- Multi-precision shadow eval (Phase 3 EVO-05)
- Reverse-Evolution Monitor (Phase 3 EVO-07)
- TRIZ Contradiction Detector / Principle Mapper / ARIZ (Phase 3 TRIZ-02〜06)
- ConceptPage の矛盾検出 (Phase 3 LLW-04)
- Wiki diff (add/merge/split as ChangeOp) (Phase 3 LLW-05)
- llove F16 Candidate Arena (Phase 4 INT-03)
- Signed adapter / Quarantine zone (Phase 4 SEC-01/02)
- llmesh sensor bridge (Phase 4 INT-01)

</domain>

<decisions>
## Implementation Decisions

### D-Graph: Structural Memory Backend (MEM-05)

- **D-01:** Graph backend は **Kùzu** (embedded analytical graph DB)。Python パッケージ `kuzu` (PyPI)。STATE.md の open question で推奨されており、ローカル運用 / Cypher サブセット対応 / OLAP 強い。Neo4j は server 必要・依存重い、NetworkX+SQLite は規模出ない。
- **D-02:** Graph schema は **bipartite** で開始：
  - `MemoryNode` (entity / concept): `(id, memory_type, zone, payload_json, created_at, provenance_json, embedding_blob)`
  - `MemoryEdge` (relation): `(src_id, dst_id, rel_type, weight, provenance_json, created_at)`
  - `rel_type` enum: `derived_from / contradicts / generalizes / temporal_after / co_occurs_with / linked_concept (LLW-01)`
- **D-03:** Storage path: `D:/data/llive/memory/structural.kuzu/`。Phase 2 では single-DB、Phase 4 で zone 分離。

### D-Param: Parameter Memory (MEM-06)

- **D-04:** Parameter memory backend は **filesystem + DuckDB index** のハイブリッド。各 AdapterProfile は安全な safetensors ファイル (`D:/data/llive/memory/parameter/<adapter_id>.safetensors`) と DuckDB の `adapter_index` テーブル（`adapter_id, name, base_model, format, size_mb, sha256, provenance_json, tags[], created_at`）。
- **D-05:** 対応 adapter format（Phase 2 は LoRA を最優先、IA3 と prefix-tuning は interface 予約）：
  - **LoRA** (HuggingFace PEFT 互換)
  - IA3 (interface のみ、Phase 3+)
  - Prefix tuning (interface のみ、Phase 3+)
  - generic state_dict swap (escape hatch)
- **D-06:** `AdapterProfile` pydantic model: `(id, name, base_model, format, adapter_size_mb, target_modules, alpha, dropout, tags, provenance, sha256)`. registry は `llive.memory.parameter.AdapterStore` クラスで `register / load / activate / deactivate / list / verify_sha256` API を提供。
- **D-07:** Phase 2 は **HuggingFace PEFT (`peft>=0.10`)** を optional extra `[torch]` 系に追加して採用。コア依存は増やさない（PEFT が無くても interface は import 可能、`load_adapter()` で初めて要求）。

### D-Bayes: Bayesian Surprise (MEM-07)

- **D-08:** Bayesian surprise は **online running mean+variance** (Welford's algorithm) を採用。各 ConceptPage / semantic entry のローカルな統計を維持し、新規 entry の surprise を z-score 化、確率密度の対数 negative-log-likelihood として返す。
- **D-09:** API: `BayesianSurpriseGate(theta_mean=0.3, theta_variance=0.5)` を `SurpriseGate` の後継として `llive.memory.surprise` に追加。Phase 1 の `SurpriseGate`（cosine NN distance）は **後方互換のため残し**、`BayesianSurpriseGate` を新 default にする。
- **D-10:** 動的閾値 θ は **EMA decay** で過去 N batch の surprise 分布から決める：`θ_t = μ + k·σ` (default k=1.0)。ConceptPage 別に θ を保持できるよう設計（Phase 3 LLW-04 で各ページが固有 σ を持つのに備える）。
- **D-11:** 粒子フィルタ / variational inference は Phase 2 では採用しない（依存重い、要件は確率分布として扱えれば充分）。

### D-Cons: Consolidation Cycle (MEM-08, LLW-02)

- **D-12:** Consolidation Scheduler は **APScheduler 3.x** を採用。`BackgroundScheduler` を `Consolidator` クラスでラップし、cron / interval / event の 3 trigger を統一 API で扱う。
  - default cron: 毎日 02:00 (低負荷帯) で全 episodic events を batch 処理
  - 別名 trigger: `llive consolidate run --since 1h` で手動 force-run
- **D-13:** Consolidation の単一サイクル = **「Wiki Compile pass」** (LLW-02)：
  1. **Replay Select** — 過去 N 時間の episodic events を surprise-weighted reservoir sample
  2. **Cluster** — sentence embedding + HDBSCAN で events を意味的グループに
  3. **Compile** — 各クラスタについて (a) 既存 ConceptPage を query (b) LLM に「新規ページ作成 / 既存ページ更新 / 統合 / 分割」を判定させ (c) 該当 ConceptPage を更新
  4. **Link** — 関連する ConceptPage 間に structural memory のエッジを張る
  5. **Provenance** — どの events からどの ConceptPage が更新されたかを `derived_from` に記録
- **D-14:** クラスタ手法は **HDBSCAN (`hdbscan` PyPI)**：パラメタフリー / cluster 数自動 / Phase 2 の "動く" 重視には適している。`sklearn.cluster.KMeans` は数を指定する必要があり弱い。
- **D-15:** LLM 呼び出しは **Anthropic Claude (Haiku)** をデフォルトとする（既存 `corpus2skill` 採用と統一）。`ANTHROPIC_API_KEY` env 必須。OpenAI / local Ollama fallback は Phase 3 で。
- **D-16:** Replay Select の sample 規模は **default 200 events / cycle**（small enough for one Haiku batch、large enough for meaningful clustering）。Phase 3 で adaptive batch sizing。

### D-Phase: Memory Phase Transition (MEM-09)

- **D-17:** Memory phase は 5 段階：`hot → warm → cold → archived → erased`。各 entry に `phase`, `last_access_at`, `access_count`, `phase_changed_at` を持たせる。
- **D-18:** Phase 遷移ルール（cron で daily 評価）:
  - hot → warm: 7 日間未参照
  - warm → cold: 30 日間未参照
  - cold → archived: 90 日間未参照 + surprise が低い (BayesianSurpriseGate で θ 未満)
  - archived → erased: 180 日間未参照 + 法令制約 OK (`Provenance.privacy_class` をチェック)
  - 任意の phase → hot: アクセスごとに復帰
- **D-19:** Erased entry は metadata のみ残し、payload + embedding は削除（GDPR 等 right-to-be-forgotten 対応）。`erased_at` を記録。
- **D-20:** phase transition は `MemoryPhaseManager` クラスとして `llive.memory.phase` に置く。consolidation cycle 後に自動実行 (chained scheduler)。

### D-Wiki: ConceptPage & Wiki Compiler (LLW-01, LLW-02, LLW-03)

- **D-21:** **ConceptPage** は structural memory の `MemoryNode` (memory_type=`concept`) として表現。LLW-01 の schema は data_model.md の MemoryNode を拡張：
  ```python
  class ConceptPage(BaseModel):
      concept_id: str           # kebab-case slug, unique
      title: str
      summary: str              # ≤ 2000 chars, LLM-generated
      page_type: str            # see LLW-03
      linked_entry_ids: list[str]  # semantic memory entry_ids
      linked_concept_ids: list[str]  # other concept_ids
      schema_version: int
      provenance: Provenance
      last_updated_at: datetime
      surprise_stats: dict      # Welford mean/var/n for D-10
  ```
- **D-22:** ConceptPage の永続化先：structural memory の Kùzu DB に `concept` 種別の MemoryNode として保存 + Markdown export を `D:/data/llive/wiki/<concept_id>.md` に書き出し（人間可読 / Git 管理可能）。
- **D-23:** LLW-03 `page_type` は YAML で定義（`specs/wiki_schemas/`）。Phase 2 で実装する 4 種：
  - `domain_concept` — 一般概念（"BlockContainer", "surprise gate"）
  - `experiment_record` — CandidateDiff 評価結果のページ
  - `failure_post_mortem` — Failed-Candidate Reservoir の記録（Phase 3 から本格利用、interface のみ）
  - `principle_application` — TRIZ 原理 × llive 文脈の応用例（Phase 3 LLW-04/05 で本格利用）
- **D-24:** 各 page_type の structured fields は JSON Schema (`specs/wiki_schemas/<page_type>.v1.json`) で検証する。Phase 1 で `specs/schemas/` に置いた 3 schema と同様の構成。

### D-Ingest: External Source Ingest CLI (LLW-06)

- **D-25:** `llive wiki ingest --source <path|url> --type <type>` を typer subcommand として追加。サポート type:
  - `text` — プレーンテキスト（行 / 段落単位で chunking）
  - `markdown` — 見出しで自動 chunking、heading 階層を Provenance に保存
  - `pdf` — `pypdf` でテキスト抽出 → text 経由
  - `arxiv` — arXiv ID 指定で abstract + sections 取込
  - `url` — HTML scraping (readability) → text 経由
- **D-26:** ingest 時：
  1. ソースを chunk (target 500 tokens per chunk)
  2. 各 chunk を episodic memory に書き込む（provenance に `source_type=imported, source_id=<original_uri>` をセット）
  3. ingest 完了後に Wiki Compiler を非同期 trigger (`--compile-now` で同期実行可)
- **D-27:** PDF / arXiv / url は **optional extras** `[ingest]` に切り出す（`pypdf`, `arxiv`, `readability-lxml`）。コア依存は増やさない。

### D-BC: Block Container Extensions (BC-04, BC-05)

- **D-28:** **`adapter` sub-block** (BC-04): LoRA adapter を hidden state に適用する thin wrapper。config: `{adapter_id: str, target_layer: str | "current"}`. AdapterStore から load → 実行時に推論パスにマージ（推論時 merge & forward）。
- **D-29:** **`lora_switch` sub-block** (BC-04): 複数の AdapterProfile から router の判断 (task_tag) に応じて 1 つを選んで動的 swap。config: `{adapters: [adapter_id...], selector: "task_conditioned" | "round_robin"}`. cold-start 時は base model のみ。
- **D-30:** **`nested_container`** (BC-05): ContainerSpec の `nested_containers:` フィールド (Phase 1 で schema 予約済) を実行可能化。`target` で示された nesting point に到達したら `condition` を評価し、満たせば別 ContainerSpec を再帰展開して実行。最大 depth は config で制限 (default 3) — 無限再帰防止。
- **D-31:** nested_container の循環参照検出は実装必須（同じ container_id が depth chain に 2 度現れたら ChangeOpError）。

### D-Obs: llove TUI Integration (OBS-03, OBS-04)

- **D-32:** llive ↔ llove 連携は **JSONL ファイル経由 + (optional) IPC**：
  - 第 1 段: llive が出力する trace / metrics JSONL を llove が tail で読む（Phase 1 既存形式を流用）。llive 側に変更不要、llove 側で TUI viewer 実装。
  - 第 2 段 (Phase 4 に倒す): UNIX socket / named pipe で realtime push。Phase 2 では JSONL polling で十分。
- **D-33:** llove に追加する viewer (llove リポジトリ側で別実装、本 plan-phase の scope 外だが要件として確認)：
  - `RouteTraceViewer` (OBS-03) — recent N traces を table 形式 + per-trace detail panel + memory link graph (graph viz は textual の graph widget もしくは ASCII art 簡易版)
  - `MemoryLinkVizPanel` — ConceptPage と linked_entries / linked_concepts を tree 表示
  - `BWTDashboard` (OBS-04) — 過去 24h / 7d の BWT を sparkline 表示
- **D-34:** Phase 2 の llive 側責務は「llove が読める形式の JSONL を出力する」までで打ち止め。llove 側のコードは llove リポジトリで実装。本 CONTEXT.md ではフォーマット仕様の確定のみ行う。
- **D-35:** **BWT (Backward Transfer) 計測** (OBS-04): 連続 N タスク学習中に「過去タスクへの性能影響」を計測。Phase 2 では以下の擬似 BWT を採用：
  - 連続タスク k での評価セット accuracy を `a_k_k` (タスク k 学習直後)、`a_k_K` (最終タスク K 学習後) として記録
  - `BWT = mean(a_k_K - a_k_k for k=1..K-1)` を `llive bench` の出力に含める
  - 厳密な GEM/A-GEM 風 BWT は Phase 3 で。

### D-Pkg: Package Structure Extensions

- **D-36:** Phase 2 で追加するモジュール：
  ```
  src/llive/
    memory/
      structural.py        (MEM-05: Kùzu wrapper)
      parameter.py         (MEM-06: AdapterStore)
      bayesian_surprise.py (MEM-07: Welford-based gate)
      consolidation.py     (MEM-08, LLW-02: Consolidator + Compiler)
      phase.py             (MEM-09: MemoryPhaseManager)
      concept.py           (LLW-01: ConceptPage model)
    container/subblocks/
      adapter_block.py     (BC-04: adapter sub-block)
      lora_switch_block.py (BC-04: lora_switch sub-block)
    wiki/
      __init__.py
      compiler.py          (LLW-02 entry point)
      ingest.py            (LLW-06: ingest CLI handlers)
      schemas/             (LLW-03: page_type loaders)
    cli/wiki.py            (CLI subcommands for wiki)
    cli/consolidate.py     (CLI subcommands for consolidation)
  specs/wiki_schemas/       (LLW-03: JSON Schema per page_type)
  ```
- **D-37:** Dependencies 追加 (`pyproject.toml`):
  - core: `apscheduler>=3.10`, `kuzu>=0.4` (新規)
  - `[torch]` 拡張: `peft>=0.10`, `hdbscan>=0.8`
  - `[ingest]` 拡張 (新規): `pypdf>=4.0`, `arxiv>=2.1`, `readability-lxml>=0.8`
  - `[llm]` 拡張 (新規): `anthropic>=0.30` (Consolidator が使う)
- **D-38:** **後方互換性**：Phase 1 の Pipeline / Executor は変更しない。Phase 2 機能はすべて opt-in (新 sub-block / 新 CLI subcommand / 新 Memory backend) として追加。Phase 1 ユーザは触らなくても動き続ける。

### D-Test: Testing Strategy

- **D-39:** Phase 2 では **Integration test** の比重を上げる (`testing_strategy.md` Phase 2 重点)。新規追加：
  - `tests/integration/test_consolidation_cycle.py` — events 投入 → consolidate run → ConceptPage 作成確認
  - `tests/integration/test_phase_transition.py` — entry age 操作 → phase manager 実行 → phase 遷移確認
  - `tests/integration/test_adapter_lifecycle.py` — AdapterProfile register → load → activate → use → deactivate
  - `tests/integration/test_wiki_ingest_flow.py` — ingest CLI → episodic write → wiki compile → ConceptPage 取得
- **D-40:** LLM 呼び出しを伴うテスト (Consolidator) は **Anthropic API key が無くてもスキップせず動く** ように mock 実装を用意。`LLIVE_CONSOLIDATOR_MOCK=1` で deterministic mock を使う。CI では mock 強制。

### Claude's Discretion

- Kùzu の具体的 schema 名 / Cypher 文法詳細（実装中に最適化）
- DuckDB の adapter_index テーブルの index 戦略
- APScheduler の trigger 細部 / persistence backend
- 各 sub-block の tensor 操作の具体 (HF PEFT 経由 vs 自前 LoRA merge)
- Wiki Markdown export のテンプレート細部
- pyproject.toml dependency の最小バージョン微調整
- テスト fixture / mock の具体実装

### Folded Todos

なし。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 0-1 設計文書（全て参照必須）

- `docs/requirements_v0.1.md` — 受領原文 + 設計パターン
- `docs/requirements_v0.2_addendum.md` — 8 層再構成 + TRIZ 矛盾 → FR-12〜22 (Phase 2 FR-12/16/19/21 が該当)
- `docs/requirements_v0.3_triz_self_evolution.md` — TRIZ 内蔵 (Phase 3 範囲)
- `docs/requirements_v0.4_llm_wiki.md` — LLM Wiki LLW-01〜08 (Phase 2 で LLW-01/02/03/06)
- `docs/architecture.md` — 8 層 + Mermaid 図 + パターン適用マップ
- `docs/data_model.md` — MemoryNode / MemoryEdge / AdapterProfile の正式 schema
- `docs/yaml_schemas.md` — ContainerSpec / SubBlockSpec / CandidateDiff schema (Phase 1 で実装済、Phase 2 でも下敷き)
- `docs/evaluation_metrics.md` — BWT / forgetting / pollution 定義
- `docs/observability_schema.md` — route trace + memory link JSON 形式
- `docs/security_model.md` — provenance + signed_by (Phase 4 で本実装、Phase 2 ではフィールド予約)
- `docs/testing_strategy.md` — Test pyramid (Phase 2 重点 = Property-based + Integration)
- `docs/family_integration.md` — llmesh / llove との API 互換

### Phase 1 成果物

- `.planning/phases/01-mvr/01-CONTEXT.md` — Phase 1 で確定した 17 gray area
- `.planning/phases/01-mvr/01-PLAN.md` — Phase 1 wave 分解
- `.planning/phases/01-mvr/01-VERIFICATION.md` — Phase 1 完了報告
- `src/llive/memory/` — Phase 1 で実装した semantic / episodic / provenance / surprise
- `src/llive/container/` — Phase 1 で実装した executor + 5 sub-blocks
- `src/llive/triz/` — Phase 1 で実装した TRIZ resource loader

### GSD 関連

- `.planning/PROJECT.md` — プロジェクト全体像
- `.planning/REQUIREMENTS.md` — Phase 2: MEM-05/06/07/08/09 + BC-04/05 + OBS-03/04 + LLW-01/02/03/06 = 13 reqs
- `.planning/ROADMAP.md` — Phase 2 Success Criteria 6 項目 (+1 LLW = 7)

### 外部依存（採用ライブラリ）

- Kùzu: https://kuzudb.com/ (graph DB)
- APScheduler: https://apscheduler.readthedocs.io/
- HuggingFace PEFT: https://huggingface.co/docs/peft/
- HDBSCAN: https://hdbscan.readthedocs.io/
- Anthropic SDK: https://docs.anthropic.com/

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (Phase 1 で実装済)

- `Provenance` (pydantic) — そのまま Phase 2 の AdapterProfile / ConceptPage で再利用
- `SemanticMemory` / `EpisodicMemory` — 拡張点：consolidation の入出力先
- `SurpriseGate` — Phase 2 で `BayesianSurpriseGate` 追加、後方互換
- `BlockContainerExecutor` — 変更不要、新 sub-block (adapter / lora_switch) を SubBlockRegistry に登録するだけ
- `SubBlockRegistry` — entry-points で外部 plugin 受け入れ可能、Phase 2 builtin 拡充
- `MemoryEncoder` — 拡張点：HDBSCAN clustering 前の embedding 計算で再利用
- `RouterEngine` — 変更不要 (router rule の Phase 2 拡張は別途、Phase 3 task_tag 推論で本格化)
- `Pipeline` — Phase 2 で Consolidator hook を追加 (post-run trigger)
- `MetricsStore` — BWT も同じ DuckDB に append
- `RouteTrace` — そのまま、llove 側で読む

### Established Patterns

- **D ドライブ運用** — Phase 2 で追加するデータ (kuzu / parameter store / wiki markdown) も `D:/data/llive/` 配下
- **Python 3.11 固定** — Phase 2 も継続
- **optional extras 設計** — torch / peft / hdbscan / kuzu / anthropic などは extras に分離、コア依存最小化
- **packaged _specs/** — `src/llive/_specs/` に schemas をバンドル (v0.1.1 で導入)、Phase 2 の wiki_schemas も同じパターン
- **JSONL append-only** — trace / router log / metrics は JSONL のまま、Phase 2 で wiki ingest log も JSONL

### Integration Points

- **llove TUI** — Phase 2 で結線。llive 側は JSONL 出力フォーマット確定まで、llove 側で viewer 実装
- **llmesh I/O Bus** — Phase 4 で本格結線、Phase 2 では interface 予約のみ
- **raptor RAD コーパス** — Phase 3 RAD-Backed Idea Generator (TRIZ-04) で本格利用、Phase 2 では参照しない

### Creative Options Constrained

- HF PEFT 経由 LoRA → adapter sub-block の実装は薄ラッパーで済む
- Kùzu embedded → ローカル graph DB のセットアップ不要
- APScheduler → cron / interval / event の 3 trigger を統一 API で扱える
- Anthropic Claude Haiku → corpus2skill と同じ採用、依存・コスト見通し済

</code_context>

<specifics>
## Specific Ideas / References

- **連続 5 タスク学習で BWT ≥ -1%** (Success Criterion #6) — これが Phase 2 verify の最大のハードル。Phase 2 中で「タスクセット = 何か」を確定する必要あり (推奨候補: HuggingFace `glue` の 5 subset、または既存 toy_dataset の domain-split)。
- LLW-02 (Wiki Compiler) の LLM 呼び出しは **Anthropic Haiku** を採用予定。コスト見積もり: 200 events × 1 cycle × ~$0.001 = 1 cycle ~$0.2、daily run で月 ~$6 (個人スケール)。
- **llove F11 / F15 連携** が想定されているが、llove 現バージョン (v0.6.x) では F15 (Markdown viewer / SVG / Mermaid) は実装中。Phase 2 で llive 側が JSONL を吐けるようにすれば、llove 側の進捗に合わせて段階的に統合できる。
- Phase 2 完了で v0.2.0 PyPI 公開を検討（feedback_publishing_workflow.md 沿い）。Phase 2 の差別化軸は **「LLM Wiki backbone」+「Bayesian surprise」+「Memory phase manager」** の 3 つ。

</specifics>

<deferred>
## Deferred Ideas

Phase 2 スコープ外と判断したもの：

- **粒子フィルタ / variational inference 版 Bayesian surprise** — Phase 3 EVO 系で必要なら追加
- **AI candidate generation (LLM mutation policy)** — Phase 3 EVO-03
- **Static Verifier (Z3/Lean)** — Phase 3 EVO-04
- **Multi-precision shadow eval** — Phase 3 EVO-05
- **Failed-Candidate Reservoir 本実装** — Phase 3 EVO-06 (Phase 2 では failure_post_mortem ConceptPage の interface のみ)
- **Reverse-Evolution Monitor** — Phase 3 EVO-07
- **Population-based search** — Phase 3 EVO-08
- **TRIZ Contradiction Detector / Principle Mapper / 9-Window / ARIZ** — Phase 3 TRIZ-02〜06
- **ConceptPage 矛盾検出** — Phase 3 LLW-04
- **Wiki diff (add_concept / merge / split as ChangeOp)** — Phase 3 LLW-05
- **Quarantined Memory Zone + 署名検証** — Phase 4 SEC-01
- **Signed Adapter Marketplace (Ed25519 + SBOM)** — Phase 4 SEC-02
- **llmesh sensor bridge (MQTT/OPC-UA)** — Phase 4 INT-01
- **llove Candidate Arena (F16)** — Phase 4 INT-03
- **llove TUI realtime push (UNIX socket / named pipe)** — Phase 4
- **llove TUI Wiki viewer** — Phase 4 LLW-07 (Phase 2 は JSONL 出力フォーマット確定まで)
- **RAG×Wiki 二層運用 (Wiki 優先 query)** — Phase 4 LLW-08

### Reviewed Todos (not folded)

なし。

</deferred>

---

*Phase: 02-adaptive*
*Context gathered: 2026-05-13*
*Generated under `--auto` mode (Max plan autonomy)*
*Total decisions: 40 (D-01 〜 D-40)*
