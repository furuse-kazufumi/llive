# llive Core Optimization — Experiments Log (2026-05-20 〜)

> **User goal (2026-05-20)**: 「llive のコア部分の最適化を進める。12 時間後まで
> 情報収集しながら色々と試行してみること。ちゃんと履歴を残して不具合が出ない
> 形に収束させてください。」
>
> Branch: `optimize/core-2026-05-20`
>
> 運用則:
> - main を緑のまま保つ. 試行は本 branch で完結.
> - 失敗した試行も削除せず本ログに残す (honest disclosure).
> - 採用したものだけ main に rebase / cherry-pick.
> - 各 commit に benchmark 差分を付ける ("before X ms / after Y ms / Δ Z%").
> - 不具合検知優先: 各試行後に `pytest tests/unit tests/integration` 全件を
>   確認し緑を維持. 緑でなければ revert.

## Phase A: 情報収集 + Baseline (2026-05-20 朝〜)

### A-1. 現状サマリ (memory + git から)

- **直近 commit**: `17e63bb` (docs(qiita): 2026-05-19 記事 2 draft)
- **HEAD vs origin/main**: 0/0 (up-to-date)
- **test 件数**: 1518 (前回確認 2026-05-20 朝, 114.49s)
- **8 層アーキ**: L1 hardware → L2 core model → L3 adapter → L4 block container
  → L5 memory fabric → L6 evolution → L7 observability → L8 llove HITL
- **Rust acceleration plan**: v0.7 / RUST-01〜14 として要件確定済 (Phase 5
  から着手, Phase 4 安定後の措置). 現状は Python 純実装.
- **既存 benchmark scripts** (`scripts/`):
  - `bench_progressive.py` — xs/s/m/l/xl × model のサイズ感応性
  - `bench_continuous_briefs.py` — Brief API 連続実行
  - `bench_large_input.py` — 大入力耐性
  - `bench_soak_500.py` — 500 回 soak
  - `bench_codebase_stats.py` — LOC / module 統計
  - `bench_annotations.py` / `bench_vrb.py` / `bench_oka_pipeline.py` / etc.

### A-2. memory rules (最適化に効くもの)

- [[feedback-llive-measurement-purity]] — llive 単体 (on-prem) vs cloud 直接の
  2 系統分離. 混在しない.
- [[feedback-benchmark-progressive-tokens]] — xs/s/m/l/xl 5 段階 curve.
- [[feedback-benchmark-honest-disclosure]] — 異常値が出たら必ず内訳を疑う.
  5 因子 (warmup hit / token normalization / RTT 除外 / attach overhead /
  system load) で分解.
- [[feedback-implementation-status-record]] — 4 段階 (実装済 / 未配線 /
  部分実装 / 未実装) を明示.
- [[project-llive-rust-acceleration]] — Rust 化は Phase 5+ で意味論凍結後.
  **本セッションでは Python 純実装の中で最適化** (Rust 化はしない).

### A-3. 最適化対象の候補 (memory + コード grep から)

candidate hot spots (project_llive_rust_acceleration.md より既知, 本セッションで Python 範囲内で改善する候補):

| # | 領域 | 既知の遅さ | Python 範囲の改善案 |
|---|---|---|---|
| 1 | Bayesian surprise (cosine 計算) | 80-150ms (純 Python) | numpy 強制ベクトル化, prealloc, dtype 固定 |
| 2 | Edge weight bulk decay | 8s | bulk SQL, batch transaction, prepared statement |
| 3 | Jaccard / cosine 類似度 | 純 Python set ops | numpy / frozenset / 集合演算最適化 |
| 4 | jsonschema 検証 | 純 Python | `fastjsonschema` への切替 (Python ライブラリ) |
| 5 | JSONL audit sink | I/O 待ち | buffered writer / async batch flush |
| 6 | TRIZ matrix lookup | 線形検索 | dict 化 / `functools.lru_cache` |
| 7 | FullSenseLoop stage diag overhead | per-stage 計測 | optional flag で off / 集約結果のみ |

これらをひとつずつ baseline → 試行 → 採否で回す.

### A-4. baseline 計測 (進行中)

- **pytest unit 全件 実行時間** — measuring (background)
- **bench_progressive smoke** — TBD
- **bench_codebase_stats** — TBD
- **cProfile on Brief API single call** — TBD

数値は別ファイル `baselines.json` にも保存予定 (後段で diff 用).

---

## Phase B: 実験ループ

実験は 1 試行 = 1 サブセクションで記録. テンプレ:

```
### B-N. <短いタイトル>

- **仮説**: 何が遅いと予想したか
- **変更内容**: 何を変えたか (commit hash あれば)
- **計測**:
  - before: <metric> = X
  - after:  <metric> = Y
  - Δ: Z% (改善 / 悪化 / 同等)
- **回帰確認**: pytest 結果, 緑 / 失敗
- **採否**: 採用 (main へ cherry-pick) / 不採用 (本 branch に残置) / 保留
- **学び**: 副次的に分かったこと
```

(以降, 実験ごとに追記)
