# llive 進捗ログ

> 「いま何が出来て、次に何をやるか」を CHANGELOG.md より一段カジュアルな
> 粒度で残すファイル。CHANGELOG.md は SemVer リリース単位、こちらはセッ
> ション単位の作業ログ。

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

### State (現在地)

- **Phase A 完了**: `data/rad/` 配下に 49 分野コピー済、`_index.json` 生成済
- Phase B 着手前: `src/llive/memory/rad/` モジュール追加が次
- Phase C-2 着手前: MCP server (`src/llive/mcp/server.py`)、VLM/コーディング tool 設計

### 次

- **Phase B**: `RadCorpusIndex` (loader/query/skills/append + provenance.json) + `semantic.py` / `consolidation.py` 接続 + `tests/unit/test_rad_*.py`
- **Phase C-2**: MCP server で `query_rad` / `recall_memory` / `append_learning` を tool 化
- **C-1 (並行)**: LLM backend abstraction (OpenAI / Anthropic / Ollama / llama-cpp) + VLM (LLaVA/Qwen2.5-VL/Phi-3.5-vision) + coding LLM
- corpus2skill 階層スキル (`.claude/skills/corpus/<name>/`) の自動検出を `skills.py` で実装、INDEX.md があれば優先

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
