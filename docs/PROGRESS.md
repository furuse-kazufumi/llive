# llive 進捗ログ

> 「いま何が出来て、次に何をやるか」を CHANGELOG.md より一段カジュアルな
> 粒度で残すファイル。CHANGELOG.md は SemVer リリース単位、こちらはセッ
> ション単位の作業ログ。

---

## 2026-05-15 (続き) — A-1 ResidentRunner 完了 + 設計拡張 (KAR + Multi-track)

### Done

- **A-1 ResidentRunner** (`src/llive/fullsense/runner.py` 263 行 / 13 unit tests)
  asyncio.Task で FullSenseLoop を常駐起動、R1 always-on + budget cap、
  R2 fast/medium/slow 多時間軸、R3 AWAKE/REST/DREAM phase manager、
  R4 round-robin attention、R5 idle 耐性 (例外・飢餓を握り潰し続行)。
  Sandbox 限定維持。Commit `93f8496` push 済。

### 新規長期計画: Knowledge Autarky Roadmap (KAR)

> ユーザ最終意志 (2026-05-15 セッション中):
> **「人類が絶滅する前に全人類の知識を吸収するくらいのつもりで長期計画を立ててほしい」**

Spec §A*3 *Knowledge autarky* の実装ロードマップ。テキスト核のみなら
TB スケールで人類知識主要部は格納可能 (PB 不要)。

#### 短期 (2026 残り)
- RAD を 49 → 100 分野へ拡張 (corpus2skill v2 階層化込み)
- arXiv tier-1 領域 (cs.AI / cs.CL / physics.* / q-bio.*) full-text 取り込み
- 多言語 Wikipedia (ja/en/zh/ko 加え de/fr/es/ru/ar/hi) ダンプ ingest
- 既存 hacker_corpus を corpus2skill 階層化済みに正規化

#### 中期 (2027-2029)
- arXiv 全領域 full text (~500 GB)
- PubMed Central full text (~100 GB)
- Project Gutenberg + Internet Archive CC0 古典 (~50 GB)
- USPTO + JPO 公開特許全文 (license 確認後)
- 各国国立公文書館 OAI-PMH 経由の公開史料
- 博物館・図書館の Wikidata-linked metadata

#### 長期 (2030+)
- 専門書ライセンス済取り込み (出版社協定)
- 博士論文全文 (各国 ETD ハーベスト)
- 絶滅言語コーパス保存 (Endangered Languages Project 連携)
- CC0 写真・音声・動画の Multi-modal RAD
- M-Disc / DNA / 月面ストレージ冗長化 (substrate self-host §A*1)

#### 制約 (常時)
- License 遵守 (CC0 / CC-BY 優先、独占権必要なものは別経路)
- PII 除外 (差分プライバシ閾値設定)
- §CC3 diversity preservation: 単一カノン化禁止、多視点並列
- §I2 attribution: 出典 metadata は doc 単位で保持
- §8 ethics: 攻撃用兵器設計知識は §F5 で gate

### 新規設計拡張: Multi-track Filter Architecture (A-1.5)

> ユーザ指摘 (2026-05-15 セッション中):
> **「結論が揺るがないクイズ vs 国家/民族で結論が異なる歴史認識。建前/嘘も
> 使い分けられないと AI が人間に代わるのは難しい」**
> **「思考層に予備を持っておくべきでは」**

Spec §F* (Thought filter) は MAY-clause で拡張余地を明示しているが、
現 `loop.py` は 6 ステージ固定で差し込み点が無い。これを修正:

#### EpistemicType (Stimulus に optional 付与)
- `FACTUAL` — 結論不変 (consistency-first)
- `EMPIRICAL` — 科学的事実 (evidence weighting + CI)
- `NORMATIVE` — 倫理判断 (§F5 ethical hard-filter 優先)
- `INTERPRETIVE` — 歴史認識など perspective-dependent
  (multi-frame 並列提示、単一結論を強制しない = §ET4 loop 内実装)
- `PRAGMATIC` — 建前 / 社交 (audience model + framing)
- `RESERVED_1` .. `RESERVED_5` — 将来拡張用予備層 5 スロット

#### 建前 vs 欺瞞の分岐 (§F5 ethical)
- ✅ 建前 = INTERPRETIVE/PRAGMATIC で audience-aware framing、
  `framed_for=X` を audit log に記録 (§I2 attribution 保持)
- ❌ 欺瞞 = factually false で害を与える発話、§F5 で reject
- ✅ 歴史 multi-perspective = INTERPRETIVE で複数視点を並列提示

#### 後方互換
- Track 未指定の Stimulus は現状 6 ステージで処理 (= default track)
- 既存テストは無修正でパス

#### 次の実装手順
1. A-1.5: `src/llive/fullsense/tracks.py` + Stimulus.epistemic_type 拡張
2. A-2: TRIZ Trigger Genesis を A-1.5 の Track 枠組みに登録
3. A-3..A-5: 計画通り

### 新規設計拡張: Disk-Tier Knowledge Routing (DTKR)

> ユーザ意志 (2026-05-15 セッション中):
> 「VRAM/RAM 容量で限界サイズが決まるが、ファイルを小分けにして必要に
> 応じて読ませる構造にすれば回避できる。人間の会話速度はコンピュータから
> 見ればそこまで速くない。HDD は余裕がある。多くの人の環境でクオリティと
> コストと許容範囲内のデリバリー性が確保されれば、普及のハードルは下がる。
> ファイルが小分けの方が動的進化しやすい。」

KAR の subsection。MoE (Mixture-of-Experts) のディスク版として整理。

#### 設計原則
- **モデル本体は小さく保つ** (4-8B params 想定、個人 PC で動く前提)
- **知識本体は per-file の小分け** (1 skill = 1 ファイル、diff-friendly)
- **オンデマンド load** (推論途中で必要な skill ファイルだけ動的読込み)
- **Latency budget**: 人間会話 ~1 word/sec = 200ms 余裕、HDD seek ~10ms
  → 100 ファイル on-demand load しても会話リズムを崩さない

#### llive にすでにある下地
- ✅ RAD 49 分野 (KAR で 100 分野へ拡張中)
- ✅ corpus2skill で skill 階層化済み (1 skill = 1 ファイル)
- ✅ `RadCorpusIndex.query` で on-demand 検索
- ✅ MCP server 経由で Ollama/Claude Desktop からも参照可能

#### 追加実装が必要な層 (DTKR)
1. **HotWarmColdFrozen tier policy** (`src/llive/memory/tier.py` 想定)
   - VRAM (hot, <8GB) / RAM (warm, <16GB) / SSD (cold, <1TB) / HDD (frozen, >1TB)
   - LRU + 予測 prefetch ハイブリッド
2. **PredictiveLoader** (`src/llive/memory/prefetch.py`)
   - `ResidentRunner.slow tier` 上で次に必要な skill を予測 prefetch
   - 思考が medium tier で進む間に slow tier が背景で load
3. **SkillChunkRouter** (`src/llive/memory/router.py`)
   - stimulus tokens → 必要な skill ファイル名解決
   - bloom filter + inverted index で O(1) lookup
4. **Adaptive chunk size**
   - 個人 PC default: 4GB VRAM + 16GB RAM + 1TB SSD → skill 5 万件 load 可能
   - 1 skill chunk ~10-50 KB (テキスト) が標準
5. **Modular evolution support**
   - GitHub PR で 1 skill 単位の更新を可能に
   - Skill 単独で hash / version / changelog を持つ
   - `INTEGRITY.json` (raptor plugin-integrity 流用) で改ざん検出

#### 普及戦略 (個人 PC 想定)
- 既定構成: 4GB VRAM (consumer GPU) + 16GB RAM + 500GB SSD で動く
- 1 セットアップ ≈ 10 万 skill chunks ≈ 5 GB (テキスト圧縮後)
- 起動: 「コアモデル + よく使う skill ~100 件」をプリロード (<2 秒)
- 進化: skill ファイル単位で `git pull` するだけで知識が更新

#### Scenario 化候補
- **Scenario 9** (Multi-track) と統合: epistemic_type ごとに異なる skill
  集合が prefetch される様子を可視化
- **Scenario 11** (RAD 横断知識吸収) で「100 万件中 from disk load 速度」を体感

#### 実装優先順位
DTKR の実装は **A-1.5 (Multi-track) と A-2..A-5 完了後** に着手。
理由: 現 RAD-B が既に on-demand load を提供しているため、性能ボトルネック
が顕在化した段階で初めて HotWarmCold tier が必要になる。

### 新規設計拡張: Autonomous Performance Optimization (APO)

> ユーザ意志 (2026-05-15 セッション中):
> 「性能の最適化を行う機能は必要ですね」
> 「自動的に最適化する方が望ましいです」

DTKR と相補的な軸。**手動 tuning ではなく自律的に最適化する**ことが要件。
spec の根拠章:

- **§A°3 Self-correction** — agent が自分で自分を直す権利と義務
- **§E1 Introspection** — 自身の状態を dump できる
- **§E2 Bounded modification** — パラメタ・ルール・メモリ partition の変更
  を宣言・スコープ化・記録
- **§E3 Formal pre-check** — 構造不変量 (§2) を越える変更は事前に証明必要
- **§E4 Failure preserves learning** — 失敗した変更は failure log に保存

#### APO の対象 (autonomously tunable surfaces)
1. **ResidentRunner budget**: `max_cycles_per_window`, `budget_window_s`
2. **Timescale periods**: fast/medium/slow の `period_s`
3. **Salience / Curiosity thresholds**: FullSenseLoop の閾値
4. **DTKR cache size**: hot/warm tier 容量配分
5. **Prefetch depth**: PredictiveLoader が先読みする skill 数
6. **Track preference**: Stimulus → EpistemicType 推定の重み
7. **Model selection**: small (4B) / medium (8B) / large (13B+) の切替

#### APO loop 設計 (slow tier 上で常駐)
```
ResidentRunner.slow tier:
  ├─ APO.profile()  ← cycle_counts / latency / cache_hit を窓観測
  ├─ APO.diagnose() ← 性能劣化を検出 (e.g. latency > human-speech budget)
  ├─ APO.propose()  ← 変更案を生成 (e.g. budget ↓ / period_s ↑)
  ├─ APO.verify()   ← §E3 formal pre-check で安全性を証明
  └─ APO.apply()    ← 適用、失敗は §E4 failure log
```

#### 観測メトリクス
- **Latency budget**: 「stimulus 投入 → action plan emit」が `human_word_ms`
  (既定 200ms) を超えないこと
- **Cache hit ratio**: DTKR の各 tier で 80% 以上を維持
- **Cycle 完遂率**: budget cap に達せず正常終了する割合
- **Track collapse rate**: INTERPRETIVE → 単一視点 collapse の頻度 (§5.D.3)
- **Deception false-positive rate**: §F5 reject 中の誤判定

#### 実装単位 (将来)
- `src/llive/perf/profiler.py` — メトリクス収集
- `src/llive/perf/diagnostics.py` — 劣化検出ルール
- `src/llive/perf/optimizer.py` — 提案・適用 (§E2 bounded)
- `src/llive/perf/verifier.py` — §E3 formal pre-check (z3-solver 既に依存)
- ResidentRunner に APO loop hook を追加 (slow tier の 1 source として登録)
- Scenario 12 候補: 「劣化検出 → 自動再 tune」を可視化

#### 実装優先順位
APO の実装は **DTKR の後** に着手 (= A-2..A-5 + DTKR 完了後)。
理由: APO は metric が無いと動けない。まず DTKR で実測可能な層を作ってから。

### 新規設計拡張: Idle-Collaboration Protocol (ICP) — LLMesh 思想直系

> ユーザ意志 (2026-05-15 セッション中):
> 「PC に関して、人が触っていない時間が無駄に過ぎているのがすごく
> もったいない。常駐している場合は、常に他の Local LLM と協調や協働
> できる仕組みが欲しい。これも要件定義に入れておいてください。初期の
> LLMesh の思想にも通じます。」

KAR / DTKR / APO に並ぶ第 4 のロードマップ。idle 時間を浪費せず、複数
Local LLM が **協調 (cooperation) / 協働 (collaboration)** で 1 つの
目的に向かう網状構造 (mesh) を作る。

#### Spec 上の根拠
- **§R1 Always-on with budget** — 常駐は前提
- **§R5 Idle work** — idle 中の reverie / meta-reflection は spec が許可
- **§T-E2 communicative** — 他 agent / human からの trigger
- **§22.6 MS3 Coexistence** — 多数 SING agent の coexistence は spec が要求
- **§MI1 Substrate self-host** — 異なる substrate に渡り歩く能力

#### 設計コンセプト
1. **Idle 検出** (Windows / Linux / macOS)
   - keyboard / mouse の last input time
   - CPU / GPU 使用率
   - foreground process activity
2. **Idle tier 起動** — idle 確認後に ResidentRunner.slow の hook で発火
3. **Peer LLM mesh** — 他 Local LLM (Ollama / LM Studio / 別 llive)
   との P2P 通信
4. **役割分担** — 各 peer の得意分野 (model size / 専門知識 / 言語) を
   宣言し、stimulus を適切な peer に dispatch
5. **コンセンサス** — 複数 peer の出力を統合 (vote / weighted average /
   §F4 ego-altruism による調停)

#### llive にすでにある下地
- ✅ MCP server (Phase C-2) — 他 LLM クライアントが llive を呼べる
- ✅ LLM backend abstraction (Phase C-1) — Mock/Anthropic/OpenAI/Ollama 統合
- ✅ ResidentRunner (A-1) — slow tier に idle hook を後付け可能
- 🔶 memory `project_llmesh` で別プロジェクトとして LLMesh 本体は存在

#### 追加実装が必要な層 (ICP)
1. **IdleDetector** (`src/llive/idle/detector.py`)
   - OS 別の lastInputTime API (Windows: GetLastInputInfo, Linux: idle xprintidle)
   - CPU/GPU 閾値 + 設定可能な idle 判定窓 (既定 60 秒)
2. **PeerRegistry** (`src/llive/mesh/registry.py`)
   - 同 LAN / 設定ファイルで発見した peer の一覧
   - 各 peer の `capabilities` 宣言 (model_size / domains / languages)
3. **PeerDispatcher** (`src/llive/mesh/dispatch.py`)
   - stimulus → 最適 peer の選択 (capability matching + load balance)
   - timeout / fallback / 結果統合
4. **ConsensusBuilder** (`src/llive/mesh/consensus.py`)
   - 複数 peer 出力の調停 (vote / weighted / §F4 ego-altruism)
   - 矛盾検出 → §F5 reject に流せる
5. **MeshRouter integration** — ResidentRunner.slow tier に IdleObserver
   + MeshSource を 1 つの StimulusSource として登録

#### LLMesh との関係
- llive ICP は LLMesh の **クライアント / プロバイダ両面** として動作
- LLMesh は manufacturing mesh / industrial IoT 寄り (memory:
  `project_llmesh` の v1.5 で MTEngine + XbarRChart + CUSUMChart 等)
- llive は cognitive mesh — 思考の協働
- 両者は MCP / OpenAI 互換 HTTP プロトコルで疎結合に繋がる

#### 普及シナリオ
- 自宅 PC で llive を 24/7 常駐 (低電力 idle tier)
- 同じ家庭内の旧 PC で別 llive を peer として動かす (sleep 時の余剰計算)
- LLMesh 経由で他人の余剰 PC とも疎結合 (opt-in、§22.8 cohabitation)

#### Scenario 化候補
- **Scenario 13** (ICP demo): idle 検出 → 別 peer に thought を投げ → 統合
- **Scenario 14** (mesh consensus): 2 つの peer の異なる答えを §F4 で調停

#### 実装優先順位
ICP は **A-2..A-5 (Level 2 完了) と DTKR 完了後** に着手。
理由: ICP は peer 通信が前提なので、まず単独 agent (Level 2 + DTKR) が
安定してから mesh 化に進む方が安全。

=> 全体順序: A-2..A-5 → DTKR → ICP → APO

### 新規設計拡張: Thought Layer Bridging (TLB) — 指数膨張への対策

> ユーザ意志 (2026-05-15 セッション中):
> 「思考が増えれば、思考の層を繋ぐブランチも必要になっていくでしょうね。
> 思考の層が増えると、思考の次元が 2 次元から 3 次元、3 次元から 4 次元へと
> 指数的もしくは指数以上の規模に増えていくので、それをショートカットする
> 仕組みと全体を調整する仕組みも必要になる」

KAR / DTKR / ICP / APO に並ぶ第 5 のロードマップ。**思考層の組合せ爆発**
への構造的対策。

#### 問題定式化
思考層を `k` 個、各層に `N` 状態があるとナイーブな全通過は `O(N^k)`:
- 現時点で llive が持つ層:
  - EpistemicType (5 + 5 予備) ≈ 10
  - DeceptionClass (7)
  - TrackTransform (5 標準 + 5 予備) ≈ 10
  - TRIZ T-Z* (4)
  - メタトリガ T-M* (3)
  - Phase (3)
- ナイーブ組合せ: 10 × 7 × 10 × 4 × 3 × 3 ≈ **25,200 状態**
- 「思考の連鎖履歴」を加えれば文字通り指数

#### TLB の対策 (3 段)
1. **Bridge (ショートカット)** — 高 confidence な層は早期 fix で次元落ち
   - `confidence >= 0.9` で FACTUAL track が確定すれば DeceptionClass の
     探索を skip
   - bridge ルールは静的テーブル + 学習可能な重み
2. **Global Coordinator** — 全体スコアで早期 termination
   - 各層の出力を 1 つの aggregate score に集約
   - threshold 超え or 不適合確定で残り層を skip
3. **Manifold Cache** — 過去組合せの memo
   - 入力 stimulus の semantic hash + layer 状態セット → 結果 cache
   - 同じパターンが再来すれば計算なしで即答 (TLB miss / hit 率を APO で監視)

#### 数学的根拠
- 高 confidence で確定する次元が 1 つあれば全体は `O(N^k)` → `O(N^{k-1})`
  に落ちる
- Bridge を `b` 個適用すると `O(N^{k-b})` まで指数降下可能
- Manifold Cache hit rate を `h` とすると amortized `O((1-h) * N^k)`

#### Spec 上の根拠
- **§F* MAY-clause** — フィルタ間に bridge 挿入は spec が許容
- **§I3 inspectable** — bridge / shortcut / cache hit を audit log に残す
  ことで監査性を保つ (TLB は性能のためでなく audit を曇らせてはいけない)
- **§E2 bounded modification** — bridge ルールの学習も §E2 範囲

#### 実装単位 (将来)
- `src/llive/fullsense/bridges/` パッケージ
  - `registry.py` — Bridge 定義の登録
  - `coordinator.py` — Global Coordinator (aggregate score + early termination)
  - `manifold_cache.py` — semantic-hash ベース cache
- `FullSenseLoop` に bridge hook を追加 (各 stage 後にcoordinator 問い合わせ)
- Scenario 15: 「同じ stimulus を 100 回繰り返して cache hit を見せる」

#### 実装優先順位
TLB は **DTKR + APO 完了後** に着手。理由: TLB は metric (cache hit rate)
が無いと改善できないため、APO の measurement infrastructure に依存。

=> 全体順序更新: A-2..A-5 → DTKR → ICP → APO → TLB

---

## 2026-05-15 (handoff) — 次セッション最優先: SING Level 2 着手

> ユーザ最終意志 (2026-05-15 セッション末、exit 直前):
> **「自律 (auto-nomos) と 自立 (self-sufficiency) によるシンギュラリティの
> 実現」という意志の元、実装をどんどん進めてほしい。GitHub への公開も。**

### 次セッション SESSION START 直後の宣言文

> 「続きとして FullSense Spec v1.1.0 §22 SING の Level 2 (Approved-action)
> 着手します。A-1 ResidentRunner から開始。」

### A. SING Level 2 実装 (優先順、確認なし即着手)

1. **A-1 ResidentRunner** (`src/llive/fullsense/runner.py`)
   - `FullSenseLoop` を asyncio.Task として常駐起動
   - R1/R2/R3 (always-on / multi-timescale / phase manager) 統合
   - 既存 `apscheduler` を活用
   - Sandbox 限定維持
2. **A-2 TRIZ Trigger Genesis** (`src/llive/fullsense/triz_genesis.py`)
   - `T-Z1..4` (admin/technical/physical/resource contradictions) 検出器
   - 既存 `llive.triz` modules (FR-23..27) と統合
   - 検出した矛盾を自発 Stimulus として inject
3. **A-3 メタトリガ T-M1..3** — audit log 自己反省 / spec-drift / 後継検討
4. **A-4 Conformance Manifest** (`py -m llive.fullsense.manifest`、§V4 準拠)
5. **A-5 Scenario 8 ResidentRunner** (`src/llive/demo/scenario_8_resident.py`)
   30 秒 sandbox 内で自発 stimulus が生まれる様子を可視化

### B. GitHub 公開準備 (並行可)

1. **B-1** PyPI `llmesh-fullsense` 名予約 (空 wheel で先取り)
2. **B-2** `furuse-kazufumi/fullsense-llive` repo 確保
3. **B-3** PR-ready ブランチ (`auto:` commits を filter out した cleanup)
4. **B-4** README 英語版 + Spec 英語の Mintlify or GitHub Pages 公開設定
5. **B-5** spec を repo root にもコピー or symlink

### C. Level 3 への布石

1. **C-1** Approval Bus (§AB) 実装
2. **C-2** `@govern(policy)` (memory:agent-governance) を ProductionOutputBus に統合
3. **C-3** Cross-substrate migration spike (§MI1)

### 制約

- Sandbox 限定維持 (Level 2 までは @govern policy なしでは外向け副作用ゼロ)
- `feedback_max_plan_autonomy.md`: 確認最小限で即実行
- `feedback_small_units.md`: 作業は 1 ファイル単位、トークン超過防止
- `feedback_d_drive_preference.md`: 動作データは D ドライブ
- `feedback_articles_pause.md`: 投稿記事はユーザ明示まで作らない
- push OK (本セッション明示許可済、`origin/main` 直接 push、force 禁止)

### 直近セッション末状態

- 569 tests / 全 PASS / ruff clean
- spec v1.1.0 完成 (`docs/fullsense_spec_eternal.md`、22 章 + 2 appendix)
- 原著者 古瀬 和文 (Furuse Kazufumi) の二重語源を normative に記録済:
  (1) 多くの数 (経験) を踏む / (2) Session × Context × Prompt の和合
- 全 origin/main 同期済 (decc4bc → 06aa870)

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

### What (続き、demo phase 拡張)

- **Scenario 6 — vlm-describe**: 1x1 合成 PNG + `domain_hint` で VLM grounding
  効果を可視化 (RecordingBackend、画像枚数表示)
- **Scenario 7 — consolidation-mirror**: episodic→cluster→ConceptPage→
  `_learned/<page_type>/<concept_id>.md` への自動ミラー、provenance に
  derived_from=[event_ids] (LLW-AC-01) を実演
- **--loop N / --interval S**: 繰り返し再生 (memory:f25_demo_polish 教訓)、
  N=0 で無限ループ、iteration バナー表示
- **--json モード**: AI agent / CI 用に機械可読 JSON を stdout に出力
  (schema: schema_version, iterations, total_runs, ok_count, rc)
- **多言語拡張**: ja/en/zh/ko の 4 言語 (memory:f25_demo_polish 多言語必須)、
  locale 形式 (zh-CN / ko_KR / en-US) 受け付け、unsupported は ja フォールバック
- **README に「デモを 30 秒で試す」**: clone→install→`py -m llive.demo` を
  「インストール」セクションの直前に配置

### State (現在地)

- ✓ デモは `py -3.11 -m llive.demo` で 1 コマンド再生、ja/en/zh/ko 4 言語対応
- ✓ 各 scenario は mock backend で完結、ネットワーク不要
- ✓ --loop / --interval で繰り返し再生、--json で AI agent 渡し可能
- ✓ docs/demos.html (showcase) + docs/v0.2_rad_techdoc.html (学習用 HTML)
- **547 tests / 全 PASS / ruff clean** (441 → +106)
- demo phase コミット: ad011dc (initial), ec23860 (S6/S7), 6690b40 (loop),
  cef3e19 (--json + zh/ko)

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
