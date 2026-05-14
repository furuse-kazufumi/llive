# llive Phase 5+ 残 RUST-* 設計メモ (draft)

> 2026-05-15 自律走行セッションで起こした設計たたき台。
> 実装はせず、各 RUST-* 項目について **「何を Rust に置く」「どう Python と境界を切る」「parity 検証どうするか」** だけを揃える。
>
> 大原則: `[[project_llive_rust_acceleration]]` の方針通り、
> 1. **意味論先行** ― Python 側の挙動が確定してから Rust に逃す
> 2. **5× ゲート** ― ベンチで 5× 出ない移植は採用しない
> 3. **`[rust]` extra で隔離** ― Rust 失敗時は numpy/pure-python fallback

---

## 共通アーキテクチャ

```
┌──────────────────────────────────────────────────────────────┐
│                Python API (frozen, semver)                    │
│   compute_surprise / bulk_time_decay / jaccard / ...          │
└──────────────────────────────────────────────────────────────┘
                  │                                   │
                  │ if rust_ext.HAS_RUST              │ else
                  ▼                                   ▼
   ┌──────────────────────────────┐    ┌──────────────────────────┐
   │   Rust kernel (PyO3 0.24.2)  │    │  numpy / pure-python     │
   │   crates/llive_rust_ext/     │    │  fallback                │
   └──────────────────────────────┘    └──────────────────────────┘
                  ▲                                   ▲
                  └────────── parity harness ─────────┘
                       (RUST-13, 1e-6 tolerance)
```

---

## RUST-02: 完全並列化 (rayon)

**現状 (v0.5.0):** `compute_surprise` が cosine 類似度を **逐次** で計算。
**目標:** rayon で複数 memory_embeddings 行を並列に dot 計算。

### 設計案

```rust
use rayon::prelude::*;

let max_sim = memory_embeddings
    .par_iter()
    .filter_map(|row| {
        let row_norm = l2_norm(row);
        if row_norm == 0.0 { return None; }
        let mut dot = 0.0_f32;
        for i in 0..dim { dot += new[i] * row[i]; }
        Some(dot / (new_norm * row_norm))
    })
    .reduce(|| -1.0_f32, f32::max);
```

### parity 注意

- `f32::max(NaN, x)` の挙動が逐次版と一致しないため、`reduce` の結合子で
  事前に `is_nan` チェック。
- 1 行 8KB-64KB の小さい payload では rayon overhead が逆効果 → `par_iter()` ではなく `par_chunks(N)` で micro-batch。

### bench gate

- 5× 出ない場合は採用しない (`docs/requirements_v0.7_rust_acceleration.md` § 2)
- 推定: 行数 1,000 / dim 768 で **8-12×** (素朴 cosine 並列の典型値)

---

## RUST-05: jsonschema-rs drop-in

**現状:** `python-jsonschema` (Python) で blockchain manifest 等を検証。
**目標:** `jsonschema-rs` (Rust) を **drop-in** で置換、初回 compile を高速化。

### 設計案

```python
class JsonSchemaValidator:
    def __init__(self, schema):
        self._py_validator = jsonschema.Draft202012Validator(schema)
        if rust_ext.HAS_RUST:
            self._rs = rust_ext.compile_schema(schema)
        else:
            self._rs = None

    def validate(self, data):
        if self._rs is not None:
            return self._rs.validate(data)
        return self._py_validator.validate(data)
```

### parity 注意

- error message の文字列形式は jsonschema-rs と Python 版で異なる。
  **error.message 内容は parity 対象外**、boolean (valid / invalid) のみ parity。
- `format` keyword (date-time / email 等) のサポート差異を要確認。

### bench gate

- 推定: schema compile **20-50×**、validate **3-10×** (jsonschema-rs 公式ベンチ)

---

## RUST-06: crossbeam audit sink

**現状:** SHA-256 audit chain の append が Python `threading.Lock` で逐次化。
**目標:** crossbeam channel + 専用 writer thread で書込みを **lock-free** 化。

### 設計案

```rust
use crossbeam_channel::{unbounded, Sender};

static AUDIT_TX: OnceCell<Sender<AuditEvent>> = OnceCell::new();

#[pyfunction]
fn audit_init(path: String) -> PyResult<()> {
    let (tx, rx) = unbounded::<AuditEvent>();
    AUDIT_TX.set(tx).ok();
    std::thread::spawn(move || {
        let mut writer = BufWriter::new(File::create(&path).unwrap());
        while let Ok(ev) = rx.recv() {
            // SHA-256 chain link + JSONL serialize
            writer.write_all(&ev.to_jsonl()).unwrap();
            writer.flush().unwrap();
        }
    });
    Ok(())
}

#[pyfunction]
fn audit_append(payload: String) {
    if let Some(tx) = AUDIT_TX.get() {
        tx.send(AuditEvent::new(payload)).unwrap();
    }
}
```

### parity 注意

- **チェーン整合性**: prev_hash の更新は writer thread でのみ行う必要あり (race 不可)
- crash safety: `BufWriter` flush タイミング ― **fsync interval** を設定可能に
- Python 側 `audit_verify()` は引き続き Python 実装 (頻度低 + ロジック複雑)

### bench gate

- 推定: 並列書込み多 (e.g. 推論並列 8) で **5-15×** (lock contention 解消)

---

## RUST-07: ChangeOp Rust 移植

**現状:** ChangeOp (構造変更案) の diff 計算 + 静的検証 hand-off が Python。
**目標:** diff 計算ホットパスを Rust、Z3 渡しは引き続き Python。

### 設計案

```rust
#[pyclass]
struct ChangeOpDiffer {
    // YAML AST へのハンドル
}

#[pymethods]
impl ChangeOpDiffer {
    fn diff(&self, before: &str, after: &str) -> PyResult<Vec<DiffEntry>> {
        // YAML parse → semantic AST diff
        // 既存 Python 実装と同じ DiffEntry 列を返す
    }
}
```

### parity 注意

- YAML 順序の正規化を **Python 側と同じアルゴリズム** で行わないと diff の order が変わる
- 大きな ChangeOp (≥1MB YAML) は Rust 側でも単スレッド (parser bottleneck)

### bench gate

- 推定: small ChangeOp **3-8×**、large **1.5-3×**
- → 5× ゲートを **小規模に対してのみ** 適用、large は 2× で OK と緩める案

---

## RUST-08: hora / arroy HNSW

**現状:** memory store の近傍検索が numpy 全件 cosine (O(N))。
**目標:** [hora](https://github.com/hora-search/hora) または [arroy](https://github.com/spotify/annoy 後継) で HNSW index、O(log N)。

### 設計案

```python
class MemoryStore:
    def __init__(self):
        if rust_ext.HAS_RUST:
            self._index = rust_ext.HnswIndex(dim=768, m=16, ef_construction=200)
        else:
            self._index = None  # fallback: numpy 全件

    def add(self, id, vec):
        if self._index:
            self._index.add(id, vec)
        else:
            self._fallback_add(id, vec)

    def search(self, query, k=10):
        if self._index:
            return self._index.search(query, k, ef=64)
        return self._fallback_search(query, k)
```

### parity 注意

- HNSW は **近似** 検索 → 厳密 (numpy 全件) と完全一致しない
- parity の代わりに **recall@k 計測** を導入: hora `search` の上位 10 件
  と numpy 全件 top-10 の重なり 95%+ を gate に
- index 永続化: hora の `save`/`load` を活用、numpy fallback と互換性なし

### bench gate

- 推定 (10K vectors, dim 768): numpy 50ms → hora 0.5ms = **100×**
- 大規模 (100K+) ではより顕著

---

## RUST-09: tokio async

**現状:** llmesh ingest HTTP 経路が Python urllib (sync, blocking)。
**目標:** tokio + reqwest で async batch ingest、connection pool 維持。

### 設計案

```rust
#[pyclass]
struct AsyncMcpClient {
    rt: tokio::runtime::Runtime,
    client: reqwest::Client,
}

#[pymethods]
impl AsyncMcpClient {
    fn batch_ingest(&self, events: Vec<PyObject>) -> PyResult<()> {
        self.rt.block_on(async {
            let futures: Vec<_> = events.iter().map(|ev| {
                self.client.post(&self.url).json(ev).send()
            }).collect();
            futures::future::join_all(futures).await;
        });
        Ok(())
    }
}
```

### parity 注意

- HTTP error 処理は Python と統一 (5xx は retry、4xx は raise)
- Python `LoveBridge` の fail-closed セマンティクス (HTTP fail は warn) を維持

### bench gate

- 推定: 100 events batch → urllib 1500ms / async 80ms = **18×**
- 単発 ingest では差が小さい (per-call overhead)

---

## RUST-10: phf TRIZ matrix

**現状:** TRIZ 39×39 矛盾マトリクスを Python dict で参照 (cache hit 1us)。
**目標:** phf (perfect hash function) でコンパイル時テーブル化、binary search なし、O(1) 真の。

### 設計案

```rust
use phf::phf_map;

static TRIZ_MATRIX: phf::Map<(u8, u8), &'static [u8]> = phf_map! {
    (1u8, 2u8) => &[35, 8, 2, 14],
    (1u8, 3u8) => &[13, 35, 8, 1],
    // ... 39 × 39 = 1521 entries
};
```

### parity 注意

- データソース (`specs/resources/triz_matrix_compact.yaml`) との sync を CI で確認
  (build.rs で YAML → Rust コード生成 + git diff チェック)
- yaml の duplicate-key bug (`9:` が 2 度) を build.rs で検出して error にする

### bench gate

- python dict (1us) vs phf (10ns) で **100×** だが、絶対 latency が小さく実害なし
- 採用判断: TRIZ heavy use ケース (`triz brainstorm` の large batch) でないと体感差なし
- → **優先度低、デモ価値中心** で扱う

---

## RUST-11: Z3 bridge

**現状:** Z3 SMT 検証は z3-solver (Python) で呼び出し、ChangeOp 検証で 100ms-1s。
**目標:** Z3 native bindings (z3.rs) で direct SMT 構築、Python ↔ Z3 の oneshot ボトルネックを除去。

### 設計案

```rust
use z3::{Config, Context, Solver, ast::Bool};

#[pyfunction]
fn verify_invariants(rules: Vec<String>) -> PyResult<bool> {
    let cfg = Config::new();
    let ctx = Context::new(&cfg);
    let solver = Solver::new(&ctx);
    for rule in rules {
        let assertion = parse_smtlib(&ctx, &rule)?;
        solver.assert(&assertion);
    }
    match solver.check() {
        z3::SatResult::Sat => Ok(true),
        z3::SatResult::Unsat => Ok(false),
        z3::SatResult::Unknown => Err(...),
    }
}
```

### parity 注意

- Z3 algorithm はバイト単位で deterministic とは限らない (ヒューリスティック)
- parity は **ans (sat/unsat/unknown) のみ**、model 内容は parity 対象外
- timeout 設定は Python 側と統一 (`solver.set_timeout(...)`)

### bench gate

- 推定: 大規模 invariant set (100+ assertion) で **3-5×** (FFI overhead 削減)
- 小規模では差なし (Z3 自体が支配)

---

## 横断: parity harness 拡張 (RUST-13 続編)

各 RUST-* に対して **対応する parity test** を `tests/property/` に追加:

| RUST-* | parity test | 厳格度 |
|---|---|---|
| RUST-02 | `test_compute_surprise_parity` (拡張) | 1e-6 |
| RUST-03 | `test_bulk_time_decay_parity` (実装済) | 1e-6 |
| RUST-05 | `test_jsonschema_validate_parity` (新) | bool 一致 |
| RUST-06 | `test_audit_chain_parity` (新) | hash 完全一致 |
| RUST-07 | `test_changeop_diff_parity` (新) | DiffEntry list 一致 |
| RUST-08 | `test_hnsw_recall_at_10` (新) | recall ≥ 95% |
| RUST-09 | `test_async_ingest_parity` (新) | event count 一致 |
| RUST-10 | `test_triz_matrix_parity` (新) | dict 完全一致 |
| RUST-11 | `test_z3_verify_parity` (新) | sat/unsat 一致 |

各 parity test は **Hypothesis ベース** で 50+ ケース、CI matrix で必ず実行。

---

## 横断: bench harness の整備

`benches/` ディレクトリに criterion ベンチを置き、各 RUST-* について
Python 版と Rust 版の比を測定。CI で **5× 未満** だと marker (warn) を
立て、**1× 未満** (= 遅化) で **fail**。

```rust
// benches/compute_surprise.rs
fn bench_compute_surprise(c: &mut Criterion) {
    let mut group = c.benchmark_group("compute_surprise");
    group.bench_function("rust_par", |b| b.iter(|| compute_surprise_par(...)));
    group.bench_function("rust_seq", |b| b.iter(|| compute_surprise_seq(...)));
    // Python 版は別途 pytest-benchmark で計測、ratio を combined.json で集約
}
```

---

## 実装順序の推奨

依存・効果・リスクの観点から:

| 順 | 項目 | 理由 |
|---|---|---|
| 1 | RUST-08 (hora HNSW) | 効果絶大 (100×)、新規追加で既存破壊なし |
| 2 | RUST-02 (rayon 並列) | 既存 RUST-02 baseline の自然延長 |
| 3 | RUST-09 (tokio async) | LoveBridge 経路の体感改善 |
| 4 | RUST-05 (jsonschema-rs) | 起動高速化 |
| 5 | RUST-06 (audit sink) | 並列書込みの安全強化 |
| 6 | RUST-11 (Z3 bridge) | 検証 heavy 利用のとき |
| 7 | RUST-07 (ChangeOp diff) | 大規模 ChangeOp が出てから |
| 8 | RUST-10 (phf TRIZ) | デモ価値が中心、最後 |

各項目を **Phase 5.x** として段階リリース (v0.6.0 = RUST-08、v0.7.0 = RUST-02 完全並列、…)。

---

## 関連

- `docs/requirements_v0.7_rust_acceleration.md` ― 要件本体 (源)
- `docs/PROGRESS.md` ― v0.5.0 までの実装履歴
- memory `[[project_llive_rust_acceleration]]` ― 段階方針
- memory `[[audit-2026-05-14]]` ― pyo3 0.24.2 アップグレード経緯
