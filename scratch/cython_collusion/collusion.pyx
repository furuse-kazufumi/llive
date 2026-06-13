# cython: boundscheck=False, wraparound=False, cdivision=True, language_level=3
# SPDX-License-Identifier: Apache-2.0
"""RUST-16 scratch comparison — Cython 版 collusion_score kernel.

Receives a `double[:, :]` memoryview (zero-copy from numpy.ndarray).
Returns (variance, symmetry, concentration) tuple.

Mirrors `PeerEvaluationMatrix.collusion_score()` semantics; NaN-aware.
"""

from libc.math cimport sqrt, isnan


def collusion_score_kernel(double[:, ::1] m):
    cdef Py_ssize_t n = m.shape[0]
    if n < 2 or m.shape[1] != n:
        return (0.0, 0.0, 0.0)

    cdef Py_ssize_t i, j
    cdef Py_ssize_t count = 0
    cdef double v
    cdef double sum_val = 0.0
    cdef double sum_t = 0.0

    # First pass: gather mean / mean_t.
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            v = m[i, j]
            if isnan(v):
                continue
            count += 1
            sum_val += v
            sum_t += m[j, i]
    if count == 0:
        return (0.0, 0.0, 0.0)

    cdef double mean = sum_val / count
    cdef double mean_t = sum_t / count

    # Second pass: variance / cov.
    cdef double v_t
    cdef double var_sum = 0.0
    cdef double var_t_sum = 0.0
    cdef double cov_sum = 0.0
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            v = m[i, j]
            if isnan(v):
                continue
            v_t = m[j, i]
            var_sum += (v - mean) * (v - mean)
            var_t_sum += (v_t - mean_t) * (v_t - mean_t)
            cov_sum += (v - mean) * (v_t - mean_t)
    cdef double variance = var_sum / count
    cdef double std = sqrt(variance)
    cdef double std_t = sqrt(var_t_sum / count)
    cdef double symmetry = 0.0
    if std > 1e-12 and std_t > 1e-12:
        symmetry = (cov_sum / count) / (std * std_t)

    # Column mean (excluding diagonal NaN) → top-1 / overall mean.
    cdef list col_means_list = []
    cdef double col_sum
    cdef Py_ssize_t col_cnt
    for j in range(n):
        col_sum = 0.0
        col_cnt = 0
        for i in range(n):
            if i == j:
                continue
            v = m[i, j]
            if isnan(v):
                continue
            col_sum += v
            col_cnt += 1
        if col_cnt > 0:
            col_means_list.append(col_sum / col_cnt)
    if not col_means_list:
        return (variance, symmetry, 0.0)

    cdef double mean_col = sum(col_means_list) / len(col_means_list)
    cdef double concentration = 0.0
    if mean_col > 1e-12:
        concentration = max(col_means_list) / mean_col

    return (variance, symmetry, concentration)
