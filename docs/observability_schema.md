# llive 観測スキーマ

> v0.1 NFR-03 / FR-09 の精密化。OpenTelemetry semantic conventions に準拠した span / event / metric の定義。

## 1. 設計原則

- **OpenTelemetry semantic conventions に準拠**: 既存ツール（Jaeger / Tempo / Honeycomb / Phoenix）で観測可能
- **Trace context propagation**: L1 から L7 まで `trace_id` / `span_id` を維持
- **暗黙状態禁止**: NFR-03 の通り、すべての主要イベントを構造化ログに出す
- **Semantic enrichment**: llive 固有属性（`candidate_id`, `memory_zone`, `surprise_score` 等）を追加

## 2. リソース属性 (Resource)

すべての telemetry に共通で付与:

| 属性 | 例 | 説明 |
|---|---|---|
| `service.name` | `llive` | 固定 |
| `service.version` | `0.1.0` | semver |
| `service.namespace` | `experimental` / `staging` / `production` | デプロイ環境 |
| `host.name` | hostname | |
| `process.runtime.name` | `cpython` | |
| `process.runtime.version` | `3.11.x` | |
| `llive.run.id` | ULID | この llive 起動の一意 ID |
| `llive.base_model.id` | `qwen2.5-7b` | コアモデル |
| `llive.base_model.hash` | sha256 prefix | hash |

## 3. Span 階層

### 3.1 Pipeline span (L2)

```yaml
name: llive.pipeline.invoke
attributes:
  llive.task.id: <task_id>
  llive.experiment.id: <experiment_id>
  llive.candidate.id: <candidate_id>      # 評価中なら
  llive.input.length: <token_count>
  llive.input.privacy_class: <enum>
status: ok | error
duration_ms: <float>
```

子 span:

- `llive.pipeline.preprocess`
- `llive.pipeline.memory_retrieval`
- `llive.pipeline.router_decision`
- `llive.pipeline.container_execute` (L4)
- `llive.pipeline.memory_write_gate`

### 3.2 Container span (L4)

```yaml
name: llive.container.execute
attributes:
  llive.container.id: adaptive_reasoning_v1
  llive.container.version: 3
  llive.subblock.count: 9
  llive.route.depth: 9
  llive.route.entropy: 1.42
events:
  - name: subblock.enter
    attributes:
      llive.subblock.name: memory_read
      llive.subblock.position: 2
  - name: subblock.exit
    attributes:
      llive.subblock.name: memory_read
      llive.subblock.latency_ms: 12.3
      llive.subblock.activated: true
```

### 3.3 Memory span (L5)

```yaml
name: llive.memory.read | llive.memory.write
attributes:
  llive.memory.type: semantic | episodic | structural | parameter
  llive.memory.zone: trusted | quarantine
  llive.memory.operation: read | write | merge | archive
  llive.memory.node_count: <int>
  llive.memory.query.embedding_model: <str>
  llive.memory.surprise_score: <float>            # write 時
  llive.memory.surprise_uncertainty: <float>      # FR-21
events:
  - name: memory.zone_violation
    attributes:
      llive.memory.attempted_zone: quarantine
      llive.memory.signature_present: false
```

### 3.4 Router span (L2)

```yaml
name: llive.router.decide
attributes:
  llive.router.mode: deterministic | stochastic | policy_based
  llive.router.input_features_summary: <hash>
  llive.router.selected_container: <container_id>
  llive.router.alternatives_considered: <count>
  llive.router.decision_log_ref: <path>           # FR-04 explanation log
events:
  - name: router.fallback_triggered
    attributes:
      llive.router.fallback_reason: <str>
```

### 3.5 Evolution span (L6)

```yaml
name: llive.evolution.<phase>
# phase = propose | verify | shadow_eval | short_eval | long_eval | hitl | stage | promote | rollback
attributes:
  llive.candidate.id: <candidate_id>
  llive.candidate.base: <base_candidate_id>
  llive.candidate.diff_size: <int>
  llive.candidate.mutation_policy: llm_generated | template | population | neuroevolution
  llive.evolution.score_static_verifier: proved | unprovable | refuted
  llive.evolution.score_shadow: <float>
  llive.evolution.score_short: <float>
  llive.evolution.score_long: <float>
  llive.evolution.forgetting: <float>
  llive.evolution.decision: accept | reject | defer
events:
  - name: evolution.state_transition
    attributes:
      llive.evolution.from_state: <enum>
      llive.evolution.to_state: <enum>
      llive.evolution.actor: ai_proposer | static_verifier | shadow_eval | human_<user_id>
```

## 4. Metrics

### Counter

| metric | 単位 | ラベル |
|---|---|---|
| `llive.requests.total` | count | `task_id`, `status` |
| `llive.memory.writes.total` | count | `memory_type`, `zone` |
| `llive.memory.reads.total` | count | `memory_type`, `zone` |
| `llive.candidate.proposed.total` | count | `mutation_policy` |
| `llive.candidate.promoted.total` | count | — |
| `llive.candidate.rejected.total` | count | `reject_stage` |
| `llive.candidate.rolled_back.total` | count | — |
| `llive.security.zone_violations.total` | count | `attempted_zone` |

### Histogram

| metric | 単位 | バケット |
|---|---|---|
| `llive.pipeline.latency_ms` | ms | exp [1, 10, 100, 1000, 10000] |
| `llive.subblock.latency_ms` | ms | exp |
| `llive.memory.read.latency_ms` | ms | exp |
| `llive.memory.write.latency_ms` | ms | exp |
| `llive.evolution.eval.duration_s` | s | exp [1, 10, 100, 1000, 10000] |

### Gauge

| metric | 単位 | 説明 |
|---|---|---|
| `llive.memory.nodes.count` | count | per type / zone |
| `llive.memory.pollution_ratio` | ratio | per type |
| `llive.subblock.dead_rate` | ratio | rolling window |
| `llive.router.entropy` | nats | rolling window |
| `llive.vram.peak_mb` | MB | per process |

## 5. Event Bus (P-03 Event-Driven Architecture)

llive 内部の主要イベントを **pub/sub** で配信。llmesh I/O Bus と直接 bridge 可能。

### Event types

```yaml
- llive.memory.written
- llive.memory.consolidated
- llive.memory.archived
- llive.memory.erased
- llive.candidate.proposed
- llive.candidate.state_changed
- llive.candidate.promoted
- llive.candidate.rolled_back
- llive.hitl.requested
- llive.hitl.responded
- llive.security.zone_violation
- llive.benchmark.run_started
- llive.benchmark.run_finished
```

### Schema (CloudEvents 1.0 準拠)

```yaml
specversion: "1.0"
type: llive.memory.written
source: llive://run/<run_id>/memory
id: <ULID>
time: <RFC3339>
datacontenttype: application/json
subject: <node_id>
data:
  memory_type: semantic
  zone: trusted
  surprise_score: 0.83
  provenance:
    source_type: derived
    derived_from: [<parent_node_id>]
```

## 6. ログレベル指針

| レベル | 用途 |
|---|---|
| `TRACE` | sub-block 内部の中間 tensor 統計（dev mode のみ） |
| `DEBUG` | router 判断詳細、memory query plan |
| `INFO` | pipeline / candidate state 遷移 |
| `WARN` | fallback 発生、閾値接近、HITL 要求 |
| `ERROR` | 例外、retry 不能 |
| `CRITICAL` | data corruption、署名検証失敗 |

## 7. ダッシュボード推奨ペイン

### llove TUI 内蔵
- Live trace stream (pipeline span)
- Memory link graph (interactive)
- Route trace timeline
- Candidate state board
- Security violation alert

### 外部 (Grafana / Phoenix / Honeycomb)
- p50 / p95 latency
- Forgetting trend (rolling BWT)
- Pollution ratio per memory type
- Dead block rate
- Candidate funnel (proposed → verified → shadow → short → long → hitl → prod)

## 8. データ保持

| データ | 場所 | 保持期間 |
|---|---|---|
| Trace (raw) | OTLP collector | 30 日 |
| Metric (raw) | Prometheus / TSDB | 90 日 |
| Metric (aggregated) | DuckDB / Parquet | 無期限 |
| Audit log | append-only sqlite + SHA-256 chain | 無期限 |
| Event log | event store | 1 年 |
| HITL decision | candidate manifest | 無期限 |
