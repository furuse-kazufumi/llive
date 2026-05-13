# Changelog

このプロジェクトの変更履歴。形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、バージョニングは [Semantic Versioning](https://semver.org/lang/ja/) に従う。

## [Unreleased]

### Planned

- Phase 5+ Rust 高速化 (RUST-01〜14) — 要件 v0.7 で確定済、実装は本要件自身の「Phase 4 完了 + EVO 系安定後の措置」原則に従って後続セッションで段階着手予定。

## [0.3.0] — 2026-05-14

Phase 3 (Controlled Self-Evolution MVR) + Phase 4 (Production Security MVR) 同時リリース。
両フェーズは並列実装したため共通 commit に bundle。

### Added (Phase 3 — Controlled Self-Evolution)

- **EVO-04**: Static Verifier `verify_diff(before, ops, invariants)` — 構造的事前検査 + Z3 SMT 任意レイヤ (`[verify]` extra)。終状態 invariant チェック + 全 ChangeOp トラジェクトリ整数論モデル。`src/llive/evolution/verifier.py`
- **EVO-06**: Failed-Candidate Reservoir — DuckDB シーケンス順序保証 append-only テーブル、`mutation_policy` / `contradiction_id` でフィルタ・サンプリング・prune。`src/llive/evolution/reservoir.py`
- **EVO-07**: Reverse-Evolution Monitor — BWT/pollution/rollback_rate/latency_p99 閾値駆動の自動ロールバック判定。inverse ChangeOp チェイン生成 + JSONL audit。`src/llive/evolution/reverse_monitor.py`
- **TRIZ-02**: Contradiction Detector — メトリクス時系列 → 39 工学特性 ペアの矛盾抽出 (前/後半平均差分、severity floor、direction-aware)。`src/llive/triz/contradiction.py`
- **TRIZ-03**: Principle Mapper — 39×39 矛盾マトリクス引き + examples 数による重み付け + 未登録 pair の fallback。`src/llive/triz/principle_mapper.py`
- **TRIZ-04**: RAD-Backed Idea Generator — pluggable `IdeaLLM` Protocol、決定的 `TemplateIdeaLLM` フォールバック、`RAPTOR_CORPUS_DIR` の INDEX.md スキャンによる RAD 裏付け。`src/llive/triz/rad_generator.py`
- **TRIZ-07**: Self-Reflection Session — `ContradictionDetector → PrincipleMapper → RadBackedIdeaGenerator → verify_diff → reservoir spool` 一発実行。HITL 用 JSONL 出力。`src/llive/triz/self_reflection.py`
- **LLW-04**: Wiki Contradiction Detector — provenance.derived_from の duplicate source / linked_concept_ids の duplicate slug / `structured_fields["contradicts"]` 明示注釈の 3 種を検出。`src/llive/wiki/contradiction.py`
- **LLW-05**: Wiki diff as ChangeOp — `AddConcept / RemoveConcept / MergeConcept / SplitConcept` + `WikiDiff` + `apply_wiki_diff` / `invert_wiki_diff` (Memento/Saga 鏡像)。`src/llive/evolution/wiki_change_op.py`

### Added (Phase 4 — Production Security)

- **SEC-01**: Quarantined Memory Zone — `ZonePolicy` (read/write 許可リスト + signature_required) + `QuarantinedMemoryView` で `StructuralMemory` ラップ、cross-zone 読み書きを policy 違反時に `ZoneAccessDenied` で拒否。`src/llive/security/zones.py`
- **SEC-02**: Signed Adapter Marketplace — Ed25519 (cryptography ライブラリ) で AdapterProfile の SHA-256 + identity fingerprint を署名。`generate_keypair` / `sign_adapter` / `verify_adapter`、重みファイル改竄・profile drift・誤公開鍵の各シナリオで検出。`src/llive/security/adapter_sign.py`
- **SEC-03**: Audit Trail (SHA-256 hash chain) — SQLite (stdlib のみ、追加 wheel 不要) append-only テーブル、`entry_hash = SHA256(prev_hash || ts || actor || action || payload_json)`、`verify_chain` で改竄行を first-broken-seq で報告。`src/llive/security/audit.py`

### Deferred to v0.3.1+

- **EVO-03**: LLM-based candidate generation (現状は TemplateIdeaLLM)
- **EVO-05**: Multi-precision shadow eval (torch 必須)
- **EVO-08**: Population-based search (apscheduler 統合)
- **TRIZ-05/06**: 9-Window / ARIZ pipeline
- **SEC-04**: mTLS / OIDC (infra 依存)
- **INT-01/02/03**: llmesh MQTT/OPC-UA / SPC モニタ / llove Candidate Arena (外部リポ統合)

### Changed

- `pyproject.toml`: version 0.2.0 → 0.3.0。`cryptography>=42.0` を core 追加。`[verify]` extra (`z3-solver>=4.13`) 新設。
- `.planning/STATE.md`: Phase 3 / Phase 4 を完了として記録。Next Action を Phase 5 (Rust skeleton) に更新。
- `.planning/REQUIREMENTS.md`: Phase 3 16 reqs / Phase 4 7 reqs を Validated に更新。

### Quality gates

- **Tests**: 429 passed (Phase 2 baseline 308 + Phase 3: 86 + Phase 4: 35)
- **Coverage**: 98% (target 99%, Phase 4 SQLite/cryptography ラッパで -1pp、Phase 5 で詰める)
- **Lint**: ruff `All checks passed!` (src/ + tests/ 0 warnings)
- **Build**: `python -m build` で sdist + wheel 生成、twine check PASSED

### Documentation

- `docs/requirements_v0.7_rust_acceleration.md` (Phase 5+ design contract、本 release では設計のみ、実装は段階的)
- Phase 3 検証は `.planning/phases/03-evolve/` (本 release で追加)
- Phase 4 検証は `.planning/phases/04-production-security/` (本 release で追加)

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

[Unreleased]: https://github.com/furuse-kazufumi/llive/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/furuse-kazufumi/llive/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/furuse-kazufumi/llive/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/furuse-kazufumi/llive/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/furuse-kazufumi/llive/releases/tag/v0.1.0
