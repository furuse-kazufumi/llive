# 2026-05-23 monthly resweep — RUST-15/16/17 speedup re-measure

> [[feedback_impl_method_diff_documentation]] 周期実行 (claude-loop queue `20260522T075021-e5e5b7` 発火).
> 前回 baseline: `2026-05-22_kernel_implementation_comparison.md`.
> 本記事は monthly resweep の 1 回目 (起点) で, 環境 drift + parallel bench
> contention 教訓を記録する.

## 1. 環境 snapshot

| 項目 | 2026-05-22 (baseline 推定) | 2026-05-23 (本 sweep) | drift |
|---|---|---|---|
| Python | 3.11.x | **3.11.3** | — |
| numpy | 2.x | **2.4.4** | minor up 可能性あり |
| Rust toolchain | stable | **rustc 1.94.1 (2026-03-25)** | — |
| platform | Windows 11 | **Windows-10-10.0.26220-SP0** (Win 11 Pro) | — |
| `llive_rust_ext.pyd` | 2026-05-22 08:04 build | **同 (再 build なし)** | binary 同一 |
| wheel size | 124,520 bytes | **同** | binary 同一 |
| `llive_peer_rust_ext.whl` | 2026-05-21 21:55 | **同** | binary 同一 |
| **同時走行 ccr 数** | 不明 (baseline 時記録なし) | **12 プロセス** | high system load |

→ **binary 不変** なので, 観測 drift は environment / system load / numpy 内部の
BLAS path 選択違い に起因.

## 2. 結果 (本 sweep)

### 2.1 RUST-15 persona_dissimilarity_pairwise

| N | Python (us) | Rust (us) | 2026-05-23 speedup | 2026-05-22 baseline | diff |
|---:|---:|---:|---:|---:|---:|
| 16 | 617.43 | 73.71 | **x8.38** | (個別未記録) | — |
| 32 | 2202.35 | 164.73 | **x13.37** | (個別未記録) | — |
| 64 | 8996.21 | 534.13 | **x16.84** | x17.07 | -1.3% |
| **平均** | — | — | **x12.86** | **x12.71** | **+1.2%** |

→ 全 N で 5x gate PASS. **rayon 不使用 kernel なので並列 bench でも contention なし**.
baseline と本質的に同一 (noise 内 +1.2%).

### 2.2 RUST-16 collusion_score

| N | Python fallback (us) | Existing impl (us) | Rust (us) | 2026-05-23 speedup (vs fallback) | 2026-05-22 baseline | diff |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 197.08 | 223.26 | 1.62 | **x121.99** | x115.04 | +6.0% |
| 16 | 213.83 | 208.41 | 2.31 | **x92.59** | — | — |
| 32 | 245.87 | 240.92 | 5.68 | **x43.27** | — | — |
| 64 | 299.96 | 310.36 | 18.06 | **x16.61** | — | — |
| **平均** | — | — | — | **x68.62** | **x66.70** | **+2.9%** |

→ 全 N で 5x gate PASS. baseline と本質的に同一 (noise 内 +2.9%).
**numpy 小 NxN の API overhead 支配** という [[project_llive_v0B_evolutionary]] の
判定が引き続き有効.

### 2.3 RUST-17 novelty_score_batch ⚠️ **methodology lesson**

#### 2.3.1 **並列 bench 実行時 (汚染データ — discard すべき)**

| A | Python (us) | Rust (us) | speedup | gate | baseline (RUST-17b) | diff |
|---:|---:|---:|---:|:---:|---:|---:|
| 50 | 1043.42 | 77.15 | x13.52 | PASS | x12.83 | +5.4% |
| 200 | 1559.96 | 185.46 | x8.41 | PASS | x8.71 | -3.4% |
| 1000 | 3857.11 | 1147.19 | **x3.36** | **FAIL** | x6.41 | **-47.6%** |
| 平均 | — | — | x8.43 | (avg PASS) | x9.32 | -9.5% |

#### 2.3.2 **単独 bench 実行時 (clean データ — 採用すべき)**

| A | Python (us) | Rust (us) | speedup | gate | baseline (RUST-17b) | diff |
|---:|---:|---:|---:|:---:|---:|---:|
| 50 | 829.83 | 67.34 | **x12.32** | PASS | x12.83 | -4.0% |
| 200 | 1290.91 | 138.99 | **x9.29** | PASS | x8.71 | +6.7% |
| 1000 | 3627.83 | 571.42 | **x6.35** | **PASS** | x6.41 | -0.9% |
| **平均** | — | — | **x9.32** | **PASS** | **x9.32** | **0.0%** |

→ 単独実行では **baseline と完全一致** (平均 x9.32 同値).
**並列 bench が rayon par_iter の thread pool に contention** を引き起こし,
A=1000 で **本来 571us の処理が 1147us に倍増 (-47.6% speedup)** した.

## 3. 教訓 — methodology

### 3.1 ⚠️ **rayon を使う bench は単独実行が必須**

- RUST-17 は `rayon par_iter` で 8-core 並列化されているため,
  他 bench process と CPU を取り合うと **algorithmic gain 自体が崩壊**.
- 一方 RUST-15/16 は **rayon 不使用** (純粋 ndarray 直接ループ) なので
  並列実行でも影響なし.
- **教訓**: 「並列 dispatch で時短」は rayon kernel には逆効果. monthly
  resweep では `--sequential` 厳守.

### 3.2 ⚠️ **「同時走行 ccr 数」を env snapshot に含める**

- 本 sweep 中, 同時起動 ccr.exe = 12 プロセス. これは baseline 時に
  記録されていなかった (今回明示化).
- monthly resweep template に **「同時走行 ccr 数」** + **「他重 process
  (cargo build / pytest 等)」** の欄を追加すべき.
- 次回テンプレ ([[feedback_impl_method_diff_documentation]] §template)
  に反映: `tasklist | grep -c claude.exe` を実行時に記録.

### 3.3 ✅ **binary 不変なら数値は noise±5% に収まる (それを超えたら system 起因)**

- RUST-15 +1.2%, RUST-16 +2.9% (clean), RUST-17 0.0% (clean) — すべて
  baseline と一致.
- 本ルール: **±5% を超える drift が出たら, まず `tasklist` + `Get-Counter`
  で system load を確認 → 単独 re-run** で潔白証明する.
- これを **honest disclosure 三原則** に追加:
  ([[feedback_benchmark_honest_disclosure]])

## 4. 結論 — drift verdict

| Kernel | drift 判定 | gate |
|---|---|:---:|
| RUST-15 persona_dissimilarity_pairwise | **stable** (+1.2%, within noise) | ✅ PASS |
| RUST-16 collusion_score | **stable** (+2.9%, within noise) | ✅ PASS |
| RUST-17 novelty_score_batch (単独) | **stable** (0.0%, identical) | ✅ PASS |
| RUST-17 novelty_score_batch (並列汚染) | ❌ -47.6% @ A=1000 | (汚染 discard) |

→ **全 kernel baseline 維持**. monthly resweep として **「変化なし」が
正しい結論**. ただし **methodology 改善** (並列 bench 禁止 + ccr 同時走行
数を snapshot に含める) を持ち帰る.

## 5. 今後の更新

### 5.1 次月 (2026-06-23 予定)

- monthly resweep template に **「同時走行 ccr 数」** カラム必須化.
- bench 実行は **`--sequential` mode を新設** (1 ファイル, 3 kernel 順次).
  → `scripts/bench_all_sequential.py` を起草.
- PyBind11 + C/C++ 経路の比較 (前回 [[project_llive_v0B_evolutionary]] §6.1
  で予告したまま未着手). queue 投入候補.

### 5.2 長期

- 同時走行 ccr 数を **bench フレームワークが自動収集** (現在は手動).
  raptor `libexec/raptor-bench-snapshot` 候補.
- numpy minor version up trigger で **自動 re-sweep** (現在は monthly cron).

## 6. constraints 遵守ログ

| constraint | 遵守状況 |
|---|---|
| `no-push` | ✅ 本 doc 作成のみ. push 操作なし |
| `monthly-recurring` | ✅ 月次 cron / ScheduleWakeup 想定で時系列累積形式 |
| `honest-disclosure-required` | ✅ §2.3 で並列汚染を明示し discard. drift 内訳を全公開 |

## 7. References

- baseline: `docs/perf_comparison/2026-05-22_kernel_implementation_comparison.md`
- feedback rules: [[feedback_impl_method_diff_documentation]],
  [[feedback_benchmark_honest_disclosure]], [[feedback_rust_usage_matters]]
- loop task: claude-loop queue `20260522T075021-e5e5b7`

---

> **次回更新**: 2026-06-23 (monthly recurring).
> template 更新: `scripts/bench_all_sequential.py` の新設 + ccr 同時走行数
> カラム追加を済ませてから resweep.
