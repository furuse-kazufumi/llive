# llive 進捗ログ

> 「いま何が出来て、次に何をやるか」を CHANGELOG.md より一段カジュアルな
> 粒度で残すファイル。CHANGELOG.md は SemVer リリース単位、こちらはセッ
> ション単位の作業ログ。

---

## 2026-05-15 (続き) — TRIZ ベース demo パッケージ + 技術資料

### Why (背景)

RAD 横断エピックの C 層まで揃ったので、**動くデモ**で「llive はどう使うのか」
を 30 秒で伝えられるようにする。memory `project_f25_demo_polish` の教訓
(動きで魅せる / 繰り返し再生 / セルフサービス / 多言語) と
`feedback_scenario_iterative` (smoke だけで OK にせず 1 個ずつ磨く) を
TRIZ 発明原理に重ねて設計。

### What (作業)

- `src/llive/demo/` パッケージ新規 (5 scenario + i18n + runner + CLI、~800 行):
  - Scenario 1: RAD 読み API クイックツアー (filename vs content score 差を提示)
  - Scenario 2: append_learning round-trip (書いた直後に検索可)
  - Scenario 3: code_review with RAD hint injection (security_corpus_v2 grounding)
  - Scenario 4: MCP server 実 client 経由の round-trip (Claude Desktop 同等経路)
  - Scenario 5: OpenAI HTTP server で RAG on/off 差分 (Ollama 直結経路)
- `src/llive/demo/runner.py`: Scenario 基底 + ScenarioContext + _scoped_lang
  + run_one/run_all + CLI (--only / --list / --lang / --quiet / --keep-artifacts)
- `src/llive/demo/i18n.py`: 軽量 i18n (gettext 不使用、純 dict、ja/en)
- `src/llive/mcp/server.py`: LLIVE_MCP_LOG_LEVEL env で server-side INFO 抑制
- `docs/v0.2_rad_techdoc.html`: 単一 HTML 技術資料 (Mermaid 図 / TOC /
  ダーク対応 / 学習要点 10 項目) — 学習用に self-contained
- `docs/demos.html`: 5 scenario の showcase ポータル (コピーボタン、言語切替、
  expand/collapse、Esc で畳む)
- 各 scenario を 1 個ずつ実機確認しながら磨いた:
  - step counter の 1/3→2/3→3/3 進行を担保
  - ヒントパスを file name のみに短縮
  - MCP server の INFO ログ抑制
  - i18n env が _scoped_lang で前後復元される

### State (現在地)

- ✓ デモは `py -3.11 -m llive.demo` で 1 コマンド再生、ja/en 両対応
- ✓ 各 scenario は mock backend で完結、ネットワーク不要
- 540 tests / 全 PASS / ruff clean (527 → +13 demo tests)
- コミット: ad011dc (demo + techdoc HTML + showcase)

### 次

- README にデモへのリンクを 1 行追加
- Scenario 6: VLM (画像入力で動く差別化機能を見せる)
- Scenario 7: consolidation → RAD mirror の生物学的記憶モデル目玉
- 多言語拡張 (zh/ko)、`--loop` で繰り返し再生

---

## 2026-05-15 — v0.2.0 系着手: RAD コーパス取り込み (Phase A)

### Why (背景)

Raptor が育てた RAD (Research Aggregation Directory、49 分野・44,864 docs・~112 MB) を
llive **配下に物理コピー**して、llive 単独で完結する「独立した知識庫」として使えるようにする。
さらに Phase B で生物学的記憶モデル (semantic → consolidation) から RAD に**書き戻し可能**にし、
Phase C-2 で MCP server 化することで Ollama / LM Studio / Claude Desktop / Open WebUI から
呼び出せる外部 LLM 連携を実現する。VLM とコーディング特化 LLM もサポート予定。

### What (Phase A 作業)

- `scripts/import_rad.py` 新規 (stdlib のみ、~250 行)
  - 引数: `--source` / `--dest` / `--corpora` / `--all` / `--include-legacy` / `--mirror` / `--dry-run` / `--force`
  - スマート判定既定: `<分野>_v2/` を優先、無い分野は v1 を採用 (`tui_corpus`, `security_papers_2025_2026` 等)
  - サイズ + mtime ベースの差分判定 (高速、`--force` で全再コピー)
  - `_index.json` 生成 (分野・ファイル数・バイト数・取り込み日時)
  - `_learned/` 書き層を予約 (README 付き、Phase B で `RadCorpusIndex.append_learning` が使う)
- `.gitignore` に `data/rad/` 追加 (`!data/rad/README.md` で説明のみ追跡)
- `data/rad/README.md` 新規 (レイアウト・取り込み手順・環境変数解決順を説明)
- Dry-run で 49 分野 / 44,864 files / 112.1 MB を確認後、本番取り込み実行

### What (Phase B / C-1 / C-2 / C-1.1 / C-2.1 を同セッションで完了)

- **Phase B (知識庫 API)** — `src/llive/memory/rad/`:
  loader / query / append / skills / types。`RadCorpusIndex` に
  読み + 書き API を統合、path traversal 防御、corpus2skill 階層スキル検出。
  Consolidator (`rad_index=...`) で ConceptPage を `_learned/<page_type>/`
  へミラー、provenance に `derived_from=[event_ids]` で LLW-AC-01 維持。
- **Phase C-1 (LLM backend abstraction)** — `src/llive/llm/`:
  Mock / Anthropic / OpenAI / Ollama の 4 backend、`GenerateRequest` /
  `GenerateResponse` 統一。resolve_backend() で env 自動解決
  (`LLIVE_LLM_BACKEND` > `ANTHROPIC_API_KEY` > `OPENAI_API_KEY` > `OLLAMA_HOST` > mock)。
- **Phase C-1.1 (VLM 拡張)** — `GenerateRequest.images: list[bytes | Path | str]`、
  `_normalise_image()` で magic bytes / 拡張子 / base64 を判別。
  Ollama (top-level images)、Anthropic (image blocks)、OpenAI (data:URI image_url)
  すべての backend に画像経路を実装。
- **Phase C-2 (MCP server)** — `src/llive/mcp/`:
  tools.py (transport 非依存) + server.py (公式 mcp 1.0+ stdio)。
  5 基本 tool: `list_rad_domains` / `get_domain_info` / `query_rad` /
  `read_document` / `append_learning`。スモークテストで実際の mcp
  client から spawn → initialize → list_tools → call_tool round-trip 検証。
- **Phase C-2.1 (vlm / coding MCP tool)** — `tool_vlm_describe_image`
  (画像 + optional `domain_hint` で RAD grounding)、`tool_code_complete`
  (temperature=0.0)、`tool_code_review` (`security_corpus_v2` から top-N
  ヒント注入で Cursor / Continue.dev / Claude Desktop からセキュリティ
  レビュー)。
- **ドキュメント**: ROADMAP に「RAD 横断エピック」(SemVer 衝突解消)、
  CHANGELOG [Unreleased]、`docs/mcp_integration.md` (Claude Desktop /
  LM Studio / Open WebUI / Cursor / Continue.dev 設定例) を追加。

### State (現在地)

- ✓ RAD-A 取り込み層: 49 分野 / 44,864 docs / 112.1 MB コピー済
- ✓ RAD-B 知識庫 API + Consolidator 統合
- ✓ RAD-C-1 LLM backend (text + VLM 拡張)
- ✓ RAD-C-2 MCP server + smoke E2E (mcp 1.0+ stdio で 5 tool 動作確認)
- ✓ RAD-C-2.1 vlm / coding tool (3 追加 = 計 8 tool)
- **441 → 518 tests / 全 PASS / ruff clean**
- コミット: a75ccd4 / 28107dd / d9c23ff / 1b2022f

### 次

- RAD-C-3: OpenAI 互換 HTTP server (Ollama から llive を直接呼べる経路)
- RAD-C-1.2: コーディング特化モデル明示サポート (DeepSeek-Coder / Qwen2.5-Coder
  の prompt template 整備)
- 拡張 tool: `recall_memory` (semantic memory + encoder 接続が必要)
- 実機検証: Claude Desktop に MCP 設定を入れて `query_rad` / `code_review`
  を実呼び出し

---

## 2026-05-14 (続き) — pyo3 0.24.2 (CVE-clean) + 全 441 tests PASS

### Why (背景)

RAPTOR `/sca` (OSV) の横断スキャンで pyo3 0.22 に 4 件の CVE が検出された:

| アドバイザリ | 内容 | 修正版 |
|---|---|---|
| RUSTSEC-2024-0378 / GHSA-6jgw-rgmm-7cv6 | use-after-free in `borrowed` weakref reads | 0.22.4 |
| RUSTSEC-2025-0020 / GHSA-pph8-gcv7-4qj5 | buffer overflow in `PyString::from_object` | 0.24.1 |

両方を解決する **最小ジャンプ = 0.24.2** へ昇格。

### What (作業)

- `crates/llive_rust_ext/Cargo.toml`: `pyo3 = "0.22"` → `pyo3 = "0.24.2"`
  (バージョンを patch まで明示しないと SCA OSV 路で `"0.24"` が 0.24.0 と
   解釈され RUSTSEC-2025-0020 が残ったままになる)
- `cargo build --release` (Python 3.11、abi3-py311 経由) ― API breaking ゼロ、
  warning ゼロ、29.99 秒で完了
- `tests/property/test_rust_python_parity.py` ― **15/15 PASS** (1e-6 parity
  維持、Hypothesis 50 ケース × 2 関数 + 各種境界条件)
- `tests/` 全体 ― **441/441 PASS** (z3-solver install 後)
- README.md `## ステータス` セクションに v0.4.0 + v0.5.0 + [Unreleased] 追記

### State (現在地)

- **v0.5.0** (Phase 5 first wire-in, Rust kernel ホットパス wire-in)
- **441 tests / 0 lint** (verifier 11/11 + property 15/15 + その他 415)
- pyo3 0.24.2 (4 CVE 解決、SCA で 0 vulnerable packages 確認済)
- [Unreleased]: F25 (g) `LoveBridge` writer (16 tests 追加済、commit 待ち)

### 環境メモ

- **Python 3.11** (`C:/Users/puruy/AppData/Local/Programs/Python/Python311/python.exe`)
  での運用が安定。memory `[[project_python_311_unification]]` 方針通り。
- MSYS2 の Python 3.14 で cargo build すると pyo3 0.24 が「Python 3.13 まで」
  と拒否する (3.14 サポートは pyo3 0.25.0+)。`PYO3_PYTHON` 環境変数で 3.11
  を明示するのが正解。
- `pip install z3-solver` を Python 3.11 にも入れた (verifier テストの依存)。

### 次

- Phase 5 残: RUST-02 完全並列化 (rayon)、RUST-05 (jsonschema-rs)、RUST-06
  (crossbeam audit sink)、RUST-07 (ChangeOp 移植)、RUST-08 (hora/arroy HNSW)、
  RUST-09 (tokio async)、RUST-10 (phf TRIZ matrix)、RUST-11 (Z3 bridge)
- F25 Phase h: E2E 統合検証 (3 リポジトリ同時起動 ― 実機検証必要)
- pyo3 0.25+ への将来昇格 (Python 3.14 サポートが必要になったとき)
