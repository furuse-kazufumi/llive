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

- **v0.3.0** (2026-05-14) — Phase 3 (Controlled Self-Evolution MVR) + Phase 4 (Production Security MVR) 同時リリース。Z3 静的検証 / Failed Reservoir / Reverse-Evo Monitor / TRIZ Self-Reflection / Wiki ChangeOp / Quarantined Zone / Ed25519 Signed Adapter / SHA-256 Audit Chain。429 tests / 98% coverage / 0 lint。
- **v0.2.0** (2026-05-13) — Phase 2: Adaptive Modular System 完了。4 層メモリ + surprise-gated write + consolidation cycle + LLM Wiki 統合 + 並行パイプライン。308 tests / 99% coverage / 0 lint warnings。
- **v0.1.1** (2026-05-13) — Phase 1: Minimal Viable Research Platform。PyPI 初回公開。
- **次** — Phase 5+ Rust 高速化 (要件 v0.7 定義済、`Phase 4 完了 + EVO 安定後の措置`原則で段階着手)。

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
- [ロードマップ](docs/roadmap.md)
- [変更履歴](CHANGELOG.md)

## ファミリー

- **[llmesh](https://github.com/furuse-kazufumi/llmesh)** — マルチプロトコル LLM ゲートウェイ、産業 IoT 対応
- **[llove](https://github.com/furuse-kazufumi/llove)** — TUI dashboard、可視化と HITL
- **[llmesh-suite](https://github.com/furuse-kazufumi/llmesh-suite)** — llmesh + llove のメタパッケージ
- **llive** — 自己進化型モジュラー記憶 LLM 基盤（本リポジトリ）

## ライセンス

MIT
