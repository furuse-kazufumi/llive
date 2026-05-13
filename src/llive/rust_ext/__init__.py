"""Optional Rust acceleration layer (Phase 5 / RUST-01〜04 skeleton).

The Rust extension is built from ``crates/llive_rust_ext`` via maturin and
installed as the top-level ``llive_rust_ext`` Python module. When that
module is unavailable (e.g. the user ``pip install llmesh-llive`` without
``[rust]``), every function in this package falls back to a pure-Python
implementation.

Public API (kept stable across backends):

* ``compute_surprise(new_embedding, memory_embeddings) -> float``
* ``jaccard(a, b) -> float``
* ``bulk_time_decay(edges, ref_time, tau_map) -> list[(src, dst, rel_type, new_weight)]``
* ``HAS_RUST`` boolean flag, ``__backend__`` string ("rust" or "python")

Callers that need a guaranteed Rust backend can ``import llive.rust_ext``
and assert ``llive.rust_ext.HAS_RUST is True``. Parity tests
(``tests/property/test_rust_python_parity.py``) verify both backends
agree to within 1e-6.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

try:
    import llive_rust_ext as _rust  # type: ignore[import-not-found]

    HAS_RUST = True
    __backend__ = "rust"
    __version__ = _rust.__version__
except ImportError:
    _rust = None
    HAS_RUST = False
    __backend__ = "python"
    __version__ = "0.4.0+python_fallback"


def compute_surprise(
    new_embedding: list[float] | Iterable[float],
    memory_embeddings: list[list[float]],
) -> float:
    """Cosine-similarity surprise = ``1 - max_i cosine(new, mem[i])``, clipped to [0,1].

    Returns 1.0 when ``memory_embeddings`` is empty.
    """
    new_list = list(new_embedding)
    if _rust is not None:
        return float(_rust.compute_surprise(new_list, memory_embeddings))
    return _compute_surprise_py(new_list, memory_embeddings)


def jaccard(a: Iterable[int], b: Iterable[int]) -> float:
    """Jaccard similarity of two integer id collections.

    Inputs are deduped+sorted on the Python side before crossing the FFI
    boundary so the Rust kernel can run a linear-time merge.
    """
    a_sorted = sorted(set(int(x) for x in a))
    b_sorted = sorted(set(int(x) for x in b))
    if _rust is not None:
        return float(_rust.jaccard(a_sorted, b_sorted))
    return _jaccard_py(a_sorted, b_sorted)


def bulk_time_decay(
    edges: list[tuple[str, float, float]],
    tau_map: dict[str, float],
) -> list[float]:
    """Apply ``new = w * exp(-age / tau)`` to a batch of (rel_type, weight, age_days).

    Rel types absent from ``tau_map`` are passed through unchanged. Returns
    new weights in the original input order.
    """
    if _rust is not None:
        keys = list(tau_map.keys())
        values = [float(tau_map[k]) for k in keys]
        triples = [(str(r), float(w), float(a)) for (r, w, a) in edges]
        return [float(v) for v in _rust.bulk_time_decay(triples, keys, values)]
    return _bulk_time_decay_py(edges, tau_map)


# -- pure-Python fallbacks ----------------------------------------------------


def _l2_norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _compute_surprise_py(
    new: list[float], memory_embeddings: list[list[float]]
) -> float:
    if not memory_embeddings:
        return 1.0
    dim = len(new)
    # Validate dimensions first so the error surface is independent of
    # vector magnitudes (mirrors the Rust kernel for RUST-13 parity).
    for row in memory_embeddings:
        if len(row) != dim:
            raise ValueError(f"dim mismatch: new={dim}, row={len(row)}")
    new_norm = _l2_norm(new)
    if new_norm == 0.0:
        return 1.0
    max_sim = -1.0
    for row in memory_embeddings:
        row_norm = _l2_norm(row)
        if row_norm == 0.0:
            continue
        dot = sum(a * b for a, b in zip(new, row, strict=True))
        sim = dot / (new_norm * row_norm)
        if sim > max_sim:
            max_sim = sim
    return float(max(0.0, min(1.0, 1.0 - max_sim)))


def _jaccard_py(a: list[int], b: list[int]) -> float:
    if not a and not b:
        return 1.0
    sa, sb = set(a), set(b)
    union_n = len(sa | sb)
    if union_n == 0:
        return 1.0
    return len(sa & sb) / union_n


__all__ = [
    "HAS_RUST",
    "__backend__",
    "__version__",
    "compute_surprise",
    "jaccard",
]
