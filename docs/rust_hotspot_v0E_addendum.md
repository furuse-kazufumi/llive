# Rust 高速化 v0.D/v0.E hotspot addendum (RUST-FX 拡張)

> 作成: 2026-05-21 marathon (Goal: [[goal_release_ready_v0E_rust]]).
>
> 目的: v0.D/v0.E で着地した派生集団進化 / governance / quality-diversity
> module のうち, **どこを Rust 化すれば実用的にトクか** を hot-path 視点で
> 棚卸しし, parity test の方針と段階順を決める. 実 Rust 実装は次セッション以降.

## 1. 既存 Rust 拡張 (v0.5.0)

`crates/llive_rust_ext/src/lib.rs` には現状 3 kernel:

| RUST ID | 関数 | 用途 | Status |
|---|---|---|---|
| RUST-02 | `compute_surprise` | cosine surprise (MEM-07) | ✓ v0.5.0 wire-in |
| RUST-03 | `bulk_time_decay` | edge weight decay (RUST-03) | ✓ v0.5.0 wire-in |
| RUST-04 | `jaccard` | id-set Jaccard | ✓ v0.5.0 wire-in |

これらは Python `llive.rust_ext` 経由で自動委譲, 不在時 numpy fallback,
1e-6 parity gate あり.

## 2. v0.D/v0.E hotspot 棚卸し

### 2.1 高優先 (RUST-NEW-A) — 評価あたり呼出し頻度大

#### A-1. `persona_dissimilarity(a, b)` — RUST-15 候補

- 場所: `src/llive/perf/evolutionary/persona.py:425`.
- 計算: `(1 - Jaccard(id sets)) * 0.5 + L2(effective_factor_affinity diff) * 0.5`.
- 呼出 hotspot:
    - `PersonaOverlapPenalty.apply` で集団 N×N (2026-05-21 着地).
    - 派生集団 N=64 で 1 世代あたり 2016 回. 1000 世代 marathon で 2M 回.
- Python の plain loop は L2 + Jaccard を都度計算するため遅い.
- Rust 化案:
    - `pub fn persona_dissimilarity_batch(left_ids, right_ids, left_aff, right_aff) -> Vec<f32>`.
    - Jaccard は既存 `jaccard()` kernel 流用可 (id を u32 にハッシュ).
    - L2 は naive SIMD (`std::simd` or `wide`) で 8 lane.
- Parity gate: 1e-6 (Python persona_dissimilarity と比較).

#### A-2. `MAPElitesGrid.key` + `submit` — RUST-NEW-B 候補

- 場所: `src/llive/perf/evolutionary/quality_diversity.py:_bin / key / submit`.
- 計算: 4 軸 binning + dict 引き比較 + 更新.
- 呼出 hotspot:
    - 1 世代で全個体を submit. N=64 × 1000 世代 = 64K 回.
    - bin 計算は分岐 3 + 浮動小数除算 1 = 1 つあたり ~50ns Python.
- Rust 化案:
    - `pub fn map_elites_bin(value, low, high, n_bins) -> u32`.
    - `pub fn map_elites_keys_batch(features: Vec<(f32,f32,f32,f32)>, ranges, n_bins) -> Vec<(u32,u32,u32,u32)>`.
- Parity gate: bit-exact (int 比較).

### 2.2 中優先 (RUST-NEW-B) — 大量データ / 並列性あり

#### B-1. `PeerEvaluationMatrix.collusion_score` — RUST-16 候補

- 場所: `src/llive/perf/evolutionary/peer_evaluation.py:171`.
- 計算: NxN matrix の variance / symmetry corrcoef / column_mean top-1 / mean.
- 呼出 hotspot: governance evaluate_generation 毎. 多くないが N×N で O(N²).
  N=64 で 4096 cell. 1000 世代で 4M cell.
- Rust 化案: ndarray + rayon の row-parallel.
- Parity gate: 1e-6.

#### B-2. `NoveltyScorer.novelty` k-NN — RUST-17 候補

- 場所: `src/llive/perf/evolutionary/diversity.py:NoveltyScorer.novelty`.
- 計算: archive (up to 1000) × 19 dim L2, top-k.
- 呼出 hotspot: 派生集団 N=64, archive 1000 で 1 世代 64K 距離計算.
- 既存 `compute_surprise` (cosine) と同形だが L2 + top-k.
- Rust 化案: rayon + bincount で top-k sort.
- Parity gate: 1e-6.

### 2.3 低優先 (RUST-NEW-C) — 呼出少 / 既存 OK

- `PersonaImportAlgorithm.plan` — cosine 1 回 / persona. 呼出数少. Rust 不要.
- `SurvivalRateTracker.observe` — dict 操作中心. Rust 不要.
- `PersonaCorpusLoader.keyword_extractor` — substring count. Rust 化すれば
  10x 程度速くなるが corpus 解析は session 中 1 回しか走らないので **見送り**.

## 3. 段階計画 (RUST-FX addendum)

| ID | 内容 | Phase | 依存 |
|---|---|---|---|
| RUST-15 | persona_dissimilarity Rust 化 + batch | v0.7 | maturin / pyo3 |
| RUST-16 | collusion_score (peer matrix metrics) Rust 化 | v0.7 | RUST-15 完了後 |
| RUST-17 | NoveltyScorer L2 + top-k batch Rust 化 | v0.7 | RUST-15 完了後 |
| RUST-NEW-B | MAPElites bin + submit batch | v0.7 | RUST-15 |
| RUST-18 | parity test harness 拡張 (E.17 / E.4) | v0.7 | 上記全部 |

## 4. Parity test 方針

- 既存 `tests/unit/test_rust_ext_parity.py` (Hypothesis) に **A-1 / A-2 用ケース** を
  追加する. RUST-13 と同じ「Python ↔ Rust の出力 1e-6 一致」 gate.
- Mock corpus は np.random.default_rng(seed=0) で確定.

## 5. 5× ゲート (memory rule)

[[project-llive-rust-acceleration]] に従い, 各 RUST 関数は
**Python 比 5x 以上の速度向上** を要件にする. ベンチは
`benches/bench_rust_ext_5x_gate.py` に統合 (現 v0.5.0 で MEM-07 / RUST-03 は
clear 済み, 平均 16.18x).

E.17 関連: `persona_dissimilarity` の Python 実装は L2 + Jaccard が
**毎回 numpy + set 構築**. Rust naive 実装 (no SIMD) でも 5x は確実に
クリア可能と推定. SIMD ありで 10-15x 目標.

## 6. リスク

- pyo3 0.24.2 + Windows / Linux / macOS の CI matrix が現在動いている.
  新 kernel 追加時に Rust panic を unwind 経由で安全に Python 例外に
  落とすこと (RUST-13 hypothesis parity で検証).
- maturin develop でローカル wheel が壊れると tests/ がフォールバック
  経路に倒れて parity test が **skip** されるリスク. CI でフォールバック
  検出を assert する.
- LinuxARM (Apple Silicon container) は pyo3 0.24 で SIMD intrinsics 名前空間
  が異なる. cross-compile 時の `std::simd` 利用可否を maturin で確認すること.

## 7. 本セッションでは行わないこと

- 実 Rust 実装. addendum を docs に残し, 次セッションで RUST-FX を進める.
- maturin develop / wheel build (現状 v0.5.0 wheel で 444 PASS のため弄らない).

---

> このファイルは次セッションの開始時に Rust 高速化を着手する際の起点メモ.
> [[goal_release_ready_v0E_rust]] memory との 1-1 対応で運用.
