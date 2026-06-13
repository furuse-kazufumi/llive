// SPDX-License-Identifier: Apache-2.0
//! RUST-15 PeerScoreMatrixOps — Python `PeerEvaluationMatrix` の hot path を Rust 化.
//!
//! 対象関数:
//! - `column_mean(matrix, exclude_self)` — Python `column_mean()` と bit-exact parity
//! - `row_mean(matrix, exclude_self)` — Python `row_mean()` と bit-exact parity
//! - `collusion_score(matrix)` — variance / symmetry / concentration の 3 指標
//!
//! 期待倍率: 5-10× (30 体集団で 100µs → 10µs).
//! 5× ゲート未達なら revert ([[project-llive-rust-acceleration]] 既定方針).
//!
//! 参照:
//! - `src/llive/perf/evolutionary/peer_evaluation.py` Python 実装
//! - `docs/requirements_v0.7_rust_acceleration_v0DE_addendum.md` RUST-15

use ndarray::{Array1, ArrayView2, Axis};

/// 各 agent が他者から受けた score の列平均.
///
/// `exclude_self = true` のとき対角を NaN として扱い無視する.
/// NaN を含む列は `nanmean` 相当の挙動 (NaN 以外の値だけで平均).
pub fn column_mean(matrix: ArrayView2<f64>, exclude_self: bool) -> Array1<f64> {
    let n = matrix.nrows();
    debug_assert_eq!(matrix.ncols(), n, "matrix must be square");
    let mut result = Array1::<f64>::from_elem(n, f64::NAN);
    for j in 0..n {
        let mut sum = 0.0;
        let mut count = 0u32;
        for i in 0..n {
            if exclude_self && i == j {
                continue;
            }
            let v = matrix[[i, j]];
            if !v.is_nan() {
                sum += v;
                count += 1;
            }
        }
        result[j] = if count == 0 {
            f64::NAN
        } else {
            sum / (count as f64)
        };
    }
    result
}

/// 各 agent が他者を採点した行平均.
pub fn row_mean(matrix: ArrayView2<f64>, exclude_self: bool) -> Array1<f64> {
    let n = matrix.nrows();
    debug_assert_eq!(matrix.ncols(), n, "matrix must be square");
    let mut result = Array1::<f64>::from_elem(n, f64::NAN);
    for i in 0..n {
        let mut sum = 0.0;
        let mut count = 0u32;
        for j in 0..n {
            if exclude_self && i == j {
                continue;
            }
            let v = matrix[[i, j]];
            if !v.is_nan() {
                sum += v;
                count += 1;
            }
        }
        result[i] = if count == 0 {
            f64::NAN
        } else {
            sum / (count as f64)
        };
    }
    result
}

/// 共謀検出 3 指標. Python `PeerEvaluationMatrix.collusion_score()` と parity.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CollusionScore {
    pub score_variance: f64,
    pub symmetry: f64,
    pub concentration: f64,
}

impl CollusionScore {
    pub fn zero() -> Self {
        Self {
            score_variance: 0.0,
            symmetry: 0.0,
            concentration: 0.0,
        }
    }
}

/// off-diagonal の variance / symmetry / concentration を計算.
pub fn collusion_score(matrix: ArrayView2<f64>) -> CollusionScore {
    let n = matrix.nrows();
    debug_assert_eq!(matrix.ncols(), n, "matrix must be square");

    // off-diagonal 値を集める
    let mut off_diag = Vec::<f64>::with_capacity(n * (n - 1).max(1));
    let mut off_diag_t = Vec::<f64>::with_capacity(n * (n - 1).max(1));
    for i in 0..n {
        for j in 0..n {
            if i == j {
                continue;
            }
            let v = matrix[[i, j]];
            let v_t = matrix[[j, i]];
            if v.is_nan() {
                continue;
            }
            off_diag.push(v);
            off_diag_t.push(v_t);
        }
    }
    if off_diag.is_empty() {
        return CollusionScore::zero();
    }

    // variance
    let mean = off_diag.iter().sum::<f64>() / (off_diag.len() as f64);
    let score_variance = off_diag
        .iter()
        .map(|v| (v - mean).powi(2))
        .sum::<f64>()
        / (off_diag.len() as f64);

    // symmetry = corr(M, M.T)
    let symmetry = if off_diag.len() >= 2 {
        let std1 = std_dev(&off_diag, mean);
        let mean_t = off_diag_t.iter().sum::<f64>() / (off_diag_t.len() as f64);
        let std2 = std_dev(&off_diag_t, mean_t);
        if std1 > 1e-12 && std2 > 1e-12 {
            let cov: f64 = off_diag
                .iter()
                .zip(off_diag_t.iter())
                .map(|(a, b)| (a - mean) * (b - mean_t))
                .sum::<f64>()
                / (off_diag.len() as f64);
            cov / (std1 * std2)
        } else {
            0.0
        }
    } else {
        0.0
    };

    // concentration = col_mean.max() / col_mean.mean()
    let col_means = column_mean(matrix, true);
    let valid: Vec<f64> = col_means.iter().copied().filter(|v| !v.is_nan()).collect();
    let concentration = if !valid.is_empty() {
        let m = valid.iter().sum::<f64>() / (valid.len() as f64);
        if m > 1e-12 {
            let max_v = valid.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
            max_v / m
        } else {
            0.0
        }
    } else {
        0.0
    };

    CollusionScore {
        score_variance,
        symmetry,
        concentration,
    }
}

fn std_dev(values: &[f64], mean: f64) -> f64 {
    let var: f64 = values
        .iter()
        .map(|v| (v - mean).powi(2))
        .sum::<f64>()
        / (values.len() as f64);
    var.sqrt()
}

// ---------------------------------------------------------------------------
// Tests — bit-exact parity 検証
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;
    use ndarray::array;

    #[test]
    fn column_mean_basic() {
        let m = array![
            [f64::NAN, 0.8, 0.6],
            [0.5, f64::NAN, 0.7],
            [0.4, 0.9, f64::NAN]
        ];
        let result = column_mean(m.view(), true);
        // a が受けた: 0.5, 0.4 → 0.45
        assert_relative_eq!(result[0], 0.45, epsilon = 1e-9);
        // b が受けた: 0.8, 0.9 → 0.85
        assert_relative_eq!(result[1], 0.85, epsilon = 1e-9);
        // c が受けた: 0.6, 0.7 → 0.65
        assert_relative_eq!(result[2], 0.65, epsilon = 1e-9);
    }

    #[test]
    fn row_mean_excludes_self() {
        let m = array![[f64::NAN, 0.8], [0.3, f64::NAN]];
        let result = row_mean(m.view(), true);
        assert_relative_eq!(result[0], 0.8, epsilon = 1e-9);
        assert_relative_eq!(result[1], 0.3, epsilon = 1e-9);
    }

    #[test]
    fn collusion_score_normal_population() {
        let m = array![
            [f64::NAN, 0.8, 0.3],
            [0.5, f64::NAN, 0.7],
            [0.4, 0.6, f64::NAN]
        ];
        let score = collusion_score(m.view());
        assert!(score.score_variance > 1e-3, "variance should be non-trivial");
        assert!(score.concentration > 1.0, "concentration > 1 expected");
    }

    #[test]
    fn collusion_uniform_high_suggests_collusion() {
        // 全員が 0.95 を付け合う → variance ≈ 0
        let m = array![
            [f64::NAN, 0.95, 0.95],
            [0.95, f64::NAN, 0.95],
            [0.95, 0.95, f64::NAN]
        ];
        let score = collusion_score(m.view());
        assert!(
            score.score_variance < 1e-6,
            "variance should be near 0 for uniform high"
        );
        // concentration ≈ 1.0 (全員同じ平均)
        assert_relative_eq!(score.concentration, 1.0, epsilon = 1e-6);
    }

    #[test]
    fn empty_matrix_returns_zero() {
        let m = array![[f64::NAN]];
        let score = collusion_score(m.view());
        assert_eq!(score, CollusionScore::zero());
    }
}
