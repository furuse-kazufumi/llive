# llive

> **Self-evolving modular memory LLM framework** — 生物学的記憶モデル × 形式検証 × 産業 IoT メッシュ × TUI HITL の交差点で設計された自己進化型 LLM 基盤。

llive は、固定された Decoder-only LLM コアの周辺に、可変長 BlockContainer・4 層外部記憶（semantic / episodic / structural / parameter）・審査付き構造進化を組み合わせることで、コア重みを再学習せず新能力を継続的に取り込める研究開発フレームワークです。

llmesh（マルチプロトコル LLM ゲートウェイ）と llove（TUI dashboard）の両ファミリーと統合運用できることを第一級要件としています。

## 設計の核

1. **固定コア + 可変周辺** — Adapter / LoRA / 外部記憶 / 可変 BlockContainer で能力を吸収
2. **4 層メモリの責務分離** — semantic（知識）/ episodic（経験）/ structural（関係）/ parameter（差分重み）
3. **宣言的構造記述** — sub-block 列を YAML で表現、AI が提案・比較しやすい
4. **審査付き自己進化** — オンラインは memory write と軽微 routing のみ、構造変更はオフライン審査経由
5. **生物学的記憶モデル直接埋め込み** — 海馬-皮質 consolidation cycle、surprise score、phase transition
6. **形式検証付き promotion** — Lean / Z3 / TLA+ による構造的不変量検査を LLM 評価前に挟む
7. **llmesh / llove ファミリー統合** — 産業 IoT センサを直接 episodic memory に、TUI で HITL 完結
8. **TRIZ アイデア出しを内蔵** — 40 原理 + 39×39 矛盾マトリクス + ARIZ + 9 画法を mutation policy として組込み、メトリクスから矛盾を自動検出 → 原理マッピング → RAD 裏付け → CandidateDiff 生成までを自走

## 既存類似研究との位置づけ

| 既存系 | 重なる範囲 | llive の差別化 |
|---|---|---|
| MemGPT / LongMem | 階層メモリ | 4 層分離 + phase transition + 署名 zone |
| AutoML-Zero / NAS-LLM | 構造探索 | 形式検証 gate + multi-precision shadow + 失敗データ化 |
| Self-Refine / Reflexion | 自己批評 | online/offline 分離 + llove TUI HITL staging |
| MERA / ModularLLM | モジュラー化 | 可変長 BlockContainer YAML + plugin registry |
| AutoGPT 系 | エージェント | llmesh 産業 IoT 直結 + llove TUI |

## ステータス

- **v0.5.0** (2026-05-14) — Phase 5 first wire-in。`BayesianSurpriseGate.compute_surprise` (MEM-07) と `EdgeWeightUpdater.apply_time_decay` (RUST-03) を Rust kernel 経路へ自動委譲、不在時 numpy fallback、1e-6 parity 保証。**444 tests / 0 lint** (v0.4.0 baseline 439 + RUST-03 parity 5)。pyo3 0.24.2 (CVE-clean)。
- **v0.4.0** (2026-05-14) — Phase 5 Rust acceleration **skeleton**。`crates/llive_rust_ext/` PyO3 0.22 + maturin scaffold、RUST-01 / RUST-02 baseline (`compute_surprise`) / RUST-04 baseline (`jaccard`) / RUST-13 Hypothesis parity harness。**439 tests**。
- **v0.3.0** (2026-05-14) — Phase 3 (Controlled Self-Evolution MVR) + Phase 4 (Production Security MVR) 同時リリース。Z3 静的検証 / Failed Reservoir / Reverse-Evo Monitor / TRIZ Self-Reflection / Wiki ChangeOp / Quarantined Zone / Ed25519 Signed Adapter / SHA-256 Audit Chain。429 tests / 98% coverage / 0 lint。
- **v0.2.0** (2026-05-13) — Phase 2: Adaptive Modular System 完了。4 層メモリ + surprise-gated write + consolidation cycle + LLM Wiki 統合 + 並行パイプライン。308 tests / 99% coverage / 0 lint warnings。
- **v0.1.1** (2026-05-13) — Phase 1: Minimal Viable Research Platform。PyPI 初回公開。
- **[Unreleased]** — F25 (g) `LoveBridge` writer (llive ↔ llmesh ↔ llove を MCP 経由で繋ぐ shim)、+16 tests。
- **次** — Phase 5 残 (RUST-02 rayon 並列、RUST-05 jsonschema-rs、RUST-06 crossbeam audit sink、RUST-07 ChangeOp、RUST-08 hora HNSW、RUST-09 tokio async、RUST-10 phf TRIZ、RUST-11 Z3 bridge) を意味論固定後に段階着手。

## デモを 30 秒で試す

```bash
git clone https://github.com/furuse-kazufumi/llive.git && cd llive
py -3.11 -m pip install -e .
py -3.11 -m llive.demo                  # 5 シナリオを順番に再生 (ja)
py -3.11 -m llive.demo --lang en        # 英語ナレーション
py -3.11 -m llive.demo --only 3         # コードレビュー単体だけ
py -3.11 -m llive.demo --list           # シナリオ一覧
```

mock backend で完結するので、API キーや実 RAD コーパスは不要。ブラウザで
[`docs/demos.html`](docs/demos.html) を開くと、各シナリオの説明 + コピー可能な
コマンド + 期待出力を見渡せます。技術資料は
[`docs/v0.2_rad_techdoc.html`](docs/v0.2_rad_techdoc.html) (自己完結 HTML、
Mermaid 図 + 学習要点 10 項目)。

**ブラウザデモ**:
[`docs/demos/anatomy/index.html`](docs/demos/anatomy/index.html) — SVG 人体図を
クリックすると架空キャラクター *Dr. Aria* が部位を解説（educational fiction、
medical_corpus_v2 grounding 経由）。バックエンド未起動でも mock fallback で
動作します。実 RAG は `py -3.11 -m llive.server.openai_api` 起動後にリロード。

## インストール

```bash
pip install llmesh-llive            # core (cryptography 同梱、Ed25519 署名・SHA-256 audit 利用可)
pip install llmesh-llive[torch]     # HF transformers + faiss + peft + hdbscan
pip install llmesh-llive[ingest]    # 外部 ingest CLI 用 (pypdf / arxiv / readability)
pip install llmesh-llive[llm]       # AnthropicCompileLLM (consolidation 本番用)
pip install llmesh-llive[verify]    # Z3 SMT 検証レイヤ (EVO-04 Static Verifier)
pip install llmesh-llive[dev]       # 開発依存 (pytest / hypothesis / ruff)
```

## ドキュメント

- [要件定義 v0.1（原型）](docs/requirements_v0.1.md)
- [要件定義 v0.2 追補章（TRIZ + 設計パターン + llmesh/llove 統合）](docs/requirements_v0.2_addendum.md)
- [要件定義 v0.3 (TRIZ 自己進化)](docs/requirements_v0.3_triz_self_evolution.md)
- [要件定義 v0.4 (LLM Wiki integration)](docs/requirements_v0.4_llm_wiki.md)
- [要件定義 v0.5 (spatial memory)](docs/requirements_v0.5_spatial_memory.md)
- [要件定義 v0.6 (concurrency)](docs/requirements_v0.6_concurrency.md)
- [要件定義 v0.7 (Rust acceleration)](docs/requirements_v0.7_rust_acceleration.md)
- [**FullSense Eternal Specification v1.0**](docs/fullsense_spec_eternal.md) — 自律常駐認知の永続要件定義 (substrate independent, millennial invariants, ethical minima, mortality protocol, superhuman scope, differentiation analysis)
- [FullSense 命名リスク調査](docs/fullsense_naming_research.md)
- [ロードマップ](docs/roadmap.md)
- [変更履歴](CHANGELOG.md)

## ファミリー

- **[llmesh](https://github.com/furuse-kazufumi/llmesh)** — マルチプロトコル LLM ゲートウェイ、産業 IoT 対応
- **[llove](https://github.com/furuse-kazufumi/llove)** — TUI dashboard、可視化と HITL
- **[llmesh-suite](https://github.com/furuse-kazufumi/llmesh-suite)** — llmesh + llove のメタパッケージ
- **llive** — 自己進化型モジュラー記憶 LLM 基盤（本リポジトリ）

## ライセンス

MIT
