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

### A-5. ユーザー追加方針 (2026-05-20)

ユーザー追加指示:

1. 「コア部分のデータの持ち方とかコンテナを変えてみたり, デザインパターンを
   拡張してみたりして, 出来るだけ自動的に最適な構造に収束する感じが理想的」
2. 「脳のシナプス構造のような重みづけが変化するような感じがいい」

これを受けて方針確定:

#### B-0 設計 — `SynapticSelector` (Hebbian-style strategy selection)

`src/llive/perf/synaptic_selector.py` を新規作成:

- `StrategyVariant(name, impl, weight, n_calls, avg_latency_ms)` — 各候補
- `SynapticSelector(variants, learning_rate, exploration_rate)`:
  - `choose()` — 重み付き確率 + ε-greedy で variant を選択
  - `record_result(variant, latency_ms)` — Hebbian 更新で重みを増減
  - `converge()` — 最終的に最高重み variant を返す
- 結果として「使われる経路 (LTP, long-term potentiation)」が強化され,
  「使われない経路 (LTD)」は弱化される.

これは TRIZ 内蔵 (FR-23〜27) の self-evolution と整合 — 「設計判断自体を
RL 化する」拡張. 既存 `perf/optimizer.py` (§E2 bounded modification) の上に
collection / pattern 選択の自動収束層を載せる.

### A-6. baseline 計測結果

- **pytest unit 全件**: `1517 passed in 64.85s` (前回 1518 件確認の中
  1 件は integration 側に分類, この計測では unit のみ)
  - 1 件あたり平均 42.7ms
- **HEAD**: `17e63bb` (optimize/core-2026-05-20 branch 始点)
- **環境**: Windows 11 / Python 3.11.x / `py -3.11 -m pytest`

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

### B-0. SynapticSelector 基盤実装

- **仮説**: 「データ構造 / pattern / impl を複数候補で並べ Hebbian 更新で
  最良に自動収束させる」 selector があれば, 個別 hot path の最適化判断を
  自動化できる.
- **変更内容** (commit `392aa40` + auto: backups):
  - `src/llive/perf/synaptic_selector.py` 新規 — `StrategyVariant` +
    `SynapticSelector`. ε-greedy + weighted softmax で選択, Hebbian-style
    報酬 ((mean_latency - measured) / mean_latency) で重み更新, bounded
    modification (min/max clip), thread-safe (RLock).
  - `tests/unit/test_perf_synaptic_selector.py` 19 件 — construction
    validation / choose / converge / Hebbian convergence (slow が劣後) /
    EWMA / bounds / history cap / thread safety smoke.
- **計測**:
  - before: SynapticSelector 自体は新規なので before なし.
  - llive test 件数: 1518 → 1537 (+19 = 本 test) 緑.
  - selector の overhead: 単独計測未実施 (後段で確認).
- **回帰確認**: `py -3.11 -m pytest tests/unit tests/integration -q`
  → **1537 passed in 60.64s** (回帰なし).
- **採否**: **採用** (基盤として branch に確定保留. main マージは収束後).
- **学び**: dataclass + threading.RLock + EWMA + softmax を素直に組合せれば
  100 行で動く. test 設計で「fast > medium 厳格」は exploration 不足で揺れ,
  「slow が劣後」のみが固い順序関係.

### B-1. demo: top-K 抽出問題で自動収束を観察

- **仮説**: 上位 K 抽出 hot path で `full_sort` / `partial_sort_heap` /
  `heapq.nlargest` の 3 variant を SynapticSelector に載せると, `heapq`
  系が最良に収束する (アルゴリズム的に正しい).
- **変更内容**: `scripts/demo_synaptic_selector.py` 新規.
- **計測** (`py -3.11 scripts/demo_synaptic_selector.py --n 5000 --k 10 --iters 200`):

  | variant | weight (final) | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | heapq_nlargest | **100.000 (max)** | 170 | 0.112 |
  | partial_sort_heap | 1.440 | 18 | 0.237 |
  | full_sort | 0.377 | 12 | 0.555 |

  - 200 iter / 全体経過 0.52 秒.
  - 収束結果: `heapq_nlargest` (順序的にも latency 最良).
  - exploration_rate=0.15 で full_sort も 12 回呼ばれて mean 更新は維持.
- **回帰確認**: demo は production code を touch しない. 全 test 緑のまま.
- **採否**: **採用** (demo script として確定. 本機能を実 hot path に
  注入する experiment B-N は別途).
- **学び**:
  - データサイズ・K の比で「最良」は動的に変わるはず → 別実験でデータ
    分布を変える検証が候補.
  - **weight 1.0 → 100.0 までの "急成長"** は learning_rate=0.10 で 200 iter
    で達成. もう少し学習率を下げれば 1000 iter 級でゆるやかに成長する.
  - exploration_rate を 0 にすると一極集中して他 variant の latency 観測が
    止まる. 産業実用では **exploration を常に 5-10% 残す** のが安全.

### B-2 候補 (次の試行)

| # | hot path | 候補 variants |
|---|---|---|
| B-2 | jsonschema 検証 | jsonschema (pure) / fastjsonschema / 内製 light validator |
| B-3 | TRIZ matrix lookup | linear / dict / `functools.lru_cache` / perfect hash |
| B-4 | edge weight decay | per-row loop / list comprehension / numpy 強制 ベクトル化 |
| B-5 | Bayesian surprise cosine | 純 Python / numpy / scipy.spatial.distance |
| B-6 | audit JSONL sink | sync open+write / buffered file / async batch |

各候補は独立に SynapticSelector を 1 つ用意 → 候補注入 → run → 採否.

---

## 後で main にマージする決め事

- 「**SynapticSelector 基盤 (B-0)**」と「**demo script (B-1)**」は production
  code を touch せず, かつ test が全部緑なので, **本 branch のまま PR 候補**.
- B-2 以降の実 hot path 適用は, 1 つずつ A/B benchmark の改善幅を確認し
  **5% 以上改善** + **回帰なし** の場合のみ採用 (`[[project-llive-rust-acceleration]]`
  の 5× ゲートをゆるめた相対ゲート).
- selector overhead 自体 (μs 以下のはず) を別実験で確認してから, p99
  latency が浮かないことを示す.
