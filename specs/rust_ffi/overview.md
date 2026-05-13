# Rust FFI Overview (Phase 5 / RUST-01)

This document captures the **Python ⇄ Rust contract** for the optional
acceleration layer (`llive.rust_ext`). It is the source of truth for both
the Rust crate (`crates/llive_rust_ext/`) and the Python wrapper
(`src/llive/rust_ext/__init__.py`).

## Scope

v0.4.0 ships **only the skeleton**:

* PyO3 module skeleton (RUST-01)
* `compute_surprise(new_embedding, memory_embeddings) -> float` baseline (RUST-02)
* `jaccard(a, b) -> float` set-of-ids similarity (RUST-04)
* `__version__` introspection + `HAS_RUST` Python flag
* Parity harness (RUST-13) — both backends agree to within 1e-6

Hot-spot migration (rayon parallelism, edge weight bulk decay, jsonschema-rs,
audit sink, Z3 bridge, tokio async) is deferred per
`docs/requirements_v0.7_rust_acceleration.md`.

## ABI contract

### Crossings

| Direction | Type (Rust) | Type (Python) | Note |
|---|---|---|---|
| Py → Rust | `Vec<f32>` | `list[float]` | Caller flattens; dimensions stated in docstring. |
| Py → Rust | `Vec<u32>` | `list[int]` | Caller dedupes + sorts before the call so Rust can run linear-time merges. |
| Rust → Py | `f32` | `float` | Implicit widening to Python `float`. |
| Rust → Py | `PyErr` | exception | `PyValueError` for size mismatch. |

### GIL handling

Pure-numeric kernels (`compute_surprise`, future RUST-03) must call
`py.allow_threads(|| {...})` around the computation so concurrent Python
threads can keep running. Functions that touch Python objects (extract
lists, build Python results) must do so before/after the allow_threads
block, never inside.

### Determinism

Same input → same output, bit-exact across builds (no FP randomness, no
rayon-induced reduction order changes in v0.4.0 — those land in v0.5.0
behind a `parallel=True` flag if needed).

## Build / install

Until v0.5.0 lands a proper maturin pyproject, the Rust extension is built
out-of-band:

```bash
pip install maturin
maturin develop --release --manifest-path crates/llive_rust_ext/Cargo.toml
```

After `maturin develop`, `python -c "import llive.rust_ext; print(llive.rust_ext.HAS_RUST)"`
should print `True`.

Without the Rust extension, the Python fallback runs identically (just slower).
This is enforced by parity tests in `tests/property/test_rust_python_parity.py`.

## Versioning

* The Rust crate version (in `Cargo.toml`) tracks the parent project's PyPI
  version. For v0.4.0 / Phase 5 skeleton, `llive_rust_ext = "0.4.0"`.
* When ABI changes (new args, removed functions, semantics drift), bump the
  *minor* version and add a parity test that fixes the old behaviour.
* Patch bumps (`0.4.x`) are reserved for pure-perf changes that preserve
  the parity contract.

## Future hotspot list (forward reference)

See `docs/requirements_v0.7_rust_acceleration.md` for the full plan. The
v0.5.0+ hotspots to migrate in order:

1. **RUST-03**: edge weight bulk decay (rayon parallel exp decay over Kùzu rows)
2. **RUST-05**: jsonschema-rs validator drop-in
3. **RUST-06**: crossbeam-channel audit sink (replace Python JSONL writer)
4. **RUST-10**: TRIZ matrix phf static lookup
5. **RUST-07**: ChangeOp engine + proptest parity
6. **RUST-11**: Z3 bridge (Phase 6, Static Verifier)
7. **RUST-08**: hora/arroy HNSW (Faiss-CPU drop-in)
8. **RUST-09**: tokio async pipeline executor (Phase 7)
