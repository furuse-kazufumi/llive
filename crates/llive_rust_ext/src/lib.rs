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

#[pymodule]
fn llive_rust_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", VERSION)?;
    m.add_function(wrap_pyfunction!(compute_surprise, m)?)?;
    m.add_function(wrap_pyfunction!(jaccard, m)?)?;
    m.add_function(wrap_pyfunction!(bulk_time_decay, m)?)?;
    m.add_function(wrap_pyfunction!(persona_dissimilarity, m)?)?;
    m.add_function(wrap_pyfunction!(persona_dissimilarity_pairwise, m)?)?;
    Ok(())
}
