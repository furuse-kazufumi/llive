# 2026-05-22 kernel 実装方法比較 — Python numpy vs Rust pyo3 vs Cython

> ユーザー指示 (2026-05-22): 「同じ機能実装でも実装方法の違いで差が出てくる。
> このあたりの比較は開発過程で重要なので、時々検証して技術資料に残しましょう。
> 部分的に実装方法を変えるのであれば、PyBind11 とかも入れて、C/C++ 実装も
> 比較してみたい」
> 
> [[feedback_impl_method_diff_documentation]] に従い, kernel 実装方法の
> 比較を技術資料として時系列で蓄積する. 本ファイルは初回 (2026-05-22) の
> sweep.

## 1. 比較対象 kernel と目的

llive v0.7 Rust 高速化の RUST-15 / 16 / 17 を着地させる中で, **同じ機能でも
実装方法で結果が大きく変わる** ことが繰り返し観察された. これを 1 記事に
集約し, 言語選択 / batch 設計 / FFI 境界の引き方の判断軸を明文化する.

| Kernel | 機能 | hot path | Python 経路 |
|---|---|---|---|
| **RUST-15** persona_dissimilarity | 2 個 persona 組合せの dissimilarity (Jaccard + L2) | EvolutionLoop の PersonaOverlapPenalty.apply (NxN) | `persona.py:persona_dissimilarity` (numpy + set) |
| **RUST-16** collusion_score | NxN peer matrix の variance / symmetry / concentration | governance.evaluate_generation | `PeerEvaluationMatrix.collusion_score` (np.nanvar / np.corrcoef / np.nanmean) |
| **RUST-17** novelty_score_batch | 集団 N × archive A の L2 + top-k mean | NoveltyScorer.novelty_batch | `NoveltyScorer.novelty` x N (numpy vectorized) |

## 2. 比較経路

| 経路 | 状態 (2026-05-22) | 備考 |
|---|---|---|
| **Python (numpy)** | 全 kernel baseline 確立 | 既存実装. `np.linalg.norm` / `np.nanvar` 等 BLAS 系 |
| **Rust (pyo3 0.24 + numpy zero-copy)** | RUST-15/16/17 全着地 (parity 37 PASS, 1e-6 tolerance) | maturin develop で Windows wheel 動作確認済 |
| **Cython (memoryview)** | **scratch 比較 build chain 不在で脱落** | Windows MSVC build tools 不在 + mingw が MSVC Python と incompatible. source は `scratch/cython_collusion/` に保存 |
| **PyBind11 (C++)** | **未着手 (queue 投入済)** | 次セッション以降 |
| **C/C++ ctypes** | **未着手 (queue 投入済)** | 次セッション以降 |
| **Numba (JIT)** | 未検討 | 比較候補として保留 |

## 3. 結果 (2026-05-22)

### 3.1 RUST-15 persona_dissimilarity

| 戦略 | speedup vs Python | gate | 備考 |
|---|---|---|---|
| 単発 1-pair (string id → u32 hash → Rust 1 call) | **x0.80 (FAIL)** | ❌ | FFI overhead で Python に負ける |
| **batch (N×N pair を 1 FFI に詰める)** | **x12.71 平均 (N=64 で x17.07)** | ✅ | hot path 用途で着地 |

### 3.2 RUST-16 collusion_score

| 戦略 | speedup vs Python | gate | 備考 |
|---|---|---|---|
| **単発 (numpy ndarray zero-copy)** | **x66.70 平均 (N=8 で x115.04)** | ✅ | numpy 小 N の API overhead が主因. 単発でも余裕 |

### 3.3 RUST-17 novelty_score_batch

| archive size | Python (numpy) | Rust pyo3 | speedup | gate |
|---:|---:|---:|---:|:---:|
| A=50 | 872.11us | 91.33us | **x9.55** | PASS |
| A=200 | 1450.01us | 385.58us | **x3.76** | **FAIL** |
| A=1000 | 3914.71us | 2277.47us | **x1.72** | **FAIL** |
| **平均** | — | — | **x5.01** | 辛うじて PASS |

## 4. 4 パターン判定表 (本セッションで言語化)

| Python 経路の特性 | Rust 化の単発 ROI | 例 |
|---|---|---|
| **(A)** 純 Python ループ (numpy 不使用) の 1-pair 計算 | 単発 FAIL, batch 必須 | RUST-15 (string id → u32 hash の 1-pair) |
| **(B)** numpy 大 array (>1000 要素) の vectorized op | 伸びない (numpy 内部既に C/BLAS) | — (該当 kernel まだ無し) |
| **(C)** numpy 小 NxN (< 100) の API 多用 | **単発でも 10-100x** | RUST-16 (np.nanvar / np.corrcoef / np.nanmean を 3 つ重ねがけ) |
| **(D)** numpy 中規模 batch (BLAS 1 関数で完結) | **境界線上**: 小サイズ Rust 圧勝, 大サイズで numpy 追いつく | RUST-17 (A=50 で x9.55, A=1000 で x1.72) |
| **(E)** Python ↔ Rust 境界が冷たいデータ (zero-copy 不可) | overhead 大, batch 必須 | (例: dict / 文字列大量 |

## 5. 教訓 (2026-05-22 marathon)

1. **「Rust 化 = 速い」は嘘**. **使い方** (FFI 境界 / batch / zero-copy / 並列度)
   で結果が桁違い. ([[feedback_rust_usage_matters]])
2. **「numpy = 速い」も嘘**. 小 NxN の API 多用は Python overhead 支配で
   Rust に 60-100x 負ける. (RUST-16 で実証)
3. **境界線**: 中規模 BLAS vectorized 1 関数では Rust naive 二重ループは
   負ける可能性あり. rayon / SIMD / partial sort で挽回が必要.
4. **build chain が確立できるか** は言語選択の重要要因. Cython は理論的に
   等価でも MSVC build tools 不在で本セッションでは脱落.
5. **honest disclosure は架構上の必須**. 「異常に良い結果」は内訳を疑う
   ([[feedback_benchmark_honest_disclosure]]). 単発 0.80x → batch 12.71x や
   archive 小で x9.55 → 大で x1.72 のような **対比** が判断の鍵.

## 6. 今後の計画

### 6.1 短期 (1-2 セッション)

- **RUST-17b**: rayon 並列 + std::simd + partial sort (quickselect) で
  archive 大 (A=200/1000) でも 5x gate clear するか測定.
- **PyBind11 + C/C++** 経路の scratch 比較: RUST-15/16/17 の 3 kernel を
  PyBind11 で実装し speedup / wheel size / build time / Windows CI 整合を
  測定. 結果は次回 `docs/perf_comparison/<日付>_*.md` として追加.

### 6.2 中期 (月次)

- 月次で本記事を更新し, 各 kernel の最新 speedup を re-measure (env drift /
  numpy minor version up / Rust nightly 等で結果が動くため).
- 新規 kernel 追加時は必ず本表の 4 パターン (A/B/C/D/E) のどれに属するかを
  分類してから着手.

### 6.3 長期

- raptor RAD コーパス (HPC / SIMD / GPU 領域) から実装手法の knowledge を
  反映. cross-domain ideation でアプローチを拡張.
- 4 パターン判定表を **AI codex** 化して llive 自身が呼べる形 (RUST-FX
  decision DSL) に. PoC は v0.8 以降.

## 7. References

- pyo3 0.24 docs (numpy zero-copy)
- numpy BLAS internals (linalg.norm dispatching)
- Cython memoryview (zero-copy semantics)
- PyBind11 (eigen / numpy integration)
- ctypes (raw C ABI)
- partial sort algorithms (Hoare quickselect O(N))

---

> **次回更新**: 次セッション以降, PyBind11 + C/C++ 比較結果を `docs/perf_comparison/<日付>_*.md` として追記.
> 本記事はその時系列の初回 (baseline).
