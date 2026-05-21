// SPDX-License-Identifier: Apache-2.0
//! PyO3 binding stub (Phase 2 で maturin build 経由で配線).
//!
//! 本 skeleton は **interface 設計のみ**. maturin build は次セッション着工.

use crate::peer_score::{collusion_score, column_mean, row_mean};
use ndarray::ArrayView2;
use numpy::{IntoPyArray, PyArray1, PyReadonlyArray2};
use pyo3::prelude::*;

/// Python から呼ぶ entry: `llive_rust_ext.column_mean(matrix, exclude_self=True)`
#[pyfunction]
#[pyo3(signature = (matrix, exclude_self=true))]
fn py_column_mean<'py>(
    py: Python<'py>,
    matrix: PyReadonlyArray2<'py, f64>,
    exclude_self: bool,
) -> Bound<'py, PyArray1<f64>> {
    let view = matrix.as_array();
    let result = column_mean(view, exclude_self);
    result.into_pyarray_bound(py)
}

/// Python から呼ぶ entry: `llive_rust_ext.row_mean(matrix, exclude_self=True)`
#[pyfunction]
#[pyo3(signature = (matrix, exclude_self=true))]
fn py_row_mean<'py>(
    py: Python<'py>,
    matrix: PyReadonlyArray2<'py, f64>,
    exclude_self: bool,
) -> Bound<'py, PyArray1<f64>> {
    let view = matrix.as_array();
    let result = row_mean(view, exclude_self);
    result.into_pyarray_bound(py)
}

/// 3-tuple (variance, symmetry, concentration) を返す.
#[pyfunction]
fn py_collusion_score(matrix: PyReadonlyArray2<f64>) -> (f64, f64, f64) {
    let view = matrix.as_array();
    let s = collusion_score(view);
    (s.score_variance, s.symmetry, s.concentration)
}

#[pymodule]
fn llive_rust_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(py_column_mean, m)?)?;
    m.add_function(wrap_pyfunction!(py_row_mean, m)?)?;
    m.add_function(wrap_pyfunction!(py_collusion_score, m)?)?;
    Ok(())
}
