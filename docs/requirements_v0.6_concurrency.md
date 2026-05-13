# llive 要件定義 v0.6 — 並行プロンプト処理 / 思考ブランチ並列探索

**Drafted:** 2026-05-13
**Status:** **要件追加（実装は段階的、Phase 2 で骨格 / Phase 4 で本格化）**
**Type:** Concurrency addendum
**Trigger:** ユーザ要望「あるPromptに対する処理を実行中に別のPromptが並行入力されたら、別スレッドで思考ブランチを並行探索する構造」

---

## 1. 動機

現在の llive は **単一プロンプト・シーケンシャル実行**を前提に設計されている。実運用では：

- **複数ユーザ / API クライアントが同時にプロンプトを投入** する状況に対応すべき
- **1 プロンプトでも複数の "思考ブランチ"** (異なる container / candidate / adapter で並列推論) を試したい場面がある
- 既存の `threading.Lock` は単に競合回避用で、**スケーラブルな並行性は提供しない**

LLM Wiki の動的 edge weight (AC-10/11) はますますこのニーズを強める：
- read_hit / time_decay / random_boost / surprise が並行イベントとして降ってくる
- ブランチ間で memory アクセスが競合する
- consolidation cycle と推論ループの並走

---

## 2. 要件 (CONC-XX シリーズ)

### CONC-01: Thread-safe Memory Layers (Phase 2 必須)

全 memory backend の公開 API は **thread-safe** であることを保証する：

- `SemanticMemory`: write / query / save / load / clear / all_embeddings (既に `_lock` あり ✅)
- `EpisodicMemory`: write / query_range / query_recent / count / clear (既に `_lock` あり ✅)
- `StructuralMemory`: add_node / add_edge / query_neighbors / list_nodes / count_nodes / delete_node (既に `_lock` あり ✅)
- `AdapterStore`: register / get / list / activate / deactivate / verify_sha256 (既に `_lock` あり ✅)
- `EdgeWeightUpdater`: on_read_hit / on_contradiction / on_surprise / apply_time_decay / random_boost / prune / _adjust (既に `_lock` あり ✅)
- `ConceptPageRepo`: upsert / get / list_all / link_concept / link_entry (構造依存、structural の lock を通じて safe ✅)
- `Consolidator`: run_once (cycle 全体に `_lock` ✅、ただし呼出元から見た直列化のみ)

→ **Phase 2 では既存ロックを継承するだけで CONC-01 は達成済み**。formal-verification は Phase 4。

### CONC-02: ConcurrentPipeline (Phase 2 必須・最小実装)

複数プロンプトを `ThreadPoolExecutor` で並行実行する薄いラッパーを追加：

```python
class ConcurrentPipeline:
    def __init__(self, pipeline: Pipeline, max_workers: int = 4): ...
    def run_parallel(self, prompts: list[str], **kwargs) -> list[PipelineResult]: ...
    def submit(self, prompt: str, **kwargs) -> Future[PipelineResult]: ...
    def close(self) -> None: ...
```

Phase 2: `concurrent.futures.ThreadPoolExecutor` ベース。GIL の制約上、HF model inference は事実上シリアル化されるが、memory I/O / Wiki ingest / router 判定は並列化可能。Phase 4 で asyncio / multiprocessing 検討。

### CONC-03: BranchExplorer (Phase 2 必須・最小実装)

**1 プロンプトに対し複数 container を並列に試す**ためのユーティリティ：

```python
class BranchExplorer:
    def __init__(
        self,
        pipeline: Pipeline,
        container_ids: list[str],
        max_workers: int = 4,
    ): ...
    def explore(self, prompt: str, **kwargs) -> list[BranchResult]: ...
```

各 BranchResult は `(container_id, PipelineResult, latency_ms)` を持ち、結果は Wiki Compiler が比較・統合する材料として使う。Phase 3 EVO 系の population search の前段にもなる。

### CONC-04: Snapshot-based Reads (Phase 3-4)

並行 read が consolidation cycle の途中で memory state を見ると不整合を読みやすい：

- 各 ConcurrentPipeline.submit はジョブ開始時に memory snapshot を取得
- snapshot は immutable view、書き込みは元 backend へ
- Phase 4 で `kuzu` の transaction API を使って実装、Phase 2-3 では coarse-grained lock で十分

### CONC-05: Write Contention Tracking (Phase 3)

`structlog` で `lock_wait_ms` をメトリクスとして記録。長時間ブロックを HITL から可視化できる llove dashboard 連携：

- `D:/data/llive/logs/llove/lock_contention.jsonl` に append
- BWT dashboard と同じフォーマット、llove `LockContentionPanel` 用

### CONC-06: Branch Result Aggregation (Phase 3-4)

複数ブランチの結果を比較する標準ロジック：

- `text_diff` (rouge / cosine sim) で各ブランチ間距離
- `metric_compare` で latency / surprise / route_entropy を表形式に
- Wiki Compiler が比較結果を `failure_post_mortem` / `experiment_record` ConceptPage として記録

### CONC-07: Cancellation (Phase 4)

`Future.cancel()` で実行中のブランチをキャンセル可能に：

- HF model.generate は kill 信号を受け付けないため、長時間 inference は cooperative cancel
- container_executor に `state.cancelled` フラグを足し、各 sub-block が check できるようにする
- Phase 2 では skip (HF inference は同期完了まで待つ)

### CONC-08: Backpressure / Queue Management (Phase 4)

`ConcurrentPipeline` に queue サイズ上限を持たせ、満杯時は早期 reject / shed する：

- 暴走防止 + メモリ確保の予測可能性
- Prometheus / OpenTelemetry 連携 (Phase 4)

---

## 3. Phase 2 必須機能 (まとめ)

- ✅ CONC-01 (thread-safe memory layers, 既存 _lock 活用)
- ✅ CONC-02 (ConcurrentPipeline 最小実装)
- ✅ CONC-03 (BranchExplorer 最小実装)

CONC-04〜08 は Phase 3-4 に倒すが、**設計時点で hooks を残しておく**。

---

## 4. 既存設計との整合性

| 既存要件 | 影響 | 対応 |
|---|---|---|
| FR-12 (Hippocampal Consolidation) | consolidation cycle 中に推論が並走可能 | _lock により mutex 取得、Phase 4 で snapshot isolation 化 |
| FR-23 (Contradiction Detector) | 並列ブランチで矛盾検出が trigger | Phase 3 でブランチ間 contradiction も追加 |
| AC-10/11 (dynamic edge weight) | read_hit / boost が並行発生 | _lock により mutex 取得 (CONC-01) |
| LLW-02 (Wiki Compiler) | consolidate と推論が併走 | Consolidator の `_lock` で cycle 全体を直列化 (粗粒度だが安全) |
| OBS-01/02 (trace + metrics) | 並列 trace が混ざる | request_id でフィルタ、structlog の context binding を活用 |
| BWT (OBS-04) | 並列タスク学習中の計測 | BWTMeter は thread-safe (_lock) |

---

## 5. 実装方針 (Phase 2)

### `llive/orchestration/concurrent.py`

```python
class ConcurrentPipeline:
    def __init__(self, pipeline, max_workers=4):
        self.pipeline = pipeline
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def run_parallel(self, prompts, **kwargs):
        futures = [self._executor.submit(self.pipeline.run, p, **kwargs) for p in prompts]
        return [f.result() for f in futures]

    def submit(self, prompt, **kwargs):
        return self._executor.submit(self.pipeline.run, prompt, **kwargs)

    def close(self):
        self._executor.shutdown(wait=True)


class BranchExplorer:
    def __init__(self, pipeline, container_ids, max_workers=4):
        self.pipeline = pipeline
        self.container_ids = list(container_ids)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def explore(self, prompt, **kwargs):
        # Force container override per branch — Pipeline currently routes by router,
        # so for branch exploration we bypass router and execute a specific container.
        futures = {
            cid: self._executor.submit(
                self.pipeline.run_with_container, prompt, container_id=cid, **kwargs
            )
            for cid in self.container_ids
        }
        return [(cid, f.result()) for cid, f in futures.items()]

    def close(self):
        self._executor.shutdown(wait=True)
```

`Pipeline.run_with_container(prompt, container_id, ...)` を追加する必要あり (Phase 2 の Pipeline 拡張)。

### テスト
- Concurrent submission で memory layer が壊れないこと (3-4 thread × 各 100 events)
- BranchExplorer が独立した PipelineResult を返すこと
- ThreadPoolExecutor shutdown 後の使用が SafeError を出すこと

---

## 6. Out of Scope (v0.6 段階)

- **multi-process 並列** — GIL bypass は Phase 4 で multiprocessing / vLLM 経由
- **GPU 並列推論** — Phase 4 vLLM Adapter で実装
- **分散実行 (multi-node)** — v1.0 後検討
- **asyncio 化** — Phase 4、coroutine ベースの再設計が必要

---

*Drafted: 2026-05-13*
*Phase 2 implementation: CONC-01/02/03 minimum skeleton*
*Phase 3-4: CONC-04〜08 expansion*
