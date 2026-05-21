// SPDX-License-Identifier: Apache-2.0
//! llive Rust acceleration layer.
//!
//! Phase 1 (本 skeleton): RUST-15 PeerScoreMatrixOps の純 Rust 実装 + parity test.
//! Phase 2 (次セッション): maturin で Python wheel build + pyo3 binding 配線.
//!
//! 参照: `docs/requirements_v0.7_rust_acceleration_v0DE_addendum.md` RUST-15.

pub mod peer_score;

#[cfg(feature = "python")]
mod py_bindings;

#[cfg(feature = "python")]
pub use py_bindings::*;
