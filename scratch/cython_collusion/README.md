# Cython scratch comparison (RUST-16 collusion_score) — honest disclosure

> 2026-05-22 marathon. ユーザー提案「RUST-16 collusion_score の scratch 比較
> やってみる」(memory [[project_cython_vs_pyo3_decision]] を執行).

## 目的

llive 高速化レイヤで Cython vs Rust (pyo3) のどちらが numpy heavy hot path
で勝つかを **scratch (本体に統合せず)** で実測比較する.

## 結果 (2026-05-22)

| 経路 | 状態 | bench 5x gate |
|---|---|---|
| Python (numpy, 既存 `PeerEvaluationMatrix.collusion_score`) | baseline | — |
| **Rust (pyo3 + numpy zero-copy)** | ✅ 着地, 31 parity test PASS (1e-6) | **平均 x66.70** (N=8 で x115.04 / N=64 で x18.22) |
| **Cython (memoryview + native ループ)** | ❌ **build chain 不在で着地できず** | — |

## Cython 失敗の honest disclosure

Cython は本来同等の native ループ kernel が書けるはずだが, Windows 環境で
build が不可能だった:

1. **MSVC build tools 不在** — `cl.exe` 無し. Visual Studio Installer の
   "Build Tools for C++" は別途数 GB のインストールが必要.
2. **mingw fallback も失敗** — `/c/msys64/ucrt64/bin/gcc` で
   `--compiler=mingw32` を指定したが MSVC でビルドされた Python の
   `void*` size check で型衝突, gcc がエラーで停止.
3. **WSL / Linux 経路は本セッションでは未試行** (環境変更が大きい).

結果として **Cython kernel は scratch 比較から脱落**. これは言語選択の
重要要因の 1 つを示す事例:

> 「数値計算が同等に書ける」だけでは採用には足りず, **build chain が
> 確立できる必要がある**.

llive はすでに `crates/llive_rust_ext` (pyo3 + maturin + Windows / Linux /
macOS CI) を確立しているため, Rust 化は **build chain コスト 0** で
追加できる. Cython は MSVC build tools / CI runner 設定を別途整える
コスト発生.

## Cython source は残す

`collusion.pyx` / `setup.py` は **build できない環境でも source として残す**.
将来 Linux/WSL / MSVC build tools が整った環境で再試行する起点として有用.

## 関連

- [[feedback_rust_usage_matters]] — Rust 化判断のチェックリスト
- [[project_cython_vs_pyo3_decision]] — 使い分け判断軸
- [[feedback_benchmark_honest_disclosure]] — 異常結果の内訳を疑う
- `scripts/bench_collusion_score_5x_gate.py` — 2 way 比較 bench (Python vs Rust)
- `src/llive/rust_ext/__init__.py:collusion_score_kernel` — Rust wrapper
- `crates/llive_rust_ext/src/lib.rs:collusion_score_kernel` — Rust kernel
