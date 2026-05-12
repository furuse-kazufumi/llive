# llive

## What This Is

llive は自己進化型モジュラー記憶 LLM フレームワーク。固定 Decoder-only LLM コア + 可変長 BlockContainer + 4 層外部記憶 (semantic / episodic / structural / parameter) + 審査付き構造進化 を組み合わせ、コア重みを再学習せず継続的に能力拡張できる研究開発基盤。llmesh / llove / llmesh-suite に続くファミリーの第四メンバー（PyPI 名 `llmesh-llive`）。

## Core Value

**「コア重みを再学習せず、新しい能力を安全に追加し続けられる LLM 基盤」**

3 つの矛盾を **両立** する：
- 安定な中核重みを維持しつつ、新しい能力を素早く追加できる
- 探索空間を広く取りつつ、評価コストは抑えられる
- 記憶容量を増やしつつ、ノイズや忘却は抑えられる

## Requirements

### Validated

(None yet — ship to validate. 既存 docs/ と specs/ は設計成果であり実装ではない。)

### Active

#### Phase 1 (MVR) — schema + Core + Memory + Container + 単一 candidate eval

- [ ] **CORE-01**: HuggingFace 系 Decoder-only LLM を `BaseModelAdapter` でラップして load・generate できる
- [ ] **CORE-02**: tokenizer / context length / precision / device map の差異を吸収できる
- [ ] **BC-01**: ContainerSpec YAML を読み込んで sub-block を順序実行できる
- [ ] **BC-02**: 5 種類以上の sub-block (`pre_norm`, `causal_attention` or `gqa`, `memory_read`, `ffn_swiglu`, `memory_write`) を持つ
- [ ] **BC-03**: ContainerSpec / SubBlockSpec / CandidateDiff の JSON Schema 検証が走る
- [ ] **MEM-01**: semantic memory (vector search) を read/write できる
- [ ] **MEM-02**: episodic memory (時系列) を read/write できる
- [ ] **MEM-03**: 全 write に provenance を必須付与する
- [ ] **RTR-01**: rule-based router で 2 経路以上の選択ができる
- [ ] **RTR-02**: router の判断理由を explanation log として出力できる
- [ ] **EVO-01**: CandidateDiff を読み込んで A/B ベンチ評価が走る
- [ ] **EVO-02**: ChangeOp の apply / invert が機械的に実行できる
- [ ] **OBS-01**: route trace と memory link を JSON で出力できる
- [ ] **TRIZ-01**: 40 原理 + 39×39 マトリクス + 39+11 特性 を内蔵リソースとして読込可能

#### Phase 2 (Adaptive Modular)

- [ ] **MEM-04**: structural memory (graph) を read/write できる
- [ ] **MEM-05**: parameter memory (adapter store) を管理できる
- [ ] **MEM-06**: surprise score を Bayesian (mean+variance) として扱う
- [ ] **MEM-07**: episodic → semantic への consolidation サイクルが走る
- [ ] **MEM-08**: episodic → semantic → archive → erase の phase transition が動作
- [ ] **BC-04**: adapter / lora_switch sub-block が動作する
- [ ] **OBS-02**: llove TUI で route trace と memory link を可視化できる
- [ ] **OBS-03**: forgetting score (BWT) を計測してダッシュボード表示

#### Phase 3 (Controlled Self-Evolution)

- [ ] **EVO-03**: AI による candidate diff の自動生成 (mutation policy: llm_generated / template / population)
- [ ] **EVO-04**: Lean / Z3 / TLA+ による candidate 不変量検証 (Static Verifier) が動作
- [ ] **EVO-05**: INT8 / 4bit shadow evaluation が動作
- [ ] **EVO-06**: failed candidate を `candidate_episodic_memory` に保存して mutation 学習に利用
- [ ] **EVO-07**: Reverse-Evolution Monitor で forgetting 悪化方向を自動 rollback
- [ ] **TRIZ-02**: Contradiction Detector がメトリクスから矛盾ペアを自動抽出
- [ ] **TRIZ-03**: TRIZ Principle Mapper が矛盾 → 40 原理を引ける
- [ ] **TRIZ-04**: RAD-Backed Idea Generator が CandidateDiff を生成
- [ ] **TRIZ-05**: 9-Window System Operator が時間軸 × 階層軸の発想を生成
- [ ] **TRIZ-06**: ARIZ Pipeline が 9 ステップを自動実行

#### Phase 4 (Multimodal / Production PoC)

- [ ] **SEC-01**: Quarantined Memory Zone の cross-zone access が署名検証必須で動作
- [ ] **SEC-02**: Signed Adapter Marketplace (Ed25519 + SBOM) が動作
- [ ] **SEC-03**: 監査ログを append-only sqlite + SHA-256 chain で保持
- [ ] **INT-01**: llmesh sensor stream (MQTT/OPC-UA) を episodic memory に直接書込
- [ ] **INT-02**: llmesh の MTEngine / XbarRChart / CUSUM で memory access SPC モニタ
- [ ] **INT-03**: llove F16 マルチゲームアリーナで candidate vs candidate 対局
- [ ] **EVO-08**: 30 日連続稼働で人手介入ゼロの自律 promote サイクル

### Out of Scope

- **基盤モデル本体の大規模事前学習** — 既存 LLM 利用前提、コアモデル再学習はやらない
- **大規模 GPU クラスタスケジューラ独自開発** — llmesh + 外部 (k8s / Ray) で代替
- **完全自律な本番構造変更** — promote は必ず HITL or 形式検証 gate を経由
- **マルチモーダル LLM 自前学習** — encoder bridge で外部モデル接続のみ
- **Mobile / Web UI 単独実装** — llove TUI で代替、別 UI は v2+ 検討

## Context

### 既存資産（Phase 0 で完了）

| カテゴリ | 場所 | 内容 |
|---|---|---|
| 要件定義 v0.1〜v0.3 | `docs/requirements_v0.[123]*.md` | 受領原文 + TRIZ + 設計パターン + TRIZ 内蔵 |
| 設計文書 | `docs/architecture.md` 他 12 ファイル | 8 層 + Mermaid + JSON Schema + メトリクス + セキュリティ + テスト + ロードマップ + 用語集 + 統合 |
| 公開 LLM ひな形 | `specs/templates/` | Qwen2.5-7B / Llama-3.1-8B / Mistral-7B-v0.3 / Phi-3.5-mini |
| 標準 SubBlockSpec | `specs/subblocks/` | common / attention / ffn / llive_extensions |
| TRIZ リソース | `specs/resources/` | 40 原理 / 矛盾マトリクス / 39+11 特性 |
| 検証スクリプト | `scripts/inspect_hf_model.py` | テンプレート vs HF config 整合性検証 |

### ファミリー位置

- **[llmesh](https://github.com/furuse-kazufumi/llmesh)** v1.5.0 — マルチプロトコル LLM ゲートウェイ、産業 IoT
- **[llove](https://github.com/furuse-kazufumi/llove)** v0.6.x — TUI dashboard、可視化
- **[llmesh-suite](https://github.com/furuse-kazufumi/llmesh-suite)** v0.1.0 — メタパッケージ
- **llive** v0.0.1 — 本リポジトリ（自己進化型 LLM 基盤）

### 既存類似研究との位置づけ

| 類似系 | 重なり | llive の差別化 |
|---|---|---|
| MemGPT / LongMem | 階層メモリ | 4 層分離 + phase transition + 署名 zone |
| AutoML-Zero / NAS-LLM | 構造探索 | 形式検証 gate + multi-precision shadow + 失敗データ化 |
| Self-Refine / Reflexion | 自己批評 | online/offline 分離 + llove TUI HITL |
| MERA / ModularLLM | モジュラー化 | 可変長 BlockContainer YAML + plugin registry |
| AutoGPT 系 | エージェント | llmesh 産業 IoT 直結 + llove TUI |
| TRIZ × AI 学術提案 | 概念レベル | **動作する実装 + 産業 IoT 連携** |

総合命題: **「生物学的記憶モデル × 形式検証 × 産業 IoT メッシュ × TUI HITL × TRIZ 内蔵」** の 5 軸交差点。

## Constraints

- **Tech stack**: Python 3.11.x — pyproject.toml で `>=3.11,<3.12` を pin (memory `project_python_311_unification.md`)
- **Storage**: D ドライブ運用 — `D:/projects/llive/` (memory `feedback_d_drive_preference.md`)
- **Hardware**: 開発時は 1 GPU 想定 (Phi-3.5-mini / Qwen2.5-0.5B でテスト)、本番候補は 7B〜8B
- **Dependencies**: 外部 LLM SDK は HuggingFace transformers を初期対象、将来 vLLM / TGI
- **Compatibility**: raptor の RAD コーパス (`C:/Users/puruy/raptor/.claude/skills/corpus/`) を `RAPTOR_CORPUS_DIR` 経由参照
- **Family compatibility**: llmesh / llove と API 互換性を維持、llmesh-suite メタパッケージへ Phase 4 完了時に追加
- **Licensing**: MIT（既存ファミリーに揃える）
- **Safety**: production 構造変更は必ず HITL or 形式検証経由、自律暴走禁止

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| プロジェクト名 `llive` | PyPI / GitHub クリア確認済、llmesh / llove と命名規則完全一致 | ✓ 確定 |
| PyPI 名 `llmesh-llive` | `llmesh-llove` パターン踏襲 | ✓ 確定 |
| Python 3.11.x 固定 | memory `project_python_311_unification.md` 方針 | ✓ 確定 |
| D ドライブ運用 | memory `feedback_d_drive_preference.md` | ✓ 確定 |
| 8 層アーキテクチャ | llmesh I/O 層 + llove HITL 層を独立化 (v0.2) | ✓ Phase 1 で正式採用 |
| TRIZ 内蔵 (FR-23〜27) | llive 自身の発想力を内蔵化 (v0.3) | — Phase 3 で実装 |
| 公開 LLM ひな形 4 種 | Phase 1 MVR の出発点 | ✓ specs/templates/ で確保 |
| 既存 docs 維持 | v0.1〜v0.3 累積、`.planning/` とは別管理 | — 並走運用 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-13 after initialization*
