//! llive_rust_ext (RUST-01 skeleton)
//!
//! Optional PyO3 extension module. The Python side (`llive.rust_ext`) imports
//! this module when available and falls back to pure-Python implementations
//! when it isn't.
//!
//! Phase 5 contents:
//! * `__version__`         — extension build version (RUST-01)
//! * `compute_surprise`    — cosine-similarity-based surprise kernel (RUST-02 baseline)
//! * `jaccard`             — set-of-ids Jaccard similarity (RUST-04)
//!
//! These are correctness-only baselines; rayon / ndarray-linalg parallelism
//! will land in v0.5.0 after the parity harness validates the pure Rust path.

use numpy::PyReadonlyArray2;
use pyo3::prelude::*;
use pyo3::types::PyList;
use rayon::prelude::*;

const VERSION: &str = "0.5.0";

/// Cosine-similarity surprise: `1 - max_i cosine(new, mem[i])`, clipped to `[0, 1]`.
///
/// Inputs are flat `f32` lists. `new_embedding` length must match each row of
/// `memory_embeddings`. Returns `1.0` when `memory_embeddings` is empty.
#[pyfunction]
fn compute_surprise(
    py: Python<'_>,
    new_embedding: &Bound<'_, PyList>,
    memory_embeddings: Vec<Vec<f32>>,
) -> PyResult<f32> {
    let new: Vec<f32> = new_embedding.extract()?;
    py.allow_threads(|| {
        if memory_embeddings.is_empty() {
            return Ok(1.0_f32);
        }
        let dim = new.len();
        // Dim mismatches are validated *before* numerics so the error surface
        // matches the pure-Python fallback regardless of vector magnitudes.
        for row in &memory_embeddings {
            if row.len() != dim {
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "dim mismatch: new={dim}, row={}",
                    row.len()
                )));
            }
        }
        let new_norm = l2_norm(&new);
        if new_norm == 0.0 {
            return Ok(1.0_f32);
        }
        let mut max_sim: f32 = -1.0;
        for row in &memory_embeddings {
            let row_norm = l2_norm(row);
            if row_norm == 0.0 {
                continue;
            }
            let mut dot = 0.0_f32;
            for i in 0..dim {
                dot += new[i] * row[i];
            }
            let sim = dot / (new_norm * row_norm);
            if sim > max_sim {
                max_sim = sim;
            }
        }
        let surprise = (1.0_f32 - max_sim).clamp(0.0, 1.0);
        Ok(surprise)
    })
}

fn l2_norm(v: &[f32]) -> f32 {
    v.iter().map(|x| x * x).sum::<f32>().sqrt()
}

/// Jaccard similarity of two `u32` id sets. Sets must be sorted+deduped; the
/// caller is responsible (Python side enforces this in `llive.rust_ext`).
#[pyfunction]
fn jaccard(a: Vec<u32>, b: Vec<u32>) -> f32 {
    if a.is_empty() && b.is_empty() {
        return 1.0;
    }
    let mut i = 0usize;
    let mut j = 0usize;
    let mut inter: u32 = 0;
    while i < a.len() && j < b.len() {
        match a[i].cmp(&b[j]) {
            std::cmp::Ordering::Less => i += 1,
            std::cmp::Ordering::Greater => j += 1,
            std::cmp::Ordering::Equal => {
                inter += 1;
                i += 1;
                j += 1;
            }
        }
    }
    let union = a.len() as u32 + b.len() as u32 - inter;
    if union == 0 {
        return 1.0;
    }
    inter as f32 / union as f32
}

/// Edge-weight time decay (RUST-03 baseline).
///
/// Inputs:
///   * `edges`: list of `(rel_type, weight, age_days)` triples.
///   * `tau_map_keys` / `tau_map_values`: parallel arrays mapping rel_type → tau_days.
///     Rel types absent from the map are returned unchanged (weight passes through).
///
/// Output: list of new weights, one per input edge, in the original order.
/// Decay formula: `new_weight = weight * exp(-age_days / tau)` when tau > 0.
#[pyfunction]
fn bulk_time_decay(
    py: Python<'_>,
    edges: Vec<(String, f64, f64)>,
    tau_map_keys: Vec<String>,
    tau_map_values: Vec<f64>,
) -> PyResult<Vec<f64>> {
    if tau_map_keys.len() != tau_map_values.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "tau_map_keys / tau_map_values length mismatch",
        ));
    }
    let mut tau_lookup: std::collections::HashMap<String, f64> =
        std::collections::HashMap::with_capacity(tau_map_keys.len());
    for (k, v) in tau_map_keys.into_iter().zip(tau_map_values.into_iter()) {
        tau_lookup.insert(k, v);
    }
    py.allow_threads(|| {
        let out: Vec<f64> = edges
            .into_iter()
            .map(|(rel, weight, age_days)| {
                let tau = tau_lookup.get(&rel).copied().unwrap_or(0.0);
                if tau <= 0.0 {
                    weight
                } else {
                    let factor = (-age_days / tau).exp();
                    weight * factor
                }
            })
            .collect();
        Ok(out)
    })
}

/// Persona dissimilarity (RUST-15 baseline) — Jaccard + L2 + 合成を 1 FFI call.
///
/// `(1 - Jaccard(a_ids, b_ids)) * 0.5 + min(1, L2(a_aff - b_aff) / sqrt(N)) * 0.5`.
///
/// Inputs:
///   * `a_ids` / `b_ids`: **sorted, deduped** u32 sets. caller (Python side) is
///     responsible for the canonical form.
///   * `a_aff` / `b_aff`: 同じ次元 N の f64 affinity vector ([0, 1] 推奨).
///
/// Output: dissimilarity in `[0, 1]`. Mirrors Python `persona_dissimilarity`
/// (`src/llive/perf/evolutionary/persona.py:425`) to within 1e-6 (RUST-13 style
/// parity gate).
#[pyfunction]
fn persona_dissimilarity(
    a_ids: Vec<u32>,
    b_ids: Vec<u32>,
    a_aff: Vec<f64>,
    b_aff: Vec<f64>,
) -> PyResult<f64> {
    if a_aff.len() != b_aff.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "affinity dim mismatch: a={}, b={}",
            a_aff.len(),
            b_aff.len()
        )));
    }
    if a_aff.is_empty() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "affinity vector must be non-empty",
        ));
    }
    // Jaccard via linear merge (a_ids / b_ids are caller-canonical).
    let mut i = 0usize;
    let mut j = 0usize;
    let mut inter: u32 = 0;
    while i < a_ids.len() && j < b_ids.len() {
        match a_ids[i].cmp(&b_ids[j]) {
            std::cmp::Ordering::Less => i += 1,
            std::cmp::Ordering::Greater => j += 1,
            std::cmp::Ordering::Equal => {
                inter += 1;
                i += 1;
                j += 1;
            }
        }
    }
    let union = a_ids.len() as u32 + b_ids.len() as u32 - inter;
    let jaccard = if union == 0 {
        // Python 側 persona_dissimilarity と一致させる: 両 set 空のとき 0.0.
        return Ok(0.0);
    } else {
        inter as f64 / union as f64
    };
    // L2 of affinity diff
    let mut sum_sq = 0.0_f64;
    for k in 0..a_aff.len() {
        let d = a_aff[k] - b_aff[k];
        sum_sq += d * d;
    }
    let l2 = sum_sq.sqrt();
    let n = a_aff.len() as f64;
    let l2_norm = (l2 / n.sqrt()).min(1.0);
    Ok(0.5 * (1.0 - jaccard) + 0.5 * l2_norm)
}

/// Internal pairwise core, no PyResult overhead.
fn _dissim_pair(a_ids: &[u32], b_ids: &[u32], a_aff: &[f64], b_aff: &[f64]) -> f64 {
    let mut i = 0usize;
    let mut j = 0usize;
    let mut inter: u32 = 0;
    while i < a_ids.len() && j < b_ids.len() {
        match a_ids[i].cmp(&b_ids[j]) {
            std::cmp::Ordering::Less => i += 1,
            std::cmp::Ordering::Greater => j += 1,
            std::cmp::Ordering::Equal => {
                inter += 1;
                i += 1;
                j += 1;
            }
        }
    }
    let union = a_ids.len() as u32 + b_ids.len() as u32 - inter;
    if union == 0 {
        return 0.0;
    }
    let jaccard = inter as f64 / union as f64;
    let mut sum_sq = 0.0_f64;
    for k in 0..a_aff.len() {
        let d = a_aff[k] - b_aff[k];
        sum_sq += d * d;
    }
    let l2 = sum_sq.sqrt();
    let n = a_aff.len() as f64;
    let l2_norm = (l2 / n.sqrt()).min(1.0);
    0.5 * (1.0 - jaccard) + 0.5 * l2_norm
}

/// Pairwise persona_dissimilarity matrix (RUST-15 batch).
///
/// Inputs:
///   * `ids_list`: N entries of **sorted, deduped** u32 sets.
///   * `aff_matrix`: N entries of equal-dim f64 affinity vector.
///
/// Output: flattened upper-triangular (i < j) NxN dissimilarities in
/// row-major (i, j) order, length = N*(N-1)/2. Python wrapper rebuilds the
/// symmetric NxN matrix.
#[pyfunction]
fn persona_dissimilarity_pairwise(
    ids_list: Vec<Vec<u32>>,
    aff_matrix: Vec<Vec<f64>>,
) -> PyResult<Vec<f64>> {
    let n = ids_list.len();
    if aff_matrix.len() != n {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "len mismatch: ids_list={}, aff_matrix={}",
            n,
            aff_matrix.len()
        )));
    }
    if n == 0 {
        return Ok(Vec::new());
    }
    let dim = aff_matrix[0].len();
    if dim == 0 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "affinity vector must be non-empty",
        ));
    }
    for row in &aff_matrix {
        if row.len() != dim {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "affinity dim mismatch: expected {}, got {}",
                dim,
                row.len()
            )));
        }
    }
    let mut out: Vec<f64> = Vec::with_capacity(n * (n.saturating_sub(1)) / 2);
    for i in 0..n {
        for j in (i + 1)..n {
            out.push(_dissim_pair(&ids_list[i], &ids_list[j], &aff_matrix[i], &aff_matrix[j]));
        }
    }
    Ok(out)
}

/// RUST-16 collusion_score kernel — numpy zero-copy NxN matrix → (variance, symmetry, concentration).
///
/// Mirrors `PeerEvaluationMatrix.collusion_score()` numerically (1e-6 parity).
/// Receives the raw NxN matrix as a numpy `PyReadonlyArray2<f64>` (zero-copy).
/// Returns `(score_variance, symmetry, concentration)` tuple.
///
/// NaN-aware: off-diagonal NaN entries are excluded (mirrors Python's
/// `np.fill_diagonal(m, np.nan)` semantics by skipping NaN cells).
#[pyfunction]
fn collusion_score_kernel(matrix: PyReadonlyArray2<f64>) -> PyResult<(f64, f64, f64)> {
    let m = matrix.as_array();
    let shape = m.shape();
    if shape.len() != 2 || shape[0] != shape[1] {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "matrix must be square NxN",
        ));
    }
    let n = shape[0];
    if n < 2 {
        return Ok((0.0, 0.0, 0.0));
    }

    // First pass: gather mean / mean_t over valid off-diagonal cells.
    let mut count: usize = 0;
    let mut sum_val: f64 = 0.0;
    let mut sum_t: f64 = 0.0;
    for i in 0..n {
        for j in 0..n {
            if i == j {
                continue;
            }
            let v = m[[i, j]];
            if v.is_nan() {
                continue;
            }
            count += 1;
            sum_val += v;
            sum_t += m[[j, i]];
        }
    }
    if count == 0 {
        return Ok((0.0, 0.0, 0.0));
    }
    let mean = sum_val / count as f64;
    let mean_t = sum_t / count as f64;

    // Second pass: variance / std / std_t / covariance.
    let mut var_sum: f64 = 0.0;
    let mut var_t_sum: f64 = 0.0;
    let mut cov_sum: f64 = 0.0;
    for i in 0..n {
        for j in 0..n {
            if i == j {
                continue;
            }
            let v = m[[i, j]];
            if v.is_nan() {
                continue;
            }
            let v_t = m[[j, i]];
            var_sum += (v - mean).powi(2);
            var_t_sum += (v_t - mean_t).powi(2);
            cov_sum += (v - mean) * (v_t - mean_t);
        }
    }
    let variance = var_sum / count as f64;
    let std = variance.sqrt();
    let std_t = (var_t_sum / count as f64).sqrt();
    let symmetry = if std > 1e-12 && std_t > 1e-12 {
        (cov_sum / count as f64) / (std * std_t)
    } else {
        0.0
    };

    // Column mean (excluding diagonal NaN); then top-1 / overall mean.
    let mut col_means: Vec<f64> = Vec::with_capacity(n);
    for j in 0..n {
        let mut col_sum = 0.0;
        let mut col_cnt: usize = 0;
        for i in 0..n {
            if i == j {
                continue;
            }
            let v = m[[i, j]];
            if v.is_nan() {
                continue;
            }
            col_sum += v;
            col_cnt += 1;
        }
        if col_cnt > 0 {
            col_means.push(col_sum / col_cnt as f64);
        }
    }
    let concentration = if col_means.is_empty() {
        0.0
    } else {
        let mean_col: f64 = col_means.iter().sum::<f64>() / col_means.len() as f64;
        if mean_col > 1e-12 {
            col_means.iter().cloned().fold(f64::MIN, f64::max) / mean_col
        } else {
            0.0
        }
    };

    Ok((variance, symmetry, concentration))
}

/// RUST-17 novelty_score_batch — k-NN L2 mean for each query vs archive.
///
/// Inputs (numpy zero-copy):
///   * `values`: shape (N, D). N query vectors.
///   * `archive`: shape (A, D). A archive vectors. May be empty.
///   * `k`: top-k for the mean (clamped to A when k > A).
///
/// Output: Vec<f64> length N. Each entry = mean of the k smallest L2 distances
/// from values[i] to archive entries. When archive is empty, returns 1.0 per row
/// (mirrors Python ``NoveltyScorer.novelty`` semantics).
#[pyfunction]
fn novelty_score_batch(
    values: PyReadonlyArray2<f64>,
    archive: PyReadonlyArray2<f64>,
    k: usize,
) -> PyResult<Vec<f64>> {
    let v = values.as_array();
    let a = archive.as_array();
    if k < 1 {
        return Err(pyo3::exceptions::PyValueError::new_err("k must be >= 1"));
    }
    let v_shape = v.shape();
    let a_shape = a.shape();
    let n = v_shape[0];
    let dim = v_shape[1];
    let a_n = a_shape[0];
    if a_n == 0 {
        // archive empty → all novelty 1.0 (mirror Python convention).
        return Ok(vec![1.0; n]);
    }
    if a_shape[1] != dim {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "dim mismatch: values dim={}, archive dim={}",
            dim, a_shape[1]
        )));
    }
    let mut out = vec![0.0_f64; n];
    let mut dists_buf = vec![0.0_f64; a_n];
    let k_use = k.min(a_n);
    for i in 0..n {
        for j in 0..a_n {
            let mut sum_sq = 0.0_f64;
            for d in 0..dim {
                let diff = v[[i, d]] - a[[j, d]];
                sum_sq += diff * diff;
            }
            dists_buf[j] = sum_sq.sqrt();
        }
        dists_buf
            .sort_by(|x, y| x.partial_cmp(y).unwrap_or(std::cmp::Ordering::Equal));
        let mean: f64 = dists_buf[..k_use].iter().sum::<f64>() / k_use as f64;
        out[i] = mean;
    }
    Ok(out)
}

#[pymodule]
fn llive_rust_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", VERSION)?;
    m.add_function(wrap_pyfunction!(compute_surprise, m)?)?;
    m.add_function(wrap_pyfunction!(jaccard, m)?)?;
    m.add_function(wrap_pyfunction!(bulk_time_decay, m)?)?;
    m.add_function(wrap_pyfunction!(persona_dissimilarity, m)?)?;
    m.add_function(wrap_pyfunction!(persona_dissimilarity_pairwise, m)?)?;
    m.add_function(wrap_pyfunction!(collusion_score_kernel, m)?)?;
    m.add_function(wrap_pyfunction!(novelty_score_batch, m)?)?;
    Ok(())
}
