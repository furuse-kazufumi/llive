# llive

> **Part of the [FullSense ™](TRADEMARK.md) family** — `llmesh` (secure LLM hub) ・ **llive** (self-evolving memory) ・ `llove` (TUI dashboard) の 3 製品を束ねる FullSense ブランドの中で、自己進化型モジュラー記憶 LLM 基盤を担当するパッケージです。FullSense Spec v1.1 をリファレンス実装します。

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

### 素の OSS LLM (Qwen / Llama / Mistral / ...) に対する位置づけ

llive にとって OSS LLM weights は **競合ではなく内側で呼ぶ素材**。Brief API
(LLIVE-002, 2026-05-16) でどの OSS LLM も `LLMBackend` として透過的に差し替え
可能 — 差別化はモデル単体ではなく、その上に乗る **フレームワーク層** にある。

| 層 | 素の OSS LLM (Qwen / Llama / Mistral / ...) | llive (それを内包する) | 実装状況 |
|---|---|---|---|
| **推論コア** | Decoder-only LLM 重み | OSS LLM を `LLMBackend` として呼び出す | 実装済 (Ollama / OpenAI / Anthropic / Mock) |
| **記憶** | 単一 context window | 4 層 (semantic / episodic / structural / parameter) + 海馬-皮質 consolidation (FR-12) | semantic/episodic 実装済 |
| **意思決定** | 1 ターン生成 | FullSense 6 stage loop (salience → curiosity → thought → ego/altruism → plan → output) | 実装済 |
| **入力契約** | プロンプト 1 本 | **Brief API** ― 構造化 work unit + constraints + success_criteria + tool whitelist | 実装済 (2026-05-16) |
| **安全** | プロンプトレベル | Approval Bus + Policy + Quarantined Memory (SEC-01) + Ed25519 Signed Adapter (SEC-02) | 実装済 |
| **監査** | なし | append-only SIL ledger (Brief / Approval) + SHA-256 hash chain (SEC-03) | 実装済 |
| **自己進化** | 事前学習 + ファインチューニングのみ | オンライン提案 → Z3 形式検証 (EVO-04) → 審査 → 昇格 (EVO-06/07) | Phase 3 完了 |
| **アイデア源** | なし | TRIZ 40 原理 + 39×39 矛盾マトリクス内蔵 (FR-23〜27) | 実装済 |
| **HITL** | なし | llove TUI Candidate Arena (FR-20) | 設計済、未統合 |
| **産業 IoT** | なし | llmesh MQTT / OPC-UA sensor bridge (FR-19) | 設計済、未統合 |

実測 (2026-05-16 progressive validation matrix, xs/s/m × {llama3.2:3b,
qwen2.5:7b, qwen2.5:14b}, on-prem only): **Brief API + loop overhead < 1 %**
(LLM-only wall time / Total wall time > 99.8 %)。詳細は
[`docs/benchmarks/2026-05-16-progressive-merged/summary.md`](docs/benchmarks/2026-05-16-progressive-merged/summary.md)。

同点と認める領域: **生成品質そのもの** (内蔵 OSS LLM に依存) / **on-prem 実行**
(OSS LLM 直叩きでも成立) / **多言語** (素のモデルでも対応)。

## ステータス

- **v0.5.0** (2026-05-14) — Phase 5 first wire-in。`BayesianSurpriseGate.compute_surprise` (MEM-07) と `EdgeWeightUpdater.apply_time_decay` (RUST-03) を Rust kernel 経路へ自動委譲、不在時 numpy fallback、1e-6 parity 保証。**444 tests / 0 lint** (v0.4.0 baseline 439 + RUST-03 parity 5)。pyo3 0.24.2 (CVE-clean)。
- **v0.4.0** (2026-05-14) — Phase 5 Rust acceleration **skeleton**。`crates/llive_rust_ext/` PyO3 0.22 + maturin scaffold、RUST-01 / RUST-02 baseline (`compute_surprise`) / RUST-04 baseline (`jaccard`) / RUST-13 Hypothesis parity harness。**439 tests**。
- **v0.3.0** (2026-05-14) — Phase 3 (Controlled Self-Evolution MVR) + Phase 4 (Production Security MVR) 同時リリース。Z3 静的検証 / Failed Reservoir / Reverse-Evo Monitor / TRIZ Self-Reflection / Wiki ChangeOp / Quarantined Zone / Ed25519 Signed Adapter / SHA-256 Audit Chain。429 tests / 98% coverage / 0 lint。
- **v0.2.0** (2026-05-13) — Phase 2: Adaptive Modular System 完了。4 層メモリ + surprise-gated write + consolidation cycle + LLM Wiki 統合 + 並行パイプライン。308 tests / 99% coverage / 0 lint warnings。
- **v0.1.1** (2026-05-13) — Phase 1: Minimal Viable Research Platform。PyPI 初回公開。
- **[Unreleased]** — F25 (g) `LoveBridge` writer (llive ↔ llmesh ↔ llove を MCP 経由で繋ぐ shim)、+16 tests。
- **次** — Phase 5 残 (RUST-02 rayon 並列、RUST-05 jsonschema-rs、RUST-06 crossbeam audit sink、RUST-07 ChangeOp、RUST-08 hora HNSW、RUST-09 tokio async、RUST-10 phf TRIZ、RUST-11 Z3 bridge) を意味論固定後に段階着手。

## デモを 30 秒で試す

**最短コース** (PyPI から install):

```bash
py -3.11 -m pip install llmesh-llive
llive-demo                              # 10 シナリオ全部を順番に再生 (ja)
llive-demo --only resident-cognition    # 自発思考の常駐ループだけ (Scenario 8)
llive-demo --only multi-track           # 5 epistemic track 体験 (Scenario 9)
llive-demo --only deception-filter      # §5.D 7 分類 ALLOW/REJECT 実演 (Scenario 10)
```

**ソースから**:

```bash
git clone https://github.com/furuse-kazufumi/llive.git && cd llive
py -3.11 -m pip install -e .
llive-demo                              # 10 シナリオを順番に再生
llive-demo --lang en                    # 英語ナレーション (ja / en / zh / ko)
llive-demo --only 1                     # 1-based index でも指定可
llive-demo --list                       # シナリオ一覧
llive-demo --loop 3 --interval 1.0      # 繰り返し再生 (TRIZ #19)
llive-demo --json                       # AI agent / CI 用 JSON 出力
```

**spec 準拠の自己申告 (§11.V4 Conformance Manifest)**:

```bash
llive-manifest --summary-only           # holds / violated / undecidable のカウント
llive-manifest                          # 全 clause を JSON で出力
```

### 各シナリオの見どころ (12 件)

| # | id | 説明 |
|---|---|---|
| 1 | `rad-quick-tour` | RAD 読み API クイックツアー (filename vs content score 差) |
| 2 | `append-roundtrip` | `_learned/` への書き込み → 即検索 round-trip |
| 3 | `code-review` | `security_corpus_v2` から top-N ヒント注入で security review |
| 4 | `mcp-roundtrip` | 公式 mcp 1.0+ stdio client で 8 tool round-trip |
| 5 | `openai-http` | Ollama 経路 (RAG on/off 差分) |
| 6 | `vlm-describe` | VLM grounding (1x1 合成 PNG + domain_hint) |
| 7 | `consolidation-mirror` | episodic → cluster → ConceptPage → `_learned/` 自動ミラー (LLW-AC-01) |
| 8 | `resident-cognition` | **A-5**: 自発思考の常駐ループ 30 秒。AWAKE/REST/DREAM phase + TRIZ ひらめき ✨ |
| 9 | `multi-track` | **A-1.5**: 同一 stimulus を 5 epistemic track で通すと答えが変わる |
| 10 | `deception-filter` | **§5.D**: 建前 (D1) ALLOW / 捏造 (D4) REJECT / 自己欺瞞 (D7) §A°2 違反 |
| 11 | `rad-omniscience` | **KAR snapshot**: RAD 横断検索で複数分野から hint を集める「全人類知識吸収」の現時点実演 |
| 12 | `image-algorithm-advisor` | **会社デモ**: 画像 1 枚 → VLM (Mock) + RAD で 3 アルゴリズム比較 + 推奨 + リスク |

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

llive は **dual-license** で提供しています:

  * **オープンソース**: [Apache License 2.0](LICENSE) — 研究 / 個人利用 / OSS 統合 / 評価 / 内部 R&D など大半の用途で十分
  * **商用ライセンス**: [LICENSE-COMMERCIAL](LICENSE-COMMERCIAL) — クローズドソース製品への統合、Apache-2.0 の NOTICE / 表示義務の免除、SLA / サポート / 補償が必要な場合

v0.6.0 で MIT → Apache-2.0 + Commercial の dual-license に切替えました。v0.5.x までは MIT が継続します。

### 寄与

寄与歓迎します。`CONTRIBUTING.md` に DCO sign-off の手順、`SECURITY.md` に脆弱性報告窓口があります。

### 商標

「llive」「llmesh」「llove」は Kazufumi Furuse の商標です。詳細は [TRADEMARK.md](TRADEMARK.md) を参照してください。

### サードパーティ依存

第三者 license の集計は `NOTICE` を参照、より詳細は `pip-licenses --format=markdown` で取得できます。
