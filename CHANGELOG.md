# Changelog

このプロジェクトの変更履歴。形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、バージョニングは [Semantic Versioning](https://semver.org/lang/ja/) に従う。

## [Unreleased]

### Added (Phase 5-7 要件定義のみ、実装は未着手)

- `docs/requirements_v0.7_rust_acceleration.md` — Rust 高速化レイヤ要件 (RUST-01〜14)。PyO3 + maturin による段階的 hotspot Rust 化戦略 (Phase 5: numeric/audit / Phase 6: formal verification bridge / Phase 7: tokio async concurrency)。早期最適化禁止、5× 改善ゲート、`[rust]` extra 隔離原則。

## [0.2.0] — 2026-05-13

Phase 2: Adaptive Modular System リリース。4 層メモリ + surprise-gated write + consolidation cycle + LLM Wiki 統合 + 並行パイプラインを実装。

### Added

#### Phase 2 v2 (9 reqs)

- **MEM-05**: Structural memory (Kùzu graph backend) — `src/llive/memory/structural.py`
- **MEM-06**: Parameter memory (adapter store, SHA-256 検証) — `src/llive/memory/parameter.py`
- **MEM-07**: Bayesian surprise gate (Welford online mean+variance, dynamic θ) — `src/llive/memory/bayesian_surprise.py`
- **MEM-08**: episodic→semantic consolidation cycle (Wiki Compiler 統合) — `src/llive/memory/consolidation.py`
- **MEM-09**: 5-stage phase transition (hot/warm/cold/archived/erased) — `src/llive/memory/phase.py`
- **BC-04**: adapter / lora_switch sub-blocks — `src/llive/container/subblocks/adapter_block.py`
- **BC-05**: nested_container (max_depth + circular detection) — `src/llive/container/executor.py`
- **OBS-03**: llove TUI 用 JSONL 仕様確定 (`docs/llove_jsonl_v1.md`)
- **OBS-04**: BWT (Backward Transfer) meter — `src/llive/evolution/bwt.py`

#### LLM Wiki integration (4 reqs, Karpathy 2026-04 パターン統合)

- **LLW-01**: ConceptPage 第一級表現 — `src/llive/memory/concept.py`
- **LLW-02**: Wiki Compiler (consolidation 統合) — `src/llive/memory/consolidation.py::Consolidator._cycle`
- **LLW-03**: page_type 別 JSON Schema (4 種) — `specs/wiki_schemas/*.v1.json`
- **LLW-06**: 外部生ソース ingest CLI — `src/llive/wiki/ingest.py` + `llive wiki ingest`

#### Anti-Circulation Safeguards (LLW-AC, 8 reqs)

- **AC-01**: Source-anchored provenance (derived_from は raw event_ids のみ許可)
- **AC-03**: Evidence-anchored LLM prompts
- **AC-04**: Diversity preservation (merge downgrade)
- **AC-05**: One-pass guarantee (cycle 前に snapshot 取得)
- **AC-08**: Diversity-aware Replay Select (surprise-weighted)
- **AC-09**: Edge weight semantics (Jaccard)
- **AC-10**: Dynamic edge weight (5 triggers: read_hit / time_decay / contradiction / surprise / random_boost) — `src/llive/memory/edge_weight.py`
- **AC-11**: Exploration vs exploitation (floor / random_boost / UCB1) — `EdgeWeightUpdater`

#### Concurrency primitives (3 reqs, v0.6 並行プロンプト処理要件)

- **CONC-01**: Thread-safe memory layers (全 backend に `_lock` 取得)
- **CONC-02**: ConcurrentPipeline (multi-prompt 並行) — `src/llive/orchestration/concurrent.py`
- **CONC-03**: BranchExplorer (parallel containers / same prompt) — `Pipeline.run_with_container`

### Changed

- `pyproject.toml`: `0.2.0.dev0` → `0.2.0`。依存に `kuzu`, `apscheduler`, `safetensors` を core 追加。`[torch]` extra に `peft`, `hdbscan` 追加。`[ingest]` extra (pypdf / arxiv / readability-lxml / requests) と `[llm]` extra (anthropic) を新設。
- `docs/roadmap.md`: Phase 5 / Phase 6 / Phase 7 (Rust acceleration) milestone を新規追加、バージョニング戦略を 0.7.x まで拡張。
- `.planning/STATE.md`: Phase 2 完了として記録、Next Action を Phase 3 着工 + v0.2.0 公開検討に更新。

### Quality gates

- **Tests**: 308 passed (Phase 1 baseline 49 + Phase 2 component 45 + Phase 2 unit 200+ + property tests)
- **Coverage**: 99% (`src/llive` ベース、optional dep / real LLM 経路は exclude_lines で除外)
- **Lint**: ruff `All checks passed!` (0 warnings on `src/` + `tests/`)
- **Type**: mypy 未実行 (Phase 3 で強化予定)

### Documentation

- `.planning/phases/02-adaptive/02-CONTEXT.md` / `02-PLAN.md` / `02-VERIFICATION.md`
- `docs/requirements_v0.4_llm_wiki.md` (LLW-01〜08 全体仕様)
- `docs/requirements_v0.5_spatial_memory.md` (Phase 3+ 予定)
- `docs/requirements_v0.6_concurrency.md` (CONC-01〜08)
- `docs/llove_jsonl_v1.md` (OBS-03 連携フォーマット)

## [0.1.1] — 2026-05-13

### Fixed

- パッケージング: `specs/` を `llive/_specs/` として wheel に bundle、`llive` import 時に同梱 JSON Schema が見つかるよう修正。

## [0.1.0] — 2026-05-13

Phase 1: Minimal Viable Research Platform リリース。最初の公開バージョン。

### Added

- 16 requirements (CORE / BC / MEM / RTR / EVO / OBS / TRIZ Phase 1 系) 実装
- 49 tests pass / 82% coverage
- PyPI 初回公開 (`pip install llmesh-llive`)
- GitHub: https://github.com/furuse-kazufumi/llive

[Unreleased]: https://github.com/furuse-kazufumi/llive/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/furuse-kazufumi/llive/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/furuse-kazufumi/llive/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/furuse-kazufumi/llive/releases/tag/v0.1.0
