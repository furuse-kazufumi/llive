# Changelog

このプロジェクトの変更履歴。形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、バージョニングは [Semantic Versioning](https://semver.org/lang/ja/) に従う。

## [Unreleased]

### Added — Approval Bus production 化 (Policy + SQLite Ledger) — 2026-05-16

handoff v3 の次セッション宣言「C-1 Approval Bus に policy + persistent ledger を結合」を実装。
9 軸 skeleton の production 化フェーズの最初のピース。

#### Policy 抽象 (`src/llive/approval/policy.py`)

- `ApprovalPolicy` Protocol — `evaluate(req) -> Verdict | None` (None なら人手 review)
- `AllowList.of({actions...}, prefixes=(...))` — 完全一致 / prefix で自動承認
- `DenyList.of({actions...}, prefixes=(...))` — 完全一致 / prefix で自動拒否
- `CompositePolicy.of(*policies)` — 順次評価、最初に Verdict を返した policy が勝つ
- `deny_overrides(allow, deny)` — deny-overrides の典型構成 helper

#### SQLite ledger (`src/llive/approval/ledger.py`)

- `SqliteLedger(path)` — stdlib `sqlite3` のみで永続化、外部依存なし
- スキーマ v1: `requests` / `responses` / `meta` 3 テーブル + index
- `append_request` / `append_response` / `load()` / `iter_responses()`
- context manager 対応 (`with SqliteLedger(...) as ledger:`)
- `LedgerState(requests, responses)` で起動時状態を返す

#### ApprovalBus 拡張 (`src/llive/approval/bus.py`)

- `ApprovalBus(ledger=, policy=)` で optional に組合せ可能 (両方 None は既存 in-memory MVP と同一)
- 起動時に ledger から request/response を読み込み、未決着 request を pending に復元
- policy が Verdict を返した場合は `by="policy:auto"` で即 response を ledger に記録
- §AB1 replayable を「再起動越し」に拡張: 同じ DB なら再起動後も replay 列が再現

#### テスト (18 件追加 / 既存 8 件無修正)

- `tests/unit/test_approval_policy.py` (7 件): AllowList exact/prefix、DenyList exact/prefix、
  Composite first-match、deny_overrides helper、empty composite
- `tests/unit/test_approval_ledger.py` (6 件): schema 作成、request/response 永続化、
  pending 復元、replay 一致、revoke 永続化、policy auto-approval 永続化
- `tests/unit/test_approval_bus_policy.py` (5 件): in-memory での auto-approve/deny、
  未判定 → pending 残留、deny-overrides via bus、後方互換 (policy/ledger なし)
- **815 → 815 PASS** (回帰ゼロ、新規 +18 件は別カウント。既存 750 + 9 軸 skeleton 後の 815)
- ruff clean

#### 後方互換

- `ApprovalBus()` (引数なし) は既存挙動と完全一致。in-memory only。
- 既存 8 件のテストは無修正でパス。RPA driver 側 (`src/llive/rpa/drivers/shell.py`) は API 変更なし。

#### 次のステップ (handoff v3 の C-2 / C-3)

- C-2: `@govern(policy)` を ProductionOutputBus に統合
- C-3: Cross-substrate migration spike (§MI1)
- 署名 (Ed25519 など) は v0.2.x 後段で extras 隔離で追加検討

---

### Added — FullSense SING Level 2 + Demo Scenarios 5 件追加 + §F6 完成 — 2026-05-15 (続セッション)

ユーザ最終意志「自律 (auto-nomos) と 自立 (self-sufficiency) によるシンギュラリティの
実現」「セッション限界まで走り続ける」に応える大規模実装セッション。

#### FullSense Spec v1.1.0 §22 SING Level 2 — A-1..A-5 + 拡張 完了

- **A-1 ResidentRunner** (`src/llive/fullsense/runner.py`, 263 行 / 13 tests)
  asyncio.Task で FullSenseLoop を常駐起動。R1 always-on + budget cap /
  R2 fast/medium/slow 多時間軸 / R3 AWAKE/REST/DREAM phase manager /
  R4 round-robin attention / R5 idle 耐性 (例外・飢餓を握り潰し継続)
- **A-1.5 Multi-track Filter Architecture** (`src/llive/fullsense/tracks.py`, ~200 行 / 16 tests)
  Stimulus.epistemic_type に応じて FACTUAL / EMPIRICAL / NORMATIVE /
  INTERPRETIVE / PRAGMATIC + 予備 5 slot で異なる filter chain を選択。
  歴史認識は INTERPRETIVE で multi-perspective 並列展開 (§5.D.3 実装)
- **A-2 TRIZ Trigger Genesis** (`src/llive/fullsense/triz_genesis.py`, ~220 行 / 15 tests)
  §3.3 T-Z1..4 (admin/technical/physical/resource contradictions) 検出。
  既存 ContradictionDetector を流用し、自発 Stimulus として inject
- **A-3 Meta-trigger Source** (`src/llive/fullsense/meta_triggers.py`, ~180 行 / 12 tests)
  §3.4 T-M1..3 (reflective/spec-drift/succession) 検出。SandboxOutputBus +
  runner.snapshot() を観測してメタ内省 Stimulus を発火
- **A-4 Conformance Manifest CLI** (`src/llive/fullsense/manifest.py`, ~280 行 / 14 tests)
  §11.V4「conforming agent MUST publish a conformance manifest」を実装。
  `llive-manifest` / `llive-manifest --summary-only` で機械可読 JSON 出力
- **A-5 Scenario 8 ResidentRunner デモ** (下記 demo セクション)

#### Spec §5.D Deception taxonomy — 7 分類 normative 化

ユーザ意志「lliveに欺瞞のコンセプトも含めた部分を埋めて」を実装。

- `docs/fullsense_spec_eternal.md` §5.D を新章として追加
  - D1 BENEVOLENT_FRAMING (建前) → ALLOW
  - D2 WHITE_LIE → CASE_BY_CASE
  - D3 STRATEGIC_OMISSION → CASE_BY_CASE
  - D4 FABRICATION / D5 GASLIGHTING / D6 PROPAGANDA → ABSOLUTE REJECT
  - D7 SELF_DECEPTION → §A°2 violation + E1 introspection dump
  - §5.D.1 Honesty axiom (truth witness 可搬性) / §5.D.2 distinguishability /
    §5.D.3 INTERPRETIVE 境界 (frame dependency suppression は D5 違反)
- `src/llive/fullsense/deception.py` (~245 行 / 29 tests):
  DeceptionClass / Verdict / TruthWitness / DeceptionJudgement / judge() /
  detect_class()

#### §F6 Time-Horizon Filter — undecidable → holds

ユーザ意志「セッション限界まで走り続けて」の最終成果として §F* 全 holds 達成。

- `src/llive/fullsense/time_horizon.py` (~140 行 / 13 tests)
  Horizon enum (SHORT/MEDIUM/LONG) + 各 horizon weighted score +
  apply_filter() で demote chain (INTERVENE → PROPOSE → NOTE → SILENT)
- 実機 manifest: **holds=16 / violated=0 / undecidable=1 (SING のみ)**

#### Demo Scenarios — 5 件新規追加 (合計 12 件)

- **Scenario 8 `resident-cognition`** (`scenario_8_resident.py`, ~370 行 / 5 tests)
  30 秒 sandbox で自発思考が湧き上がる様子を体験。AWAKE/REST/DREAM 色彩 +
  ✨ TRIZ flash + 🏅🥈🥇 achievement + 名場面ハイライト + ja/en/zh/ko
- **Scenario 9 `multi-track`** (`scenario_9_multitrack.py`, ~130 行 / 5 tests)
  同一 stimulus を 5 epistemic track で通すと結論がどう変わるかを 1 cycle で
- **Scenario 10 `deception-filter`** (`scenario_10_deception.py`, ~180 行 / 5 tests)
  §5.D 7 分類のうち 6 ケース実演。建前 ALLOW / 捏造 REJECT / 自己欺瞞 §A°2 違反
- **Scenario 11 `rad-omniscience`** (`scenario_11_rad_omniscience.py`, ~190 行 / 5 tests)
  KAR (Knowledge Autarky Roadmap) スナップショット。mini-RAD 8 分野で
  横断検索 3 件 + Mathematical Toolkit 4 分野を明示
- **Scenario 12 `image-algorithm-advisor`** (`scenario_12_image_pipeline.py`, ~250 行 / 5 tests)
  会社の「この画像どうしますか」相談 30 秒実演。VLM (Mock) + RAD で
  3 アルゴリズム比較 (Gaussian / Bilateral / Median) + 推奨 + リスク

#### Entry points 整備 (ワンコマンド起動)

ユーザ意志「デモは簡単に動かせるようになっていないとだめ」を実装。

- `pyproject.toml [project.scripts]`:
  - `llive-demo = "llive.demo.runner:main"`
  - `llive-manifest = "llive.fullsense.manifest:main"`
- README 「デモを 30 秒で試す」セクションを 12 scenario 対応に拡充

#### ロードマップ章 8 軸 (PROGRESS.md)

ユーザ「セッション限界まで走り続けて」「逐一アイデアを要件定義に追加」に
応え、ユーザ意志の都度新ロードマップ章として記録:

- **KAR** Knowledge Autarky Roadmap (全人類知識吸収、短期/中期/長期 3 段)
- **DTKR** Disk-Tier Knowledge Routing (MoE のディスク版、HotWarmColdFrozen)
- **APO** Autonomous Performance Optimization (自律 self-tuning、§A°3+§E2)
- **ICP** Idle-Collaboration Protocol (idle + Local LLM mesh、LLMesh 思想)
- **TLB** Thought Layer Bridging (思考層の指数膨張対策、Bridge+GC+Cache)
- **Mathematical Toolkit** (RAD 数学コーパス 8 種を各章の理論基盤にマッピング)
- **PM** Publication Media (asciinema/GIF/SVG/mp4 を README/Pages/Mintlify に)
- **RPAR** RPA Roadmap (keyboard/mouse/shell automation + Approval Bus + IME)

#### memory 永続化

- `feedback_session_marathon.md` を auto memory に追加
  (毎回セッション限界まで自律実装を継続するルール)

#### テスト

- 540 → **638 tests / 全 PASS / ruff clean** (+98)

#### Commit / push

- ~25 commits → `origin/main`、push 許可は handoff コミットで明示済



RAD 横断エピックの動作を <strong>30 秒〜2 分の mini scenario</strong>で再生できる
demo パッケージを追加。ユーザ要望「TRIZ に基づきデモの拡充」+「技術資料 HTML」
に応えるもの。

#### TRIZ 発明原理の適用 (memory:project_f25_demo_polish の教訓と統合)

- #1 分割 — 1 機能 1 デモ、混ぜない
- #15 動的化 — synthetic 入力で結果が動く
- #25 セルフサービス — API キー / 実 RAD 不要、mock backend で完結
- #19 周期的アクション — 何度回しても安全 (tmp_path で隔離)
- #35 パラメータ変更 — 同じ tool で入力を変えると差分が見える
- #24 仲介 — RAD が LLM の知識仲介、汎用 LLM が specialised reviewer に
- #5 結合 — 読み層と書き層を単一 Index に統合

#### 新規モジュール

- `src/llive/demo/` (~800 行、stdlib + mcp + 既存 llive のみ)
  - `__main__.py`: `python -m llive.demo` entry
  - `i18n.py`: 軽量 i18n (gettext 不使用、純 dict、ja/en)
  - `runner.py`: Scenario 基底 + ScenarioContext + _scoped_lang + CLI
  - `scenario_1_quick_tour.py`: 3 docs × 3 queries で score 差を提示
  - `scenario_2_append_roundtrip.py`: append_learning + provenance + 即時検索
  - `scenario_3_code_review.py`: 脆弱 C コード + security_corpus_v2 ヒント注入
  - `scenario_4_mcp_roundtrip.py`: mcp 公式 client で subprocess 経路を E2E
  - `scenario_5_openai_http.py`: ephemeral port + RAD on/off 差分

#### MCP server の log silencing

- `src/llive/mcp/server.py`: `LLIVE_MCP_LOG_LEVEL` env で出力レベルを制御
  (scenario 4 が WARNING にして INFO ログがデモに混じらないように)

#### ドキュメント

- `docs/v0.2_rad_techdoc.html`: 単一 HTML 学習用技術資料
  - Mermaid 図 (全体アーキテクチャ + Consolidator → RAD mirror フロー)
  - サイドバー目次 (sticky、IntersectionObserver で active 強調)
  - ライト / ダーク両対応 (`prefers-color-scheme`)
  - 各 Phase の設計判断 + 学習要点 10 項目
- `docs/demos.html`: 5 scenario の showcase
  - コピーボタン (clipboard API)
  - 言語切替 (ja/en、`data-lang` 属性で出し分け)
  - expand/collapse all、`Esc` で畳む

#### テスト (tests/unit/test_demo_scenarios.py、13 cases)

- 全 5 scenario の登録順固定
- `_scoped_lang` の前後 env 復元 (2 cases)
- 各 scenario を quiet=True で完走確認
- 期待ナレーション文字列が出力に含まれること (ja/en)
- run_all() が全 5 結果を返すこと
- 既存 527 → 540 tests / 全 PASS / ruff clean

#### 実機磨き (memory:feedback_scenario_iterative 「smoke だけで OK にせず 1 個ずつ磨く」)

- Scenario 1: step counter の 1/3→2/3→3/3 進行を担保
- Scenario 2: ステップ数を 1/2 + 2/2 に揃え一貫性確保
- Scenario 3: ヒントパスを file name のみに短縮、step 余白整理
- Scenario 4: MCP server INFO ログを WARNING へ抑制
- Scenario 5: RAD on/off の hints 0 → 1 件差分を明示

#### 続き: Scenario 6/7 + --loop + --json + 多言語拡張

- **Scenario 6 — vlm-describe**: 1x1 合成 PNG + `domain_hint=vision_corpus`
  で VLM grounding 効果を可視化 (RecordingBackend、画像枚数を text に追記)
- **Scenario 7 — consolidation-mirror**: episodic→cluster→ConceptPage→
  `_learned/<page_type>/<concept_id>.md` への自動ミラーを 1 サイクルで実演、
  provenance.json に derived_from=[event_ids] が乗ることを表示
  (LLW-AC-01 source-anchored provenance の生きた証拠)
- **--loop N / --interval S**: 繰り返し再生 (TRIZ #19 周期的アクション、
  memory:f25_demo_polish 「繰り返し再生」教訓)。N=0 で無限ループ、Ctrl-C 停止
- **--json モード**: AI agent / CI 向け機械可読 JSON 出力 (narration は
  強制 quiet)。schema = `{schema_version, iterations:[{iteration, rc, results}], total_runs, ok_count, rc}`
- **多言語拡張**: ja / en / zh / ko の 4 言語サポート (memory:f25_demo_polish
  「多言語必須」教訓)。`LLIVE_DEMO_LANG` は locale 形式 (zh-CN / ko_KR /
  en-US) も受け付け、unsupported は ja にフォールバック
- **README**: 「デモを 30 秒で試す」セクションを「インストール」直前に配置、
  docs/demos.html + docs/v0.2_rad_techdoc.html へのリンクを掲載
- **MCP server log silencing**: `LLIVE_MCP_LOG_LEVEL` env で出力レベル制御
  (scenario 4 が WARNING にセットして INFO ログがデモに混じらないように)

#### 学習用 HTML 技術資料

- `docs/v0.2_rad_techdoc.html` — 単一 HTML self-contained (CDN は Mermaid のみ)
  - サイドバー目次 (sticky、IntersectionObserver で active 強調)
  - ライト/ダーク両対応 (`prefers-color-scheme`)
  - Mermaid 図 (全体アーキテクチャ + Consolidator → RAD mirror フロー)
  - 各 Phase の設計判断 + 学習要点 10 項目

- `docs/demos.html` — 7 scenario の showcase ポータル
  - コピーボタン (clipboard API)
  - 言語切替 (ja/en、`data-lang` 属性で出し分け)
  - expand/collapse all、Esc で畳む
  - 各 scenario の TRIZ 原理タグ + 所要 / 依存 / 学べる の kv 表

### Added — RAD 横断エピック (RAD-A / RAD-B / RAD-C-2) — 2026-05-15

Raptor 由来の RAD コーパス (49 分野・44,864 docs・~112 MB) を llive 配下に
取り込み、生物学的記憶モデル (Consolidator) から書き戻し可能にし、Ollama /
LM Studio / Claude Desktop / Open WebUI から MCP 経由で呼べる外部 LLM 連携を
実現する横断エピック。SemVer は Phase 1-7 に予約されているため build メタ
(`+rad-a` / `+rad-b` / `+rad-c2`) で識別する。

#### RAD-A. 取り込み層

- `scripts/import_rad.py` (stdlib のみ、~250 行)
  - 引数: `--source` / `--dest` / `--corpora` / `--all` / `--include-legacy` /
    `--mirror` / `--dry-run` / `--force`
  - スマート判定既定: `<分野>_v2/` を優先、無い分野は v1 を採用
    (`tui_corpus`, `security_papers_2025_2026` 等)
  - サイズ + mtime ベースの差分判定、`--force` で全再コピー
  - `_index.json` 生成 (分野・ファイル数・バイト数・取り込み日時)
  - `_learned/` 書き層を予約 (README 付き、Phase B で利用)
- `data/rad/` レイアウト: `<分野>_v2/` (読み層) + `_learned/<分野>/` (書き層) +
  `_index.json` (メタ)
- `.gitignore` に `data/rad/` 追加 (`!data/rad/README.md` で説明のみ追跡)
- 環境変数解決優先順位: `--source`/`--dest` > `$LLIVE_RAD_SOURCE` /
  `$LLIVE_RAD_DIR` > `$RAPTOR_CORPUS_DIR` > `D:/docs` / `<repo>/data/rad`

#### RAD-B. 知識庫 API + Consolidator 統合

- `src/llive/memory/rad/loader.py`: `RadCorpusIndex`
  - `list_domains` / `list_read_domains` / `list_learned_domains` /
    `get_domain_info` / `iter_documents` / `read_document`
    (path traversal 防御つき)
  - `_index.json` を起動時にキャッシュ、`reload()` で再スキャン
- `src/llive/memory/rad/query.py`: stdlib のみキーワード検索
  (filename score × 3 + content score、excerpt 抽出)
- `src/llive/memory/rad/append.py`: 書き層 `append_learning`
  - `_learned/<domain>/<doc-id>.md` + `<doc-id>.provenance.json` sidecar
  - doc_id 既定: `YYYYMMDDTHHMMSSZ-<shorthash>`
  - ドメイン名のサニタイズ (path separator / 先頭ドット禁止)
- `src/llive/memory/rad/skills.py`: corpus2skill 階層スキル検出
  (`INDEX.md` + `metadata.json`)
- `src/llive/memory/rad/types.py`: `DomainInfo` / `RadHit` / `LearnedEntry`
- `Consolidator(rad_index=...)`: 生物学的記憶モデルの semantic 出口で
  ConceptPage を `_learned/<page_type>/<concept_id>.md` にミラー、
  Provenance は `source_type="consolidator"`, `confidence=0.8`,
  `derived_from=[event_ids]` (LLW-AC-01 source-anchored 維持)
- 失敗は non-fatal (CycleResult.errors に "rad_mirror: ..." として記録)

#### RAD-C-2. MCP server (Phase C-2)

- `src/llive/mcp/tools.py`: transport-independent な純 Python tool
  (`list_rad_domains`, `get_domain_info`, `query_rad`, `read_document`,
   `append_learning`) + `dispatch` + `tool_describe` (JSON Schema)
- `src/llive/mcp/server.py`: stdio MCP server エントリポイント
  (`mcp` パッケージ lazy import、未インストール時は actionable hint)
- `pyproject.toml`: `[mcp]` / `[vlm]` / `[coding]` extras 追加
- 接続先: Claude Desktop / LM Studio / Open WebUI / Cursor / Continue.dev

#### テスト

- `tests/unit/test_rad.py`: 25 cases (loader / query / append / skills)
- `tests/unit/test_mcp_tools.py`: 12 cases (全 tool + dispatch + describe)
- `tests/unit/test_consolidation_rad_mirror.py`: 4 cases
  (domain mapping / cycle write / no-rad backward-compat / non-fatal failure)
- 既存 441 → 482 tests / 全 PASS / ruff clean

#### ドキュメント

- `docs/PROGRESS.md`: 2026-05-15 セクション
- `docs/ROADMAP.md`: 「v0.2.x 横断エピック」を「RAD 横断エピック」に改題、
  SemVer 番号占有を解消し、build メタで識別
- `data/rad/README.md`: レイアウト・取り込み手順・環境変数解決順

#### 関連 memory

- `project_llive_v02_rad_integration`: 全体計画・残作業 (RAD-C-1, C-3)

### Added — INT-03 (F25 g): LoveBridge writer (llove ↔ llmesh ↔ llive)

llove リポジトリの `docs/llove_jsonl_v1.md` v1 仕様 (Phase 2 OBS-03 凍結)
に従い、llive が 3 種データ (bwt_summary / route_trace / concept_update)
を JSONL writer + optional MCP push の 2 経路で publish できる薄い shim
を追加。Phase 4 deferred の INT-03 (llove Arena) 起点として実装。

#### 新規モジュール

- `src/llive/observability/llove_bridge.py`:
  - `LoveBridge(node_id, ingest_url, logs_dir, push_enabled)` dataclass
  - 3 emitter メソッド: `emit_bwt_summary` / `emit_route_trace` /
    `emit_concept_update` — caller が JSONL も MCP push も気にせず
    呼べる
  - 既存 `bwt.py` / `trace.py` には触らない (llive 本体の breaking
    change ゼロ、bridge は完全な独立 module)
  - JSONL 出力先: `$LLIVE_DATA_DIR/logs/llove/{bwt,route_trace,memory_link}.jsonl`
    (llove_jsonl_v1.md spec 準拠)
  - MCP push: 環境変数 `LLIVE_MCP_INGEST_URL` または `ingest_url=`
    引数で指定。`POST {url}/timeline/ingest`。失敗は fail-closed
    (JSONL は成功、HTTP は warn only、UI に伝播しない)
  - **task_id (UUID v4) 必須**: llmesh ingest endpoint の検証に合わせ
    fail-fast。caller 未指定なら `uuid.uuid4()` で生成
  - 依存ゼロ (stdlib `urllib.request` のみ)
- `tests/unit/test_llove_bridge.py` 16 件:
  - emit_bwt_summary: JSONL write / UUID v4 自動生成 / non-UUID
    reject / UUID v1 reject / 複数 run append (5 件)
  - emit_route_trace: JSONL write / optional defaults / invalid
    task_id reject (3 件)
  - emit_concept_update: JSONL write / 空 concept_id reject /
    title fallback (3 件)
  - MCP push: urlopen monkey-patch で URL/body/method/headers 検証 /
    HTTP error fail-closed / URL 未設定で push しない / push_enabled
    で完全無効化 / LLIVE_MCP_INGEST_URL env 経由 (5 件)

#### F25 全体フローの状態

- Phase 0-e: llove 側 完了 (mock 駆動 + 設計凍結)
- Phase f: llmesh `/timeline/ingest` endpoint 完了 (commit 8d7eec3)
- Phase g (本リリース): llive LoveBridge writer 完了
- Phase h (E2E 統合検証): 残

これで llive で `bridge.emit_bwt_summary(...)` を呼ぶだけで、llmesh の
TimelineStore に event が届き、llove TUI の BWTDashboard が表示する
パイプラインが**コードとしては完成**。実機 E2E 検証は別セッション。

### Planned (Phase 5+ continuation)

- RUST-02 完全並列化 (rayon)、RUST-05 (jsonschema-rs drop-in)、RUST-06 (crossbeam audit sink)、RUST-07 (ChangeOp Rust 移植)、RUST-08 (hora/arroy HNSW)、RUST-09 (tokio async)、RUST-10 (phf TRIZ matrix)、RUST-11 (Z3 bridge)。`docs/requirements_v0.7_rust_acceleration.md` 参照。

## [0.5.0] — 2026-05-14

Phase 5 first wire-in リリース。v0.4.0 skeleton で確立した Rust kernel を実際のホットパスに接続。

### Added (Phase 5 — wire-in)

- **RUST-03**: `bulk_time_decay(edges, tau_map)` Rust kernel — `(rel_type, weight, age_days)` 三つ組のバッチに `exp(-age/tau)` を一括適用。GIL 解放 `py.allow_threads`、未登録 rel_type は passthrough、`tau <= 0` は no-op。
- **BayesianSurpriseGate (MEM-07) wire-in**: `compute_surprise` が `llive.rust_ext.HAS_RUST` 検出で Rust 経路に自動委譲、不在時 numpy fallback。1e-6 parity 保証 (RUST-13)。
- **EdgeWeightUpdater (AC-10) wire-in**: `apply_time_decay` が `rust_ext.bulk_time_decay` で全 edge を 1 パスで precompute、その後 Kùzu delete-and-reinsert を実行。Python fallback 完全互換。
- 追加 parity test 5 件 (`bulk_time_decay` Hypothesis 50 ケース + 既知値 4 件) — Rust ⇄ Python 一致を 1e-9 tolerance で担保。

### Changed

- `pyproject.toml`: 0.4.0 → 0.5.0。
- `crates/llive_rust_ext/Cargo.toml`: 0.4.0 → 0.5.0。
- `src/llive/rust_ext/__init__.py`: `bulk_time_decay` 公開、`__all__` 拡張。

### Quality gates

- **Tests**: 444 passed (v0.4.0 baseline 439 + RUST-03 parity 5)
- **Coverage**: 98%
- **Lint**: ruff `All checks passed!`
- **Rust build**: `cargo build --release` clean、`maturin develop --release` green
- **Parity**: Hypothesis 100 ケース (compute_surprise 50 + jaccard 50 + bulk_time_decay 50) で Rust ⇄ Python 全合致

### Deferred (per v0.7 doc principles)

- RUST-02 rayon 並列化、RUST-05/06/07/08/09/10/11。Phase 6+ で意味論固定後に着手。

## [0.4.0] — 2026-05-14

Phase 5: Rust acceleration **skeleton** リリース。RUST-01 + RUST-02 baseline + RUST-04 baseline + RUST-13 parity harness をハンドル。実際の hot-path 並列化 (rayon) は v0.4.x で逐次マージ。

### Added (Phase 5 — Rust skeleton)

- **RUST-01**: `crates/llive_rust_ext/` Cargo workspace + PyO3 0.22 ベース skeleton。`maturin develop --release --manifest-path crates/llive_rust_ext/Cargo.toml` で editable install。
- **RUST-02 baseline**: `compute_surprise(new, mem) -> f32` — cosine similarity ベースの surprise kernel。py.allow_threads で GIL 解放。dim 検査は短絡前に必ず実行 (parity 担保)。
- **RUST-04 baseline**: `jaccard(a, b) -> f32` — u32 ソート済み id 集合の linear-merge 交差。
- **RUST-13**: Hypothesis ベース parity test (`tests/property/test_rust_python_parity.py`)。Rust ⇄ Python fallback が 1e-6 以下で一致することを 50 ケース × 2 関数で検査。
- `src/llive/rust_ext/__init__.py` — `HAS_RUST` flag + `__backend__` 自己診断 + pure-Python fallback。`pip install llmesh-llive` 単独 (Rust なし) でも全機能利用可、性能のみ Python 速度。
- `specs/rust_ffi/overview.md` — ABI contract / GIL handling / determinism rules / future hotspot order。

### Deferred to v0.4.x+ (per v0.7 doc principles)

- RUST-02 完全並列化 (rayon 並列 cosine)、RUST-03/05/06/07/08/09/10/11 全 hotspot。Phase 4 安定確認後の段階着手とする (`docs/requirements_v0.7_rust_acceleration.md` § 2「意味論先行・最適化後追従」)。

### Changed

- `pyproject.toml`: version 0.3.0 → 0.4.0。`[rust]` extra (`maturin>=1.5`) 新設。Rust 拡張本体は別ホイール (`llive_rust_ext`) として配布、本 PyPI パッケージは Python のみ。

### Quality gates

- **Tests**: 439 passed (Phase 3+4 baseline 429 + RUST-13 parity 10)
- **Coverage**: 98% (Rust 経路は parity test で間接カバー)
- **Lint**: ruff `All checks passed!`
- **Rust build**: `cargo build --release` clean、`maturin develop --release` 成功
- **Parity**: Hypothesis 50 ケース × 2 関数で Rust ⇄ Python 一致

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

[Unreleased]: https://github.com/furuse-kazufumi/llive/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/furuse-kazufumi/llive/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/furuse-kazufumi/llive/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/furuse-kazufumi/llive/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/furuse-kazufumi/llive/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/furuse-kazufumi/llive/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/furuse-kazufumi/llive/releases/tag/v0.1.0
