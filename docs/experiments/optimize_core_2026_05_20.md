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

### B-2. cosine 類似度の variants 自動収束

- **仮説**: cosine 類似度は llive memory tier の多用 hot path. 4 つの
  implementation (pure_python / numpy_dot / numpy_einsum / numpy_normalized)
  を SynapticSelector に load すれば, **ベクトル次元に応じて最良候補が
  自動選択** されるはず. 特に「事前 L2 normalize 済み input なら norm 計算を
  スキップできる numpy_normalized が支配的」になることを予測.
- **変更内容** (commit pending):
  - `src/llive/perf/variants/__init__.py` 新規 (variants パッケージ宣言)
  - `src/llive/perf/variants/cosine_variants.py` 新規 (4 variants + ALL_VARIANTS)
  - `tests/unit/test_perf_cosine_variants.py` 新規 (parity 10 件: 各 dim で
    pure_python / numpy_dot / numpy_einsum が ε 以内, normalize 前提下で
    numpy_normalized も一致)
  - `scripts/demo_synaptic_cosine.py` 新規 (3 次元 16/128/768 で自動収束)
- **計測** (`py -3.11 scripts/demo_synaptic_cosine.py --dim <D> --iters 500`):

  **dim=16:**

  | variant | weight | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | numpy_normalized | **100.000 (max)** | 420 | 0.00139 |
  | numpy_dot | 1.343 | 29 | 0.00626 |
  | pure_python | 0.785 | 22 | 0.00764 |
  | numpy_einsum | 0.386 | 29 | 0.00887 |

  **dim=128:**

  | variant | weight | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | numpy_normalized | **100.000 (max)** | 421 | 0.00153 |
  | numpy_dot | 6.440 | 29 | 0.00523 |
  | numpy_einsum | 3.374 | 30 | 0.00980 |
  | pure_python | 0.028 | 20 | 0.04759 |

  **dim=768:**

  | variant | weight | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | numpy_normalized | **100.000 (max)** | 421 | 0.00277 |
  | numpy_dot | 11.644 | 28 | 0.00548 |
  | numpy_einsum | 11.137 | 31 | 0.01314 |
  | pure_python | 0.010 | 20 | 0.26979 |

  全 3 次元で `numpy_normalized` (pre-normalize) が収束.
- **回帰確認**: parity test 10 件全緑. demo は production code を touch
  しないので既存 test 影響なし.
- **採否**: **採用** (variants + demo を branch に確定). production 注入は
  別 B として後段で判断.
- **学び (重要)**:
  1. **pre-L2-normalize caching** が最大の自由度. cosine の 50-80% を
     norm 計算が占めている.
  2. **小次元 (dim=16) では pure_python が numpy と拮抗** (0.764us vs
     0.626us). 既存実装は numpy 固定なので, 極小次元では微妙に損している
     可能性. 数百〜千次元の embedding ではこの問題は無い.
  3. **dim=128 以降では pure_python は完全に劣化** (30-90 倍). 次元増大
     とともに numpy vectorization の advantage が指数的に出る.
  4. **production 提案** (次の実 hot path 適用 B 候補):
     - `memory/surprise.py` の `_l2_normalize` 結果を memory tier の
       embedding cache に保持 → cosine 計算は `numpy_normalized` 経路で
       実行できる
     - 効果見込み: 2-5 倍高速化 (norm 計算スキップ分)

### B-4. edge weight decay の variants 自動収束 — **selector の限界を発見**

- **仮説**: edge graph の bulk decay は N (要素数) に依存して最良 variant が
  動的に変わるはず. 小 N では Python の listcomp / loop が numpy overhead
  を下回り, 大 N では numpy 圧勝.
- **変更内容** (commit pending):
  - `src/llive/perf/variants/decay_variants.py` 新規 (5 variants:
    py_loop / py_listcomp / py_map / np_inplace / np_einsum)
  - `tests/unit/test_perf_decay_variants.py` 15 件 (parity / zero rate /
    identity rate / input non-mutation guarantee)
  - `scripts/demo_synaptic_decay.py` 新規 (N=100/10000/100000 で自動収束)
- **計測** (`py -3.11 scripts/demo_synaptic_decay.py --n <N> --iters <I>`):

  **N=100, iters=300:**

  | variant | weight | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | np_inplace | **100.000 (max)** | 247 | 0.00144 |
  | np_einsum | 1.237 | 18 | 0.00515 |
  | py_listcomp | 1.120 | 9 | 0.00657 |
  | py_loop | 1.014 | 6 | 0.00801 |
  | py_map | 0.789 | 20 | 0.00963 |

  → 期待通り `np_inplace` が圧勝 (最速).

  **N=10000, iters=300:**

  | variant | weight | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | np_einsum | **100.000 (max)** | 252 | 0.01000 |
  | np_inplace | 6.396 | 21 | 0.00962 |
  | py_listcomp | 0.821 | 7 | 0.60953 |
  | py_loop | 0.617 | 6 | 0.79307 |
  | py_map | 0.259 | 14 | 0.82440 |

  → **問題**: 実は `np_inplace` (0.00962ms) の方が `np_einsum` (0.01000ms)
  より速いが, weight は `np_einsum` が 100 (max) に収束.

  **N=100000, iters=200:**

  | variant | weight | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | np_einsum | **100.000 (max)** | 160 | 0.23480 |
  | np_inplace | 3.345 | 15 | 0.19746 |
  | py_listcomp | 0.831 | 7 | 5.91169 |
  | py_loop | 0.620 | 6 | 8.31332 |
  | py_map | 0.260 | 12 | 9.32972 |

  → 同じ問題: `np_inplace` (0.19746ms) が `np_einsum` (0.23480ms) より
  17% 速いのに収束は `np_einsum`.

- **回帰確認**: llive 1547 → **1562 緑** (+15 = decay parity test).
- **採否**: **採用** (variants + demo を branch 確定). production 注入は
  避けるべき判断. なぜなら次の honest disclosure が示すように selector の
  早期収束 bias を含むため.

- **学び (honest disclosure)**:
  1. **小 N (=100) では SynapticSelector は正しく np_inplace に収束**.
  2. **中〜大 N (10000+) では一極集中 dynamics により実は遅い variant
     (np_einsum) に収束する病理現象が発生**:
     - 序盤に偶然 np_einsum が greedy 経路に乗ると重みが伸びる
     - softmax で更に偏り np_inplace は exploration round (15%) でしか
       呼ばれず重みが伸びない
     - 結果: avg_latency_ms 上は np_inplace が真の最良なのに converge は
       np_einsum

  この弱点は **本セッションで最も価値ある発見**. SynapticSelector を
  production に注入する前に, 以下のいずれかが必要:

  - **対策案 A**: ε-greedy ではなく UCB (Upper Confidence Bound) ベース
    に切替. 試行回数が少ない variant に exploration bonus.
  - **対策案 B**: exploration_rate を時間 annealing せず一定で長期保持.
  - **対策案 C**: 重み更新の reward を「他 variant の avg_latency_ms
    との相対値」に変更 (現状は全 active 平均との差).
  - **対策案 D**: 一定 round ごとに全 variant を確認 round で強制実行.

  これは [[feedback-benchmark-honest-disclosure]] の精神そのもの: **「異常に
  良い結果が出たら必ず内訳を疑う」** = ここでは「収束結果が最良と言い切る
  前に avg_latency_ms と比較し直す」.

### B-5. UCBSynapticSelector を実装 — B-4 病理が完全解消

- **仮説**: B-4 の早期収束 bias は ε-greedy の構造的欠陥. UCB1
  (Auer 2002) の `mean_reward + c * sqrt(ln(total) / n)` ベースに切替えれば
  試行回数が少ない variant に exploration bonus が付き, 真の最良に収束する.
- **変更内容** (commit pending):
  - `src/llive/perf/synaptic_selector.py` に `UCBSynapticSelector` クラス追加
    (既存 `SynapticSelector` と同形 API, backward compatible).
    - `choose()`: 未試行は最優先, それ以外は UCB1 max を選ぶ.
    - `_compute_rewards()`: 全 variant の latency_window 内平均を [0, 1] に
      reverse-normalize (短い latency → 高 reward).
    - `record_result()`: latency を FIFO window (default 64) で保持し
      reward を再計算.
  - `tests/unit/test_perf_ucb_synaptic_selector.py` 15 件 (construction
    validation / 未試行最優先 / 真の最良収束 / exploration 分布 /
    snapshot reward / latency_window / thread safety).
  - `scripts/demo_synaptic_decay_ucb.py` 新規 (B-4 と同じ decay variants
    を UCB で run).
- **計測** (UCB demo, B-4 と同条件):

  **N=100, iters=500:** converged_to = **np_inplace** ✓

  | variant | reward | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | np_inplace | 0.9723 | 227 | 0.00196 |
  | np_einsum | 0.8069 | 78 | 0.00644 |
  | py_listcomp | 0.7764 | 68 | 0.00768 |
  | py_loop | 0.7529 | 66 | 0.00780 |
  | py_map | 0.6455 | 61 | 0.01061 |

  **N=10000, iters=500:** converged_to = **np_inplace** ✓ (B-4 では誤って np_einsum)

  | variant | reward | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | np_inplace | 0.9977 | 212 | 0.00765 |
  | np_einsum | 0.9927 | 204 | 0.01200 |
  | py_listcomp | 0.6739 | 39 | 0.56547 |
  | py_loop | 0.5105 | 24 | 0.88291 |
  | py_map | 0.4614 | 21 | 0.84398 |

  **N=100000, iters=300:** converged_to = **np_inplace** ✓ (B-4 では誤って np_einsum)

  | variant | reward | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | np_inplace | 0.9863 | 135 | 0.22785 |
  | np_einsum | 0.9845 | 133 | 0.25047 |
  | py_listcomp | 0.3977 | 15 | 6.16804 |
  | py_loop | 0.1446 | 9 | 8.02684 |
  | py_map | 0.0651 | 8 | 9.05241 |

- **回帰確認**: llive 1562 → **1577 緑** (+15 = UCB test). 既存
  SynapticSelector test 19 件もそのまま緑 (backward compat 維持).
- **採否**: **採用** (UCBSynapticSelector を branch 確定).
  **production への注入推奨は本 UCB 版**. ε-greedy 版は demo / 軽量用途のみ.

- **学び**:
  1. UCB は np_inplace と np_einsum を 212 vs 204 とほぼ均等に試行し
     公平比較した上で僅差で np_inplace を選んだ → **真の最良判定**.
  2. py_系 (loop/listcomp/map) は早期に低 reward と判明し試行回数を
     15-39 に絞った → **探索効率も良い**.
  3. UCB は exploration bonus が時間とともに減衰 (`sqrt(ln t / n)` の
     `1/sqrt(n)` 項) するので, 長期的には自然と greedy 化する. ε-greedy
     のように exploration_rate を手動 tuning しなくても良い.
  4. Hebbian-style の SynapticSelector と UCB は **棲み分け**:
     - ε-greedy (Hebbian): 短期で greedy 寄りに動く. 候補が明確に差がある
       場合, demo / 軽量探索向け.
     - UCB: 真の最良判定を確実にしたい場合, production 注入用.

### B-6. sliding window container 自動収束 — deque が圧勝

- **仮説**: 「先頭 pop + 末尾 push を N 回」という古典的 sliding window
  操作で `list.pop(0)` (O(N)) と `list[1:]+[x]` (O(N) copy) と
  `collections.deque(maxlen=N)` (O(1)) を比較. 理論的には deque 圧勝.
- **変更内容**:
  - `src/llive/perf/variants/sliding_window_variants.py` 新規 (3 variants)
  - `tests/unit/test_perf_sliding_window_variants.py` 8 件 (parity)
  - `scripts/demo_synaptic_sliding_window.py` 新規 (UCB 版)
- **計測**:

  **maxlen=100, pushes=5000, iters=100:** converged_to = **deque**

  | variant | reward | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | deque | 0.9919 | 55 | 0.17309 |
  | list_popzero | 0.9047 | 38 | 0.43242 |
  | list_slice | 0.2347 | 7 | 2.59791 |

  **maxlen=1000, pushes=10000, iters=50:** converged_to = **deque**

  | variant | reward | n_calls | avg_latency_ms |
  |---|---:|---:|---:|
  | deque | 0.9982 | 24 | 0.32391 |
  | list_popzero | 0.9646 | 22 | 1.77255 |
  | list_slice | 0.0957 | 4 | 38.69049 |

  maxlen 増大に伴い list_slice の劣化が激しい (3x → 119x). deque は
  常に最速で安定.

- **回帰確認**: llive 1577 → **1585 緑** (+8 = sliding window parity).
- **採否**: **採用** (variants + demo を branch 確定). 教科書的な
  「データ構造選択の自動収束」例.
- **学び**:
  1. 古典的な計算量差 (O(N) vs O(1)) は UCB で 50-100 iter で明確に
     判別される. exploration round の試行回数差が UCB の効率性を示す
     (deque 55 vs list_slice 7).
  2. list_slice は maxlen=1000 で 38ms 程度かかる. これは「Python の
     list 操作は気軽に使うと毎回 O(N) で痛い」典型例.
  3. production への適用候補: memory tier で「recent N events」を保持
     する箇所. 既存実装が list ベースなら deque 移行で 2-5x 高速化見込み.

### B-7 以降の候補

| # | hot path | 候補 variants | 状態 |
|---|---|---|---|
| B-7 | audit JSONL sink | sync / buffered / async batch | 候補 |
| B-8 | jsonschema 検証 | jsonschema (pure) / fastjsonschema / 内製 light | 外部依存追加要, 保留 |
| B-9 | UCB を実 production hot path に注入 | (memory tier の cosine 等) | 採用ゲート: 5% 改善 + 全 test 緑 |

---

## 後で main にマージする決め事

- 「**SynapticSelector 基盤 (B-0)**」と「**demo script (B-1)**」は production
  code を touch せず, かつ test が全部緑なので, **本 branch のまま PR 候補**.
- B-2 以降の実 hot path 適用は, 1 つずつ A/B benchmark の改善幅を確認し
  **5% 以上改善** + **回帰なし** の場合のみ採用 (`[[project-llive-rust-acceleration]]`
  の 5× ゲートをゆるめた相対ゲート).
- selector overhead 自体 (μs 以下のはず) を別実験で確認してから, p99
  latency が浮かないことを示す.
