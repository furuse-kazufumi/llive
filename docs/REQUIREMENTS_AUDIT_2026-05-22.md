# llive 要件定義 俯瞰レポート (2026-05-22)

> Read-only Agent (Explore) が docs/ + .planning/ + src/ を横断スキャンした
> 結果. 「要件定義が増えすぎたので整理 + 忘れていることの確認」
> (ユーザー指示 2026-05-22) への応答.

## Section A: 要件定義 docs 一覧 (18 ファイル, ~6,500 行)

| ファイル | 行数 | 主要 ID prefix | 概要 | 状態 |
|---|---|---|---|---|
| `docs/requirements_v0.1.md` | — | FR-01〜27 | Phase 1-4 概要 | **陳腐化候補** |
| `docs/requirements_v0.2_addendum.md` | — | FR 補則 | v0.1 詳細補充 | **陳腐化候補** |
| `docs/requirements_v0.3_triz_self_evolution.md` | 317 | TRIZ / 自己進化 | TRIZ 40 原理統合 | 着地 |
| `docs/requirements_v0.4_llm_wiki.md` | 367 | LLW-01〜08 | LLM Wiki (Karpathy 2026-04) | 一部着地 |
| `docs/requirements_v0.5_spatial_memory.md` | 123 | 空間メモリ | spatial awareness | 着地 |
| `docs/requirements_v0.6_concurrency.md` | 197 | 並行性 | asyncio/multiprocessing | 着地 |
| `docs/requirements_v0.7_rust_acceleration.md` | 324 | RUST-01〜18 | Rust FFI / 性能 | **17% 着地, 14 件未** |
| `docs/requirements_v0.7_rust_acceleration_v0DE_addendum.md` | 240 | RUST-17b/c, 5 パターン | 2026-05-22 追記 | **本編と分裂** |
| `docs/requirements_v0.8_cognitive_mesh.md` | 496 | COG-01〜08, CABT-01〜07 | 認知 mesh + 説明責任 | **CABT 未着地** |
| `docs/requirements_v0.9_growth_automation.md` | 348 | CREAT-01〜05, MATH-01〜08 | 数学・創造性層 | 大半着地 |
| `docs/requirements_v0.A_external_runtime_tracking.md` | 194 | ER-01〜08 | llama.cpp/GGUF 月次追従 | 操作要件 (手動) |
| `docs/requirements_v0.B_evolutionary_optimization.md` | 239 | EV-01〜09 | 進化型最適化層 | 89% 着地 |
| `docs/requirements_v0.C_llive_variant_evolution.md` | 228 | LV-GEN-01/02 | 派生集団進化 | 着地 |
| `docs/requirements_v0.D_self_referential_and_llm_operators.md` | 239 | SR-01/02, LX-01〜03 | Self-Ref + LLM Operator | **0% 着地 (credential 待機)** |
| `docs/requirements_v0.E_competitive_coevolution.md` | 621 | **CE-01〜34** | 競争的協調進化 | **71% 着地** |
| `.planning/REQUIREMENTS.md` | 80+ | CORE/BC/MEM/RTR/EVO/OBS/TRIZ/LW | GSD workflow REQ-ID 化 | source-of-truth 候補 |
| `docs/roadmap.md` | 100+ | M1.1〜M4.d | Gantt + Phase | 着地 |
| `docs/PROGRESS.md` | 2199 | M8.x session log | リアルタイム進捗 | 着地 |

## Section B: 要件 ID 着地状況サマリ

| Prefix | 件数 | 着地 | 未着地 | 着地率 |
|---|---:|---:|---:|---:|
| **CE-01〜34** | 34 | 24 | 10 | 71% |
| **RUST-01〜18** | 18 | **3** | **15** | **17%** ⚠ |
| **CABT-01〜07** | 7 | **0** | **7** | **0%** ⚠ |
| **MATH-01〜08** | 8 | 5 | 3 | 63% |
| **CREAT-01〜05** | 5 | 5 | 0 | 100% ✓ |
| **COG-01〜04** | 4 | 4 | 0 | 100% ✓ |
| **COG-05〜08** | 4 | **0** | **4** | **0%** ⚠ |
| **EV-01〜09** | 9 | 7 | 1 | 89% |
| **OKA-01〜07** | 7 | 6 | 1 | 86% |
| **VRB-02/04/05/06** | 4 | 3 | 1 | 75% |
| **LLIVE-001〜008** | 8 | 3 | 5 | 38% |
| **FR-01〜27** | 27 | 19 | 8 | 70% |
| **MEM-01〜09** | 9 | 9 | 0 | 100% ✓ |
| **BC-01〜05** | 5 | 4 | 1 | 80% |
| **CORE-01/02** | 2 | 2 | 0 | 100% ✓ |
| **RTR-01/02** | 2 | 2 | 0 | 100% ✓ |
| **EVO-01〜08** | 8 | 5 | 3 | 63% |
| **OBS-01〜04** | 4 | 4 | 0 | 100% ✓ |
| **TRIZ-01〜04/07** | 5 | 5 | 0 | 100% ✓ |
| **SR-01/02** | 2 | **0** | **2** | **0%** ⚠ |
| **LX-01〜03** | 3 | **0** | **3** | **0%** ⚠ |
| **ER-01〜08** | 8 | 0 | 8 | 0% (操作要件) |
| **総計** | **~220** | **~120** | **~100** | **55%** |

## Section C: 陳腐化候補 (統合 / archive 推奨)

1. **v0.1.md + v0.2_addendum.md** — `.planning/REQUIREMENTS.md` と内容重複. archive 化推奨
2. **v0.7 本編 + v0.7_addendum** — 同 feature が 2 ファイル分裂. 統合推奨
3. **v0.C/v0.D/v0.E** — 3 つが 2026-05-21 に同日新規登録. dependency graph 化必要

## Section D: 忘れられている要件 (本セッション「気づき」)

| # | ID | 状態 | 理由 |
|---|---|---|---|
| 1 | **CABT-01〜07** | docs 496 行定義 / src 0 件 | M8.8/M8.9 で進行中だが docs に未反映 |
| 2 | **RUST-02〜12, 14, 18** (14 件) | docs 詳細 / src 0 件 | phase 割当が docs にない |
| 3 | **LX-01〜03** | docs 239 行定義 / src 0 件 | credential 待機, timeline 不明 |
| 4 | **SR-01/02** | docs 定義 / src 0 件 | EV 完了後とのことだが日付なし |
| 5 | **EVO-03/05/08** | .planning 定義 / src 0 件 | Phase 3 スコープ. timeline 不明 |
| 6 | **COG-05〜08** | v0.8 定義 / src 0 件 | governance/advice/witness 層 未着手 |
| 7 | **LV-GEN dimensionality** | v0.C 19-dim vs v0.D 38-dim | current が不明確 |

## Section E: 推奨整理アクション

### 高優先 (高 ROI / 低リスク)

1. `v0.1.md` + `v0.2_addendum.md` を `docs/archive/` に `git mv` (履歴保持)
2. `v0.7` + `v0.7_addendum` を本編統合, RUST-02〜18 の phase 割当を明示
3. `docs/dependencies.md` 新規 — v0.C/v0.D/v0.E の依存グラフ
4. v0.8.md に CABT skeleton 実装状況追記 (M8.1〜M8.9 mapping)
5. memory に `[[project_llive_credential_blockers]]` — LX-01 等 credential 待機 ID を集約

### 中優先

6. `docs/REQUIREMENTS_AUDIT_2026-05-22.md` (本ファイル) を quarterly レビュー の起点に
7. genome dimensionality versioning (`GENOME_VERSION = "v0.C-19" / "v0.D-38"`)
8. roadmap.md と `.planning/REQUIREMENTS.md` の重複 check

### 低優先

9. memory cross-reference 自動化 — `[[project_llive_*]]` で言及される ID が docs/src のどちらにも無いものを定期 flag
10. docs naming 統一規約

## 関連

- 全要件 doc: `D:/projects/llive/docs/requirements_v0.*.md`
- GSD トレーサビリティ: `D:/projects/llive/.planning/REQUIREMENTS.md`
- リアルタイム進捗: `D:/projects/llive/docs/PROGRESS.md`
- 本ファイルは **次セッション以降の整理マラソンの起点**
