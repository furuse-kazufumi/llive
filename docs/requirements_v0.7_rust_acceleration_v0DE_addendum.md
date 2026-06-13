# llive 要件定義 v0.7 — Rust 高速化 v0.D/v0.E Addendum

**Drafted:** 2026-05-21
**Status:** **要件追記** (既存 `requirements_v0.7_rust_acceleration.md`
RUST-01〜14 への追補)
**Type:** Rust performance hotspot mapping for v0.D/v0.E (進化系)
**Trigger:** ユーザー Goal (2026-05-21):

> 「完璧に近い状態で Release 環境なレベルまで完成 + Rust 実装による高速化
> も検討すること」

---

## 0. 位置づけ

既存 v0.7 RUST-01〜14 は **Phase 2 (Production) 時点の hotspot** を対象に
策定. 2026-05-21 セッションで **v0.B/v0.C/v0.D/v0.E (進化系) を一気に
着地** したため, **新 hotspot 6 件** を addendum として登録.

既存 RUST-FX とは独立に着工可能 (依存層が違う). 5× 改善ゲート + bit-exact
parity test + `[rust]` extra 隔離 の方針は継承.

---

## 1. v0.D/v0.E 由来の新 Hotspot

### RUST-15: PeerScoreMatrixOps (CE-01 N×N pair_score)

**現状 (Python)**:
- `PeerEvaluationMatrix.column_mean / row_mean / collusion_score`
- 30 体集団 (900 pairs) で実 LLM 採点を走らせる際は LLM が bottleneck だが,
  **mock baseline** や **本日着地済 PeerFitnessAdapter** では Python の
  np 呼び出しが loop overhead で律速する.

**Rust 化目標**:
- `rust-numpy` + `ndarray` で N×N matrix の column/row 集約 + collusion
  3 指標 (variance / symmetry / concentration) を 1 pass.
- 30 体: 100µs → 10µs 目標 (10×). 1000 体: 50ms → 5ms 目標.
- crate: `ndarray` + `numpy` (PyO3).

**parity test**:
- Hypothesis で N×N float matrix を generate → Python / Rust 両方で集約 →
  RMSE < 1e-9.

**Approval**: 5× ゲート + RUST-14 ベンチハーネス追加.

---

### RUST-16: NoveltySearch_kNN_Distance (CE-27)

**現状 (Python)**:
- `NoveltyScorer.novelty(values)` = archive (size ≤1000) との distance →
  k-NN 平均.
- 30 体集団 × 1000 archive × 19 dim = 570K float 計算 per generation.
- 数百 ms オーダー (実 LLM 評価より速いが mock baseline では律速).

**Rust 化目標**:
- `ndarray` + `rayon` の SIMD + 並列で 30µs → 5µs 目標 (6-10×).
- archive size 10,000 でも 50ms 内維持.
- crate: `kdtree` (k-NN tree) で archive add/query を amortize.

**parity test**:
- proptest: random archive + random query → k 番目の距離が exact (距離自体は float so atol 1e-12).

---

### RUST-17: LatinHypercubeSampler (CE-28)

**現状 (Python)**:
- `scipy.stats.qmc.LatinHypercube` (Cython 内部) — 既に十分速いが
  scipy 依存重い (~50MB).

**Rust 化目標**:
- `scrs` (Sobol/Halton/LHS) もしくは自前 LHS 実装. scipy 依存 optional 化.
- 起動時間: 30 体 19 dim LHS 生成 5ms → 1ms 目標.
- crate: `scrs` or 自前 `rand_distr`.

**parity test**:
- 各 dim の binning 統計が scipy LHS と等価 (KS-test).

**意義**: scipy 依存を `[rust]` extra に押し出して core install 軽量化.

---

### RUST-18: SelfAdaptiveSigmaUpdate (SR-01)

**現状 (Python)**:
- `SelfAdaptiveGaussianMutation.__call__`: per-individual 38 dim genome の
  log-normal σ update + relative-to-width object update.
- 集団 50 × 30 世代 = 1,500 update × 38 dim = 57,000 計算. numpy で
  20ms 程度.

**Rust 化目標**:
- `ndarray` + ループ内化で **3-5×** (5ms 目標).
- crate: `rust-numpy` + `rand_distr`.

**parity test**:
- 同 seed で Python / Rust 両方で N(0,1) sequence を再現 → genome 値の
  差分 RMSE < 1e-12.

---

### RUST-19: PersonaEffectiveAffinity (CE-19)

**現状 (Python)**:
- `PersonaComposition.effective_factor_affinity()` = 加重和 + normalize.
- 10 dim × 5 personas × 集団 size. small. **本物の bottleneck ではない**.

**Rust 化判断**: **後回し OK**. RUST-15/16 完了後の付加価値として検討.
場合によっては **Rust 化見送り** (Python で十分速い).

---

### RUST-20: LexicaseSelectionInnerLoop (CE-34)

**現状 (Python)**:
- `LexicaseSelection.__call__`: criteria を shuffle → 各 step で
  candidates から worst を脱落. Python list comprehension.
- 集団 50 × criteria 5 → 250 個の inner step. small.

**Rust 化判断**: **後回し OK**. 実 production で fitness 評価が LLM
だと, Lexicase の inner loop は無視できる. mock baseline で目立つ程度.

---

## 2. 優先順位

優先 HIGH (実際に bottleneck):

| ID | 期待倍率 | 着工条件 |
|---|---|---|
| **RUST-15** | 5-10× | mock baseline で N×N matrix が hot path 確認後 |
| **RUST-16** | 6-10× | archive size 5000+ 想定の novelty search 運用後 |
| **RUST-17** | 5× | scipy 依存軽量化が目的の場合 |

優先 MID:

| ID | 期待倍率 | 着工条件 |
|---|---|---|
| **RUST-18** | 3-5× | 大規模集団 (size>100) 運用後 |

優先 LOW (見送り候補):

- RUST-19 PersonaEffectiveAffinity — Python で十分
- RUST-20 LexicaseSelection — fitness 計算が LLM の場合 negligible

---

## 3. 既存 v0.7 RUST-01〜14 との関係

| 既存 ID | 内容 | v0.E との関係 |
|---|---|---|
| RUST-02 Bayesian surprise | memory layer | v0.E では使われていない. 独立着工 |
| RUST-03 Edge weight decay | structural memory | 同上 |
| RUST-04 Jaccard / cosine | semantic similarity | v0.E persona_dissimilarity の **Jaccard 部分**で共有可能 |
| RUST-06 Audit sink | governance | v0.E CE-07 Approval Bus 連携の前提 |
| RUST-09 tokio async | I/O bottleneck | v0.E CE-02 PeerCommunication MCP で連携 |

→ **RUST-04 拡張版** として persona Jaccard も同時 Rust 化が効率的.

---

## 4. Implementation Order (推奨)

```
Stage A — v0.7 既存:
  RUST-02 Bayesian surprise (Phase 5 既定)
  RUST-04 Jaccard / cosine (Phase 5 既定, persona も同時)

Stage B — v0.7 Addendum (v0.D/v0.E):
  RUST-15 PeerScoreMatrixOps (集団 50+ 運用前提なら HIGH)
  RUST-16 NoveltySearch k-NN (archive 5000+ 運用前提なら HIGH)
  RUST-17 LatinHypercubeSampler (scipy 軽量化したいなら MID)
  RUST-18 SelfAdaptiveSigma (大規模集団 size>100 想定なら MID)

Stage C — 必要なら追加:
  RUST-19 PersonaEffectiveAffinity (現状 LOW)
  RUST-20 LexicaseSelection (現状 LOW)
```

---

## 5. Bit-Exact Parity Strategy

全 Rust 移植は **Hypothesis + proptest** で bit-exact parity を担保.

| 項目 | Python | Rust | 許容差 |
|---|---|---|---|
| RUST-15 (N×N agg) | numpy float64 | ndarray f64 | RMSE 1e-9 |
| RUST-16 (k-NN dist) | numpy linalg.norm | ndarray + rayon | 1e-12 (距離は float) |
| RUST-17 (LHS sample) | scipy qmc | scrs | KS-test p > 0.05 (分布) |
| RUST-18 (σSA-ES) | numpy random.normal | rand_distr Normal | seed 同期で 1e-12 |

`rand` crate と numpy の RNG は **互換性なし**ため, seed 同期は **numpy 側
が ground truth** とし, Rust 側は numpy-seeded ndarray を直接受け取る方が
parity を取りやすい (RNG 生成は Python 側).

---

## 6. Release-ready Integration

Rust 化は **Phase 5 着工** 既定 ([[project-llive-rust-acceleration]] 方針).

ただし **Release 環境**として完成度を上げるには **Rust 化以前**に:

1. ruff / mypy clean (本日 ruff 59/70 fix, 残 11 軽微)
2. CHANGELOG / version bump (v0.5.0 → v0.6.0a)
3. Demo scripts 拡張 (本日 demo_self_adaptive_variant.py 着地, v0.E peer
   evaluation demo を追加予定)
4. PR 分割 (optimize/core-2026-05-20 を 5 件に分けて main へ)
5. README に v0.D/v0.E section 追加

これら **Python 完成** 完了後に Rust addendum 着工.

---

## 7. References

### 直接根拠

- [[project-llive-rust-acceleration]] (既存 v0.7 RUST-FX)
- [[goal-release-ready-v0E-rust]] (本日 Goal)
- [[project-llive-v0E-coevolution]] (v0.E 構想)

### 内部 cross-reference

- `docs/requirements_v0.7_rust_acceleration.md` (既存)
- `docs/requirements_v0.D_self_referential_and_llm_operators.md`
- `docs/requirements_v0.E_competitive_coevolution.md`
- `src/llive/perf/evolutionary/peer_evaluation.py` (RUST-15 対象)
- `src/llive/perf/evolutionary/diversity.py` (RUST-16/17 対象)
- `src/llive/perf/evolutionary/self_adaptive.py` (RUST-18 対象)
- `src/llive/perf/evolutionary/persona.py` (RUST-19 対象)
- `src/llive/perf/evolutionary/mating.py` (RUST-20 対象)

### 関連 maintainer memory

- [[project-llove-rust-migration]] — specs/rust_ffi 共有
- [[feedback-llive-measurement-purity]] — on-prem 限定
- [[feedback-benchmark-honest-disclosure]] — 5× ゲートの根拠
