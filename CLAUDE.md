# llive — Project Instructions

> 自己進化型モジュラー記憶 LLM フレームワーク。llmesh / llove ファミリーの第四メンバー。

このファイルは Claude Code 等の AI 実装支援環境に対する指示書。

## Project Identity

- **Name**: llive
- **PyPI**: `llmesh-llive`
- **Path**: `D:/projects/llive/`
- **GitHub**: `furuse-kazufumi/llive`
- **License**: MIT
- **Python**: 3.11.x (`>=3.11,<3.12`)

## Core Value

**コア重みを再学習せず、新しい能力を安全に追加し続けられる LLM 基盤**

## Document Hierarchy

実装着手前に必ず読むべき順序:

1. **`.planning/PROJECT.md`** — プロジェクト全体像、Requirements、Constraints、Key Decisions
2. **`.planning/REQUIREMENTS.md`** — REQ-ID 化された要件 + Traceability
3. **`.planning/ROADMAP.md`** — Phase 1〜4 + Success Criteria
4. **`.planning/STATE.md`** — 現在の状態、Next Action

それから詳細を参照:

5. **`docs/requirements_v0.1.md`** — 受領原文 (FR-01〜11 / NFR-01〜06)
6. **`docs/requirements_v0.2_addendum.md`** — TRIZ 由来 FR-12〜22 + 8 層アーキテクチャ + 設計パターン
7. **`docs/requirements_v0.3_triz_self_evolution.md`** — TRIZ 内蔵 FR-23〜27
8. **`docs/architecture.md`** — 8 層 + Mermaid 図 7 種
9. **`docs/data_model.md`** — エンティティ JSON Schema 風定義
10. **`docs/yaml_schemas.md`** — ContainerSpec / SubBlockSpec / CandidateDiff 正本
11. **`docs/family_integration.md`** — llmesh / llove 統合詳細

その他: `evaluation_metrics.md` / `security_model.md` / `observability_schema.md` / `testing_strategy.md` / `model_templates.md` / `glossary.md` / `roadmap.md`

## GSD Workflow

このプロジェクトは GSD (Get Shit Done) ワークフローで管理されます。`.planning/config.json` を参照。

**Common commands:**
- `/gsd-discuss-phase N` — Phase N の context 確認 + アプローチ議論
- `/gsd-plan-phase N` — Phase N の plan (PLAN.md) 生成
- `/gsd-execute-phase N` — Phase N の plan 実行
- `/gsd-verify-work` — 完成物 vs Requirements 検証
- `/gsd-progress` — 現状確認 + 次アクション提案

## Architecture Layers (8)

```
L8: llove HITL Layer       (TUI review, memory viz, arena)
L7: Observability & Bench  (OpenTelemetry, dashboards)
L6: Evolution Manager      (proposal / mutation / promote / rollback)
L5: Memory Fabric          (semantic / episodic / structural / parameter)
L4: Block Container Engine (Composite + Strategy + Builder)
L3: Core Model Adapter     (HF / vLLM / TGI)
L2: Orchestration          (pipeline + router + scheduler)
L1: Interface              (CLI / MCP / REST / Batch)
      ↕
llmesh I/O Bus (MQTT / OPC-UA) — Adapter + Bridge + Pub/Sub
```

## Design Patterns Required

- 全体: Hexagonal + Microkernel + Event-Driven + CQRS+ES + Pipes&Filters + Actor + Clean
- BlockContainer: Composite + Strategy + Builder + Specification
- Memory: Repository + CQRS + Event Sourcing + Proxy (zone access)
- Evolution: Command + Memento + State + Saga
- HITL: MVVM + Command

## 拡張点 (EP-01〜05)

新規追加時の遵守事項:
- 新 sub-block: Strategy + Plugin + Specification
- 新 memory backend: Repository + Adapter
- 新 mutation policy: Strategy + Command 互換
- 新 modal encoder: Bridge + Adapter
- 新 transport: Bridge + Adapter + Pub/Sub

## RAD Corpus 連携

raptor の RAD (Research Aggregation Directory) コーパスを `RAPTOR_CORPUS_DIR` 環境変数で参照する。デフォルト:

```
RAPTOR_CORPUS_DIR=C:/Users/puruy/raptor/.claude/skills/corpus
```

特に関連深い分野:
- `neural_signal_corpus_v2` / `cognitive_ai_corpus_v2` — 海馬-皮質 consolidation, FR-12, FR-16
- `reinforcement_learning_corpus_v2` — Router policy, mutation policy
- `formal_methods_corpus_v2` / `automated_theorem_proving_corpus_v2` — Static Verifier (FR-13)
- `cryptography_corpus_v2` — Signed Adapter (FR-18)
- `hacker_corpus_v2` / `security_corpus_v2` — Quarantine zone (FR-17)
- `industrial_iot_corpus_v2` — llmesh Sensor Bridge (FR-19)
- `tinyml_corpus_v2` — Multi-precision shadow eval (FR-14)
- `compiler_corpus_v2` — Container 実行プラン compile
- `multimodal_corpus_v2` — modal encoder bridge (Phase 4 拡張)

`triz-ideation` / `cross-domain-ideation` / `rad-research` スキルは raptor 起点で起動可能。

## 実装方針 (Claude Code 用)

1. **spec-driven**: コード書く前に schema / interface を確定
2. **typed Python**: 全 public 関数に type hint 必須、`mypy` strict 対応
3. **UTF-8 boundary**: I/O 境界で明示
4. **テスト同時生成**: 本体と同時に tests/ も書く
5. **traceability**: REQ-ID, FR-XX, EP-XX をコメント / docstring に明記
6. **可視化**: 主要 sub-block の意思決定はログ + メトリクス + llove TUI で観察可能に
7. **段階的拡張**: Phase 1 MVR を確実に動かしてから次段階へ

## Sensitive Patterns to Avoid

- ❌ コア重みの直接 in-place 更新 (FR-01 違反)
- ❌ 署名なし adapter のロード (FR-18 違反)
- ❌ quarantine zone からの未検証 cross-zone read (FR-17 違反)
- ❌ HITL バイパスの production 昇格 (NFR-06 違反)
- ❌ provenance なしの memory write (FR-06 違反)
- ❌ `sys.path` 操作 (raptor 流儀踏襲、明示的 import path 利用)

## Family Members

- [llmesh](https://github.com/furuse-kazufumi/llmesh) — マルチプロトコル LLM ゲートウェイ (v1.5.0)
- [llove](https://github.com/furuse-kazufumi/llove) — TUI dashboard (v0.6.x)
- [llmesh-suite](https://github.com/furuse-kazufumi/llmesh-suite) — メタパッケージ (v0.1.0)
- llive — 本リポジトリ (v0.0.1)

## Maintainer

- Kazufumi Furuse <kazufumi@furuse.work>

---
*Last updated: 2026-05-13 after initialization*
