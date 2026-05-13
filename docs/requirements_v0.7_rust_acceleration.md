# llive 要件定義 v0.7 — Rust ベース高速化レイヤ

**Drafted:** 2026-05-13
**Status:** **要件追加（実装は段階的、Phase 3 で formal-verification 接合 / Phase 4-5 で hotspot 抽出 / v1.x で広域 PyO3 化）**
**Type:** Performance / native-extension addendum
**Trigger:** ユーザ要望「Rust を使って llive の動作を高速化する仕組みを調査」

---

## 1. 動機

llive は Phase 2 完了時点で 308 tests / 95-99% coverage を達成しているが、**実運用に向けて以下のホットパスが Python 純粋実装のままでありボトルネック化が予想される**：

1. **AC-10/11 動的 edge weight** — 1 read_hit ごとに `_adjust → fetch → delete → re-insert → JSONL append`。Kùzu はバルク UPDATE 未対応のため、edge 数が 10k を超えると O(n) で減速する。
2. **MEM-07 Bayesian surprise** — 全 write イベントで `cosine similarity × |memory|` を numpy で都度計算。`memory_embeddings` が 100k 行を超えると GIL 込みで秒オーダ。
3. **CONC-02/03 並列パイプライン** — `ThreadPoolExecutor` ベースで GIL に律速、HF inference を除いた純粋 Python パスでさえ並列化メリットが薄い。
4. **MEM-08 consolidation cycle** — Jaccard / replay select / clustering が `O(events × pages)`。夜間バッチで数十万行を処理する想定。
5. **schema validation** — `jsonschema` (Python) は MMR 100MB 級の ConceptPage バリデーションで秒オーダ、CI で目立つ。
6. **EVO-02 ChangeOp invert/apply** — 形式検証 gate の中核、deterministic + property-test 維持が必須。Python 純粋実装は型ガードとデコレータで肥大化中。
7. **observability JSONL append** — `edge_weight.jsonl` / `bwt.jsonl` / `route_trace.jsonl` が高頻度書き込み (>100/s)。Python `open(...).write(...)` は flush + GIL で抑制。
8. **OBS-04 BWT meter** — 連続学習中に全タスクで eval、行列演算が増える。

llove F18 (Rust 移植戦略, 2026-05-09 立案) と整合的に、**llive にも段階的 Rust 統合戦略を導入する**。早期最適化を避け、**Phase 4 までは Python 純粋実装で意味論を固め、Phase 5 以降に hotspot 単位で PyO3 ネイティブモジュールへ置換する**。

---

## 2. 戦略原則

| 原則 | 内容 |
|---|---|
| **意味論先行・最適化後追従** | Python 実装で意味論が確定し、property-test (Hypothesis) が安定するまで Rust 化しない。早期最適化禁止。 |
| **PyO3 経由のドロップイン置換** | 同名同シグネチャの Rust モジュールを Python 側 import で切り替え可能にする。`llive.rust_ext` namespace を予約。 |
| **fallback 必須** | wheel が無い環境 (例: Apple Silicon の特殊ビルド) では Python 純粋実装に自動 fallback。`importlib` で動的 detect。 |
| **データ互換性 spec** | Rust ⇄ Python 間の構造体 / バイナリレイアウトを `specs/rust_ffi/*.spec.md` に固定。`bincode` / `serde_json` / `numpy` array view で受け渡し。 |
| **計測駆動** | Rust 化前に `pytest-benchmark` か `pyperf` でベースラインを測定、Rust 化後に 5× 以上の改善が出ないものは reject。 |
| **maturin 単一ビルド** | `pyproject.toml` の `[tool.maturin]` でビルド統合、wheel に Rust extension を bundle。OS 別 wheel は GitHub Actions で生成。 |
| **コア依存ゼロ** | Rust 拡張は `[rust]` extra に隔離、core install は Python のみで完結し続ける。`pip install llmesh-llive` は Rust なし、`pip install llmesh-llive[rust]` で有効化。 |
| **TRIZ Principle 1, 13, 25 整合** | Segmentation (hotspot 単位分割) / Inversion (Python→Rust 方向反転は llove と整合) / Self-service (自動 detect)。 |

---

## 3. 要件 (RUST-XX シリーズ)

### RUST-01: Rust Extension Skeleton (Phase 5 / v0.5.0)

`crates/llive_rust_ext/` に Cargo workspace を新設し、PyO3 ベースの空モジュールを提供：

```
crates/
  llive_rust_ext/
    Cargo.toml
    src/
      lib.rs           # pymodule! root
      surprise.rs      # placeholder
      edge_weight.rs   # placeholder
specs/
  rust_ffi/
    overview.md
    surprise.spec.md
```

`pyproject.toml` に `[tool.maturin]` ブロックを追加、`pip install -e .[rust]` で `target/wheels/*.whl` を自動取り込み。

**Acceptance:**
- `python -c "import llive.rust_ext"` が成功
- `python -c "from llive.rust_ext import __version__; print(__version__)"` でビルド済み Rust 側バージョンが取得できる
- Rust 拡張不在の環境で `from llive.rust_ext import surprise_compute; ...` が `ImportError → Python fallback` を返す

### RUST-02: Bayesian Surprise Kernel (Phase 5)

`compute_surprise(new: ndarray, mem: ndarray) -> f32` を Rust + `ndarray` + `rayon` で書き直し：

- L2 normalize 並列化 (`par_iter`)
- 行列積を `ndarray-linalg` 経由 OpenBLAS / Accelerate にディスパッチ
- 100k × 384-dim memory で目標: 5ms 以下 (Python 純粋: 80-150ms)
- Welford update も Rust 側で持つことで GIL 解放、`drop(gil)` を意識した API 設計

**Python 側:** `BayesianSurpriseGate.compute_surprise` が `llive.rust_ext.surprise_compute` 利用可能なら委譲、無ければ既存 numpy 実装にフォールバック。

### RUST-03: Edge Weight Bulk Decay (Phase 5)

`apply_time_decay(rows, ref_time, tau_map) -> Vec<(EdgeId, new_weight)>` を Rust 化：

- 全 edge を一括 fetch → Rust で `exp(-Δt / τ)` を `rayon` で並列適用 → 結果のみ Python 側で Kùzu に書き戻す
- 副次効果として **delete-and-reinsert の同期コストを 1 回にまとめる** (bulk transaction)
- 想定改善: 50k edges で Python 純粋 8s → Rust 600ms

**Python 側:** `EdgeWeightUpdater.apply_time_decay` が rust_ext 利用可能なら呼ぶ。`_lock` は Python 側で取り、Rust 側は pure computation。

### RUST-04: Jaccard / Cosine Kernel Library (Phase 5)

`consolidation.py` の `_enforce_diversity` / `_cycle` で多用される類似度計算を Rust 化：

```rust
pub fn jaccard(a: &[u32], b: &[u32]) -> f32 { ... }
pub fn cosine_sparse(a: &CsrRow, b: &CsrRow) -> f32 { ... }
pub fn pairwise_jaccard(sets: &[Vec<u32>]) -> Array2<f32> { ... } // rayon parallel
```

set-of-ids は u32 化 + sort して binary intersection。Python `set & set` 比 10-30× 高速。

### RUST-05: JSON-Schema Validator (Phase 5)

`jsonschema-rs` (Rust 実装、CPython 経由で 10-50× 高速) を `llive.schema.validator` で optional に差し替え：

```python
try:
    from jsonschema_rs import Draft202012Validator as _RustValidator
except ImportError:
    from jsonschema import Draft202012Validator as _RustValidator
```

ホット箇所: `validate_container_spec`, `validate_change_op_diff`, ConceptPage `validate_against_page_type`。

### RUST-06: JSONL Audit Sink (Phase 5)

高頻度 audit log (`edge_weight.jsonl`, `bwt.jsonl`, `route_trace.jsonl`) を Rust 側で **batch flush + lock-free queue (crossbeam-channel)** に置換：

```rust
pub struct AuditSink {
    tx: crossbeam_channel::Sender<Vec<u8>>,
    join: thread::JoinHandle<()>,
}
impl AuditSink {
    pub fn write(&self, json_bytes: Vec<u8>) -> PyResult<()> { ... }
    pub fn close(&self) -> PyResult<()> { ... } // drain and join
}
```

Python 側は writer-thread を起こさず Sender に渡すだけ、GIL 解放可能。

### RUST-07: ChangeOp Engine (Phase 6 / v0.6.0)

`change_op.py` (243 行、property-tested) の `apply` / `invert` / `compose` を Rust 移植：

- Rust 側の `ChangeOp` は `serde_json::Value` ベース、`apply`/`invert` は in-place mutation を避けて新値返却
- Z3 verifier (Phase 3 計画) と統合: Rust 側で context-length / hidden_dim 不変条件を pre-check してから Z3 へ
- Hypothesis property test を **Rust 側** にも `proptest` で並走させ、両実装の bit-exact 一致を CI で検証

### RUST-08: ANN Memory Backend (optional, Phase 6+)

Faiss-Python の代替として **`hora` または `arroy` (HNSW Rust)** を optional backend に：

- 純粋 Rust → ARM64/Apple Silicon の wheel 配布が容易
- Faiss-CPU が requires `swig` / OS 依存ビルドを抱える問題を回避
- `SemanticMemory(backend="hora")` で切り替え

### RUST-09: Concurrent Pipeline Executor (Phase 7)

GIL 律速の `ThreadPoolExecutor` を Rust 側 `tokio` ベースで再実装：

- Rust 側で I/O 多重化、HF inference 呼び出しのみ Python に戻す
- `pyo3-async-runtimes` で `asyncio.Future` 経由
- 想定: 4-thread → 16-task fan-out で latency P99 改善

### RUST-10: TRIZ Matrix Lookup (Phase 5)

39×39 矛盾マトリクス / 40 原理データを `phf` (perfect hash) で静的化、起動時 0ms ルックアップ：

- 現状: `load_matrix()` で YAML パース + dict 構築
- Rust 化: `OnceCell<HashMap<(u8, u8), Vec<u8>>>` で起動時 1 回、その後 O(1)
- Phase 3 TRIZ-02〜07 (Contradiction Detector / Principle Mapper) の性能基盤

### RUST-11: Z3 SMT Bridge (Phase 6)

Static Verifier (FR-13, M3.1) の Z3 呼び出しを **Rust 側でラップ**：

- `z3.rs` クレート使用、context lifecycle を Rust 側で管理
- Python は ChangeOp diff を JSON で渡し、Rust 側で Z3 constraints 構築 → solve → 結果のみ Python に返す
- Memory leak / GC 問題を回避

### RUST-12: Wheel CI Matrix (Phase 5)

GitHub Actions で wheel cross-build:

| OS | arch | target |
|---|---|---|
| Linux | x86_64 / aarch64 | manylinux_2_28 |
| macOS | x86_64 / arm64 | universal2 |
| Windows | x86_64 | msvc |

`maturin-action` + `cibuildwheel` ハイブリッド。Rust 拡張不在環境向けに `sdist` も配布、その場合 install 時に Rust toolchain 不要 (Python pure fallback で動作)。

### RUST-13: Compatibility Test Harness (Phase 5)

Rust 拡張 ⇄ Python 純粋実装の **同一性検査スイート**:

```python
# tests/property/test_rust_python_parity.py
@hypothesis.given(...)
def test_surprise_compute_parity(new, mem):
    py = compute_surprise_py(new, mem)
    rs = compute_surprise_rs(new, mem)
    assert abs(py - rs) < 1e-6
```

CI で両方走らせ、bit-exact (許容差 < 1e-6) を保証。Rust 化のリスクは「意味論ずれ」が最大、これを property-test で固定。

### RUST-14: Benchmark Harness (Phase 5)

`pytest-benchmark` + `criterion` (Rust 側) で常時計測：

- `benches/` ディレクトリに代表 5 シナリオ:
  1. `surprise_compute_100k_384d`
  2. `edge_decay_50k`
  3. `jaccard_pairwise_1k`
  4. `schema_validate_concept_page_1mb`
  5. `audit_log_burst_10k`
- `make bench` で全実行、結果を `D:/data/llive/benches/<date>.json` に保存
- 退行 (>10% 悪化) で CI fail

---

## 4. Phase 別実装ロードマップ

| Phase | バージョン | 内容 |
|---|---|---|
| 5 | v0.5.0 | RUST-01〜06, 10, 12〜14 (skeleton + numeric hotspots + audit + bench + CI wheel) |
| 6 | v0.6.0 | RUST-07, 11 (ChangeOp + Z3 bridge), RUST-08 (optional HNSW) |
| 7 | v0.7.0 | RUST-09 (concurrent executor reimagined) |
| v1.x | — | 全 hotspot Rust 化、ratatui llove TUI バックエンド統合 (llove F18 と同期) |

**Phase 5 は Phase 3 (Evolve) 完了後に着手**。Phase 3 では Python 実装で AI candidate generation + Static Verifier の意味論を確定させることが最優先で、Rust 化は後追い。

---

## 5. データ / 互換性 spec

`specs/rust_ffi/overview.md` に以下を固定 (Phase 5 初期に作成)：

- **Tensor 受け渡し** — `rust-numpy` の `PyReadonlyArray2<f32>` を入力、`PyArray1<f32>` を返値とする標準。`np.ndarray` は連続 / dtype f32 を呼び出し側で保証。
- **構造体シリアライズ** — `bincode 2.0` (no_std-compatible) で Python ⇄ Rust。`serde_json` は読みやすさが必要な場合のみ。
- **エラー型** — Rust 側 `LiveRustError` enum を `PyErr` に `From` 実装。Python 側に `LiveRustError(RuntimeError)` を見せる。
- **GIL 解放ポイント** — pure computation 中は `py.allow_threads(|| { ... })` で必ず解放。Python オブジェクト触る前後に明示。
- **ロギング** — Rust 側 `tracing` クレートを Python `structlog` に bridge (`tracing-subscriber` + custom layer)。

---

## 6. 既存設計との整合性

| 既存要件 | 影響 | 対応 |
|---|---|---|
| CONC-01 (thread-safe memory) | Rust 側の lock 戦略を上書きする必要 | Python 側 `_lock` を維持、Rust kernel 内は no-lock。Python ⇄ Rust 境界で保護。 |
| CONC-04 (snapshot reads) | Rust が `Arc<Snapshot>` を保持できれば snapshot isolation が自然に取れる | Phase 7 で実装、CONC-04 を Rust 化前提に再設計 |
| MEM-07 (Bayesian surprise) | RUST-02 が中心 | 既存 `BayesianSurpriseGate` を変更せず、内部委譲のみ |
| AC-10/11 (dynamic edge weight) | RUST-03 が中心 | `EdgeWeightUpdater` の `apply_time_decay` のみ Rust 化、他は Python に残す |
| EVO-02 (ChangeOp invert) | RUST-07 が中心 | Hypothesis + proptest で両実装 parity 担保 |
| FR-13 (Static Verifier) | RUST-11 (Z3 bridge) と直接統合 | Phase 6 で同時実装 |
| OBS-01〜04 (observability) | RUST-06 (audit sink) | 出力 JSONL フォーマットは不変、書き手のみ差し替え |
| LLW-02 (Wiki Compiler) | LLM コール律速のため Rust 化メリット薄い | Rust 化対象外、TRIZ-04 RAG retrieval は対象 |
| llmesh family (Phase 4) | llmesh sensor bridge の MQTT / OPC-UA は既に C 実装、Rust 化はバッファリングのみ | RUST-09 と Phase 4 sensor bridge を同時統合 |
| llove F18 (Rust 移植戦略) | データ互換性 spec を共有する | `specs/rust_ffi/` を llive / llove で共通化 |

---

## 7. リスクと先送り判断

| リスク | 影響 | 対応 |
|---|---|---|
| Rust toolchain 必須が ユーザ install を阻害 | Adoption 低下 | `[rust]` extra に隔離、sdist + Python fallback で `pip install` は常に成功 |
| wheel ビルド OS 行列の維持コスト | CI 時間増加 | GitHub Actions で並列化、`cibuildwheel` で標準化 |
| Python ⇄ Rust 意味論ずれ | バグ検出困難 | RUST-13 parity test を property-based で広域実施 |
| GIL 解放後の race condition | データ破損 | Python 側 `_lock` を Rust 境界で常時取得、Rust 内は pure computation 限定 |
| PyO3 API 変更 (0.x→1.0 不安定期) | 改修コスト | バージョン固定 + bridge layer (`llive.rust_ext._compat`) で抽象化 |
| Apple Silicon ビルド失敗 | macOS ユーザ脱落 | universal2 wheel + sdist フォールバック |
| Rust 化したのに遅い | 投資回収失敗 | RUST-14 で必須 5× 改善ゲート、ダメなら revert |
| ChangeOp invert bit-exact 不一致 | 形式検証 gate が機能不全 | RUST-07 は Phase 6 (Static Verifier と同時)、proptest で 100k 件パス必須 |
| 早期最適化による意味論凍結 | Phase 3 EVO 系の設計自由度低下 | Phase 5 まで Rust 化に着手しない。原則固持。 |

---

## 8. Out of Scope (v0.7 段階)

- **CUDA / GPU カーネル** — `candle` で書き直すのは v1.x 以降。Phase 4-5 までは torch/transformers をそのまま使う。
- **完全 Rust 再実装** — llove F18 で v3.0 候補とした「完全 Rust」は llive でも v3.0 候補。本要件は **段階的 Rust 加速** のみ扱う。
- **WebAssembly 出力** — ブラウザ実行は llove TUI でカバー、llive 側は対象外。
- **llmesh / llove との Rust API 共通化** — `specs/rust_ffi/` で型は共有するが、ABI 共有は v1.0 以降検討。
- **Rust から HF Transformers 呼び出し** — `candle` でモデル推論を内製するのは Phase 4 で hop 検討、本要件では扱わない。
- **mypy / pyright 完全対応** — Rust 拡張の `.pyi` stub は Phase 5 で `pyo3-stub-gen` で生成、Phase 6 で完全 typed。

---

## 9. 受け入れ基準 (v0.7 → v0.5.0 / Phase 5 完了時)

- ✅ `pip install llmesh-llive[rust]` が Linux/macOS/Windows で成功
- ✅ `pip install llmesh-llive` (Rust なし) でも 308 tests 全通過
- ✅ RUST-13 parity test が 1000 ケース通過 (`tests/property/test_rust_python_parity.py`)
- ✅ RUST-14 ベンチ harness で RUST-02/03/04/05/06 が **5× 以上の改善**
- ✅ `specs/rust_ffi/overview.md` + 各 hotspot spec が `docs/architecture.md` から参照可能
- ✅ Phase 5 VERIFICATION.md に Rust 拡張の有無での挙動同一性記録
- ✅ Phase 3 / Phase 4 の既存テストが Rust 拡張 ON/OFF 両方で全通過

---

## 10. 参考 / 先行例

- **llove F18 (2026-05-09)** — llove 内で同様の段階的 Rust 移植戦略を確立、`v1.x PyO3 ホットスポット → v2.0 ratatui 並走 → v3.0 完全 Rust`。本要件と整合。
- **Polars (Rust + PyO3)** — pandas 互換 DataFrame を Rust で再実装、`pip install polars` で wheel 配布、Apache Arrow ベース。
- **Tantivy (Rust 全文検索)** — Lucene 級の検索エンジンが PyO3 wheel で配布される実例。
- **Pydantic v2 (Rust core)** — Python 純粋実装の Pydantic v1 を Rust コア (pydantic-core) で 5-50× 高速化。本要件の戦略原則は Pydantic v2 の移行パターンを参考にしている。
- **jsonschema-rs** — `jsonschema` の Rust 実装、Python bindings 提供、10-50× 高速。RUST-05 で採用。
- **z3.rs** — Z3 SMT solver の安全な Rust ラッパー、PyO3 経由で Python から使える。RUST-11 で採用。
- **candle (HuggingFace, 2026)** — Rust ML フレームワーク、CPU/CUDA/Metal 対応。将来の v1.x 以降で torch 代替候補。
- **rust-numpy** — `ndarray ⇄ numpy.ndarray` zero-copy 変換、PyO3 公式。RUST-01〜04 の基盤。

---

*Drafted: 2026-05-13*
*Phase 5 から段階的に着手、Phase 4 完了 + Phase 3 EVO 安定後の措置*
*llove F18 と整合的、`specs/rust_ffi/` で互換性 spec を共有*
