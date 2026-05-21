# SPDX-License-Identifier: Apache-2.0
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
import zlib
from collections.abc import Iterable, Sequence

try:
    import llive_rust_ext as _rust  # type: ignore[import-not-found]

    HAS_RUST = True
    __backend__ = "rust"
    __version__ = _rust.__version__
except ImportError:
    _rust = None
    HAS_RUST = False
    __backend__ = "python"
    __version__ = "0.5.0+python_fallback"


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


def persona_dissimilarity(
    a_ids: Sequence[str],
    b_ids: Sequence[str],
    a_affinity: Sequence[float],
    b_affinity: Sequence[float],
) -> float:
    """``(1 - Jaccard(a, b)) * 0.5 + min(1, L2(diff)/sqrt(N)) * 0.5``.

    RUST-15 baseline. Mirrors
    ``llive.perf.evolutionary.persona.persona_dissimilarity`` (numpy 経路) と
    数値的に等価 (1e-6 parity gate, ``tests/property/test_rust_python_parity.py``).

    Persona id は ``zlib.crc32`` で stable な u32 にマップしてから Rust に
    渡す. 衝突確率は数万件 id 同士で 1% 未満 (PERSONA_ONTOLOGY <= 数百件で
    実用上ゼロ).
    """
    a_aff_list = [float(x) for x in a_affinity]
    b_aff_list = [float(x) for x in b_affinity]
    if len(a_aff_list) != len(b_aff_list):
        raise ValueError(
            f"affinity dim mismatch: a={len(a_aff_list)}, b={len(b_aff_list)}"
        )
    if not a_aff_list:
        raise ValueError("affinity vector must be non-empty")

    a_sorted = sorted({_persona_id_to_u32(s) for s in a_ids})
    b_sorted = sorted({_persona_id_to_u32(s) for s in b_ids})
    if _rust is not None and hasattr(_rust, "persona_dissimilarity"):
        return float(
            _rust.persona_dissimilarity(a_sorted, b_sorted, a_aff_list, b_aff_list)
        )
    return _persona_dissimilarity_py(a_sorted, b_sorted, a_aff_list, b_aff_list)


def _persona_id_to_u32(persona_id: str) -> int:
    """Stable u32 hash. Caller responsibility: 同じ string → 同じ u32."""
    return zlib.crc32(str(persona_id).encode("utf-8")) & 0xFFFFFFFF


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


def _persona_dissimilarity_py(
    a_ids: list[int], b_ids: list[int], a_aff: list[float], b_aff: list[float]
) -> float:
    """Pure-Python fallback. Mirrors persona.py:persona_dissimilarity numerically."""
    sa = set(a_ids)
    sb = set(b_ids)
    union = sa | sb
    if not union:
        return 0.0
    jaccard = len(sa & sb) / len(union)
    sum_sq = sum((a - b) ** 2 for a, b in zip(a_aff, b_aff, strict=True))
    l2 = math.sqrt(sum_sq)
    n = len(a_aff)
    l2_norm = min(1.0, l2 / math.sqrt(n))
    return 0.5 * (1.0 - jaccard) + 0.5 * l2_norm


def _jaccard_py(a: list[int], b: list[int]) -> float:
    if not a and not b:
        return 1.0
    sa, sb = set(a), set(b)
    union_n = len(sa | sb)
    if union_n == 0:
        return 1.0
    return len(sa & sb) / union_n


def _bulk_time_decay_py(
    edges: list[tuple[str, float, float]],
    tau_map: dict[str, float],
) -> list[float]:
    out: list[float] = []
    for rel, weight, age_days in edges:
        tau = float(tau_map.get(rel, 0.0))
        if tau <= 0.0:
            out.append(float(weight))
        else:
            out.append(float(weight) * math.exp(-float(age_days) / tau))
    return out


__all__ = [
    "HAS_RUST",
    "__backend__",
    "__version__",
    "bulk_time_decay",
    "compute_surprise",
    "jaccard",
]
