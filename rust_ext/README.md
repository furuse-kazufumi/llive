# llive_rust_ext — Rust 高速化レイヤ skeleton (RUST-15+)

llive の hot path を Rust で実装する optional 拡張. Python 側の純実装と
**bit-exact parity** を保つ.

## Status (2026-05-21)

- **Phase 1 (本 commit)**: 純 Rust 実装 + `cargo test` で parity 検証.
  RUST-15 PeerScoreMatrixOps (column_mean / row_mean / collusion_score) 着地.
- **Phase 2 (次セッション以降)**: maturin で Python wheel build + PyO3
  binding 配線. `[rust]` extra として隔離.
- **Phase 3**: RUST-16 (NoveltySearch_kNN) / RUST-17 (LHS) / RUST-18 (σSA-ES)
  を順次着工.

## Build (Phase 1 — pure Rust テスト)

```bash
cd D:/projects/llive/rust_ext
cargo test --no-default-features
```

## Build (Phase 2 — maturin develop) — 次セッション

```bash
pip install maturin
cd D:/projects/llive/rust_ext
maturin develop --release --features python
# → Python から: from llive_rust_ext import column_mean, row_mean, collusion_score
```

## 5× ゲート

- 全 RUST-XX 実装は **Python 実装と比較して 5× 以上の改善** を求める.
- 未達なら revert ([[project-llive-rust-acceleration]] 既定方針).
- bench harness は RUST-14 (将来) で整備.

## 既存仕様との関係

- `docs/requirements_v0.7_rust_acceleration.md` (既存 RUST-01〜14)
- `docs/requirements_v0.7_rust_acceleration_v0DE_addendum.md` (新規 RUST-15〜20)
- Python 側 reference: `src/llive/perf/evolutionary/peer_evaluation.py`
