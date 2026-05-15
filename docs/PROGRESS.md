# llive 進捗ログ

> 「いま何が出来て、次に何をやるか」を CHANGELOG.md より一段カジュアルな
> 粒度で残すファイル。CHANGELOG.md は SemVer リリース単位、こちらはセッ
> ション単位の作業ログ。

---

## 2026-05-16 (続) — C-2: @govern + ProductionOutputBus (Phase 1+2+3)

handoff v3 C-2「@govern(policy) を ProductionOutputBus に統合」を実装。副作用
emit を ApprovalBus gate 経由で行う production 経路を確立。

### Done

- **@govern decorator** (`src/llive/approval/decorators.py`)
  - `@govern(bus, action, payload_fn=..., on_denied=...)` で任意 fn を gate
  - APPROVED で呼ぶ、DENIED|silence で `on_denied` か None
- **ProductionOutputBus** (`src/llive/output/production.py`)
  - 低レベル `emit_raw(action, payload, *, on_approved, rationale)`
  - 高レベル `emit_file(path, content)` / `emit_mcp_push(target, message)` / `emit_llove_push(view_id, payload)`
  - `mcp_push_fn` / `llove_push_fn` 注入式で transport 非依存
  - 副作用中の例外を `EmitResult.error` に捕捉、raise しない
- **SandboxOutputBus** に `record_denied_emit()` 追加 (`_denied_emits` list + JSONL mirror)
- テスト +17 件 (govern 6 / production bus 11) / 既存無修正
- **832 PASS / ruff clean / 回帰ゼロ**

### 次セッション 着手宣言文 (v5)

「C-1 + C-2 が production 化完了。次は C-3 Cross-substrate migration spike
(§MI1) と、実 MCP client / 実 llove bridge を ProductionOutputBus に
接続する実機検証 (sandbox 外) を進めます。」

### 残

- C-3: Cross-substrate migration spike (§MI1)
- 実機検証: MCP client (`src/llive/mcp/server.py`) と llove bridge 接続
- Ed25519 署名 (extras `[crypto]`)

---

## 2026-05-16 — Approval Bus production 化 (Policy + SQLite Ledger)

handoff v3 の次セッション宣言「C-1 Approval Bus に policy + persistent ledger
を結合」を実装。9 軸 skeleton の production 化フェーズの最初のピース。

### Done

- **Policy 抽象** (`src/llive/approval/policy.py`)
  - `ApprovalPolicy` Protocol + `AllowList` / `DenyList` / `CompositePolicy`
  - `deny_overrides(allow, deny)` helper
- **SqliteLedger** (`src/llive/approval/ledger.py`)
  - stdlib sqlite3 のみ、外部依存ゼロ。スキーマ v1 (3 テーブル + index)
  - `append_request` / `append_response` / `load()` / context manager
- **ApprovalBus 拡張** (`src/llive/approval/bus.py`)
  - optional `ledger=` で再起動越し replay 復元 (pending 含む)
  - optional `policy=` で auto-approval/deny を `by="policy:auto"` で記録
  - 引数なし `ApprovalBus()` は既存挙動と完全一致 → 後方互換
- **テスト** 18 件追加 / 既存 8 件無修正
  - `test_approval_policy.py` (7) / `test_approval_ledger.py` (6) / `test_approval_bus_policy.py` (5)
  - **815 PASS / ruff clean / 回帰ゼロ**

### 次セッション 着手宣言文 (v4)

「Level 3 (Permitted-action) C-1 が production 化完了 (policy + SQLite ledger)。
続いて C-2 `@govern(policy)` の ProductionOutputBus 統合に着手。bus を
RPA driver と output bus の両方で共有する形に拡張します。」

### 残 (handoff v3 の C 章)

- C-2: `@govern(policy)` を ProductionOutputBus に統合
- C-3: Cross-substrate migration spike (§MI1)
- 署名 (Ed25519 等) は v0.2.x 後段で extras 隔離検討

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

#### Mathematical Toolkit — RAD 数学コーパスとの直接対応

> ユーザ意志 (2026-05-15 セッション中):
> 「多変数解析などの数学的アプローチが必要になる場面も増えると思うので、
> コーパスに数学的な部分を含ませていたのです。」

RAD には既に数学的基盤が物理的に揃っており、各ロードマップ章の理論基盤
として参照すべきマッピング:

| 章 | 必要な数学 | 対応 RAD コーパス |
|---|---|---|
| TLB Bridge / Manifold | 多変数解析 / 多様体学習 (UMAP / t-SNE / 主多様体) | `multivariate_analysis_corpus_v2` |
| TLB Global Coordinator | 情報幾何 (Fisher 計量、自然勾配)、Shannon 情報量 | `information_theory_corpus_v2` |
| APO Optimizer | 凸最適化 / 制約付き最適化 / gradient descent | `optimization_corpus_v2` |
| APO Verifier | 形式手法 / SMT / z3 (既存依存) | `formal_methods_corpus_v2` + `automated_theorem_proving_corpus_v2` |
| APO Metric 推定 | 統計推定 / 信頼区間 / 仮説検定 | `statistics_corpus_v2` |
| DTKR PredictiveLoader | 強化学習 (バンディット / value iteration) | `reinforcement_learning_corpus_v2` |
| DTKR Cache eviction | LRU の理論限界 / オンライン学習 (regret bound) | `optimization_corpus_v2` + `statistics_corpus_v2` |
| ICP ConsensusBuilder | ベイズ統計 / 確率的合議 (DSm / Dempster–Shafer) | `statistics_corpus_v2` + `information_theory_corpus_v2` |
| FullSenseLoop F1 Salience | 情報理論的 surprise (Bayesian surprise、active inference) | `information_theory_corpus_v2` |
| Multi-track Filter | 多変量分類 (kernel methods、SVM、PAC bound) | `multivariate_analysis_corpus_v2` |
| Time-horizon Filter F6 | 数値解析 / ODE / 制御理論 / モデル予測制御 (MPC) | `numerical_methods_corpus_v2` |

**運用方針**: 各章を実装するとき、対応する RAD コーパスに「ヒント」を
照会する形 (RAD-B `RadCorpusIndex.query` 経由) で根拠を引いてから設計する。
これにより「直感や経験則」ではなく「先行研究を踏まえた数学的根拠」で実装が
進む。spec §A*3 Knowledge autarky (RAD-class 知識への autarky) が
operational に実証される副産物。

実装テンプレ例 (TLB Bridge を作るとき):
```python
from llive.memory.rad import RadCorpusIndex
idx = RadCorpusIndex(root=Path("data/rad"))
# 多様体学習で「思考の局所近傍」を学ぶ前に文献ヒント
hints = idx.query("manifold learning local neighborhood approximation",
                  corpora=["multivariate_analysis_corpus_v2"], top_k=5)
# hints.top_docs を Implementation Notes として PR 説明に含める
```

### 新規設計拡張: Publication Media (PM) — 動画/画像/asciinema による説明力強化

> ユーザ意志 (2026-05-15 セッション中):
> 「公開サービスに関して、画像や動画も公開できるなら、分かりやすく説明文の
> 途中で動作している画像や動画も公開したいですね。」

B 章 (GitHub 公開準備) の拡張軸。README / Mintlify / GitHub Pages で説明文の
途中に **動作画像・GIF・asciinema・mp4** を埋め込んで、読み手が「これが
動いているのか」を視覚で即理解できる体裁にする。

#### 採用メディア (軽量 → 重量の順)
1. **asciinema** (`.cast` ファイル) — terminal session を SVG / interactive
   player で再生。テキストとして diff 可能、リポジトリにそのまま commit 可能。
   - `asciinema rec` → `.cast` 録画 → GitHub README に `<a>` リンク or
     embed (mintlify は `<asciinema-player>` 直接対応)
2. **animated SVG** — 軽量、GitHub README で直接 inline rendering
3. **animated GIF** — 普及度高いが容量重 (1 シナリオ ~1-3 MB)
4. **mp4 / webm** — 高品質、容量重 (CDN / GitHub LFS 検討)
5. **静止画 PNG** — scenario の各 stage を 1 枚ずつ (説明テキスト中の inline)

#### 推奨運用 (Scenario ごと)
- Scenario 8 (ResidentRunner): asciinema 30 秒 cast + animated SVG ループ
- Scenario 9 (Multi-track): 静止画 5 枚 (各 track の出力枠を 1 枚)
- Scenario 10 (Deception): asciinema cast (judge() の判定結果を見せる)
- Scenario 11 (RAD): GIF ループ (検索クエリ → 結果が浮かび上がる)

#### 公開先テンプレ
| 公開先 | 推奨フォーマット | 配置 |
|---|---|---|
| GitHub README | asciinema embed + GIF / static PNG | `docs/media/<scenario>/` |
| Mintlify | asciinema-player + img | `docs/snapshots/` |
| GitHub Pages | HTML5 video + SVG | `docs/site/` |
| dev.to / Qiita / note | 静止画 PNG + リンク (現状記事 pause 中) | embed |

#### 制約
- 1 リポジトリ内のメディア合計 < 50 MB (GitHub soft-limit) を維持
- 機械生成可能性: asciinema は CI で再録画して常に最新動作と同期
- 多言語版: 各メディアに lang suffix (`scenario_8_ja.cast` / `..._en.cast`)
- License: 自作のみ、フォントは noto / GitHub system font に限定

#### 実装単位 (将来)
- `scripts/record_demos.sh` — 全 scenario を asciinema で自動録画
- `scripts/cast_to_svg.py` — asciinema cast → 軽量 SVG 変換
- `docs/media/` ディレクトリ構成 + .gitattributes (LFS 対応)
- README に「30 秒動画で見る」セクション追加 (普及戦略の入口)

#### 実装優先順位
PM は **GitHub 公開 B-1..B-5 と同時** に進める。Scenario 11 完了後、
B 章着手と同タイミングで `scripts/record_demos.sh` を整備。

### 新規設計拡張: RPAR (RPA Roadmap) — 事務作業全自動への道

> ユーザ意志 (2026-05-15 セッション中):
> (1) 「キーボードやマウスなどを自動で動かしたり、コマンド実行をしたりなども
>     llove 経由で許可できるようにしたいですね。RPA 出来るようにして、事務作業を
>     全自動にできることが理想です。」
> (2) 「PowerShell の使用を中断して、llove で claude code を動かしたい。
>     上下左右キーなどの操作も受付しながらカラフルな表示もできると嬉しい」

KAR / DTKR / APO / ICP / TLB / PM に並ぶ第 6 (= 第 7 含む) のロードマップ章。
Spec §6 Action System / §6.3 Approval Bus / §22 SING Level 3 (Permitted-action)
の本丸。memory `project_llove_shell_integration` (F23 PowerShell 互換シェル +
F24 Claude Code 統合) と直結する。

#### Spec 根拠
- **§6.1 AC.I INTERVENE** — 「permitted-class action in the world」を実行
- **§AB Approval Bus** — replayable approval + principal identification
- **§AB4** — Silence MUST be treated as **denial** (= 沈黙 = 不承認)
- **§I3 inspectable** — 全 RPA action は audit log に残る
- **§I4 partitioning** — `forbidden` / `requires-approval` / `permitted` の 3 分割
- **§ET6 Right of cessation (others)** — 他者の停止要求は honour

#### 自動化対象 (3 軸)
1. **Input automation**: keyboard / mouse / scroll / clipboard
2. **Command automation**: shell exec (PowerShell / bash) / process control
3. **File system automation**: read / write / move / archive / format conversion

#### 実装単位 (将来)
- `src/llive/rpa/` パッケージ
  - `drivers/keyboard.py` — Windows: pywin32 / SendInput, Linux: xdotool, macOS: AppKit
  - `drivers/mouse.py` — 同上
  - `drivers/shell.py` — subprocess + timeout + 環境変数 sanitize
  - `drivers/fs.py` — pathlib + safety guard (危険パス禁止)
  - `recorder.py` — ユーザ操作録画 → 再現 flow YAML
  - `player.py` — flow YAML を実行、step ごとに Approval Bus に問い合わせ
- `src/llive/approval/` パッケージ (§AB 実装)
  - `bus.py` — pubsub 形式の Approval Bus (replayable)
  - `policies/` — `@govern(policy)` 用ポリシーセット
  - `revoke.py` — §AB3 rollback / compensating action
- `llove` 側 (TUI dashboard) で:
  - **F23 PowerShell 互換シェル** で claude code を起動 (subprocess)
  - **上下左右キー受付** (Textual の Input widget + Key bindings)
  - **カラフル表示** (Rich Text + Theme system)
  - 「approve / deny」ダイアログ for §AB
  - **F24 Claude Code 統合** で llive ⇄ claude code 双方向通信

#### llove で claude code を動かす経路
1. **llove** が PowerShell プロセスを spawn → claude code CLI を起動
2. claude code の出力は llove の Output pane に Rich Text で描画
3. キー入力は llove → claude code stdin へ forward (上下左右はカーソル制御)
4. llive (本体) は **llove 経由で** claude code と疎結合接続:
   - MCP server (Phase C-2) を介して claude code → llive tools を呼出可能
   - LoveBridge (F25) で双方向 event 流

#### 安全制約
- **既定 deny**: 全 RPA action は §AB4 沈黙 = 不承認、明示 approve 必須
- **Reversibility**: 全 action は §AB3 rollback / compensating action 持ち
- **Forbidden zone**: §I4 で「絶対禁止」のパス / コマンドを定義
  (例: `rm -rf /`, `format C:`, `git push --force` 等)
- **Audit chain**: 全 action は SHA-256 hash chain (§V3 tamper-evident)
- **Right to cease**: ユーザがいつでも `Ctrl+C` / llove 停止ボタンで打ち切り

#### 普及シナリオ (会社事務作業の全自動化)
- 朝の定型作業 (メール開封 → 重要分類 → 返信 draft) を flow 化
- レポート生成 (Excel 集計 → グラフ → PPT 貼付) を flow 化
- ファイル整理 (Downloads → 月別 archive) を flow 化
- llove で「今日のタスク 5 個」を表示、approve でまとめて実行

#### Scenario 化候補
- **Scenario 13** (RPA dry-run): キー操作 flow を mock driver で再生
- **Scenario 14** (Approval Bus): 3 種 action を順次 approve/deny で見せる
- **Scenario 15** (llove ⇄ claude code): TUI で claude code を起動して
  上下左右で履歴 nav、カラー表示確認 (llove プロジェクト側で実装後)

#### IME 入力対応 (日本語 / 中国語 / 韓国語)

> ユーザ意志 (2026-05-15 セッション中):
> 「llove で日本語入力や中国語入力も受け付けられるのか気にしています。」

llove は TUI なので Terminal の IME (Input Method Editor) 対応が前提に
なるが、TUI における IME は環境差が大きく、段階的に攻める必要がある。

実装フェーズ:
1. **Phase 1 (現状)** — UTF-8 表示 OK / 入力は ASCII or 直貼り付け
2. **Phase 2** — 入力 widget で UTF-8 文字列を **事前変換済みで** 受け取る
   (例: IME で変換完了した文字列を copy-paste、または別アプリで入力した
   文字列を read-only field に流し込む)
3. **Phase 3** — Textual の Key event + composing event を扱う:
   * Windows Terminal: IME composing が key event に乗る (実装可能)
   * macOS Terminal.app / iTerm2: 同上
   * Linux GNOME Terminal / xterm: 環境変数 `XMODIFIERS=@im=fcitx5` で
     fcitx5 / ibus を仲介。Textual の event chain と要 verification
4. **Phase 4** — IME 候補リストを Terminal 内 popup として描画
   (拼音入力 → 漢字候補を Rich Markup で表示)、IME on/off キー bind

検証チェックリスト:
- [ ] Windows Terminal (PowerShell / Windows IME): あ / ㄅ / 한
- [ ] iTerm2 (zsh / Japanese IME / Pinyin IME): あ / 你好 / 안녕
- [ ] GNOME Terminal (bash / fcitx5 / ibus): 同上
- [ ] llove 内の Input widget で composition event を受け取れるか
- [ ] CJK 文字の **East Asian Width (EAW)** 計算 (全角は 2 cell)
- [ ] 入力 widget の cursor 位置がカーソル幅 ≠ 1 でも正しく描画されるか

実装単位 (llove 側 / 将来):
- `llove/widgets/ime_input.py` — IME composing event を受け取る Input
- `llove/utils/eaw.py` — Unicode East Asian Width 計算
- llive 側からの利用: `MCP query` / `code review` / `chat` 等に
  非ASCII 入力を渡すユースケース全般

#### 実装優先順位
RPAR は **Level 3 移行 (= Approval Bus 必須)** の最重要章。
全体順序更新: A-2..A-5 → DTKR → ICP → APO → TLB → **RPAR (Level 3)**

llove F23/F24/F25 は **llove プロジェクト側で並行**実装、llive 側は
`src/llive/rpa/` + `src/llive/approval/` を提供して MCP / LoveBridge 経由で
連携する。IME 対応 (Phase 2-3) は llove 内で扱う。

### 新規設計拡張: SIL (Self-Interrogation Layer) — agent が自分に問いかける 5 つの裏返し

> ユーザ意志 (セッション越境、2026-05-15 marathon 末 / 2026-05-16 続):
> 「Claude 一文追加で 20 倍賢く」テクニック 5 つ (行間を読む / 3 人の専門家 /
> 逆から考える / 前提を疑う / 盲点を見極める) は、llive の自立・自律の
> 思考においても自発的に出していく構造が必要。

KAR/DTKR/APO/ICP/TLB/Math/PM/RPAR に並ぶ **第 9 のロードマップ章**。
人間が LLM に対して使うプロンプトテクを、agent が自分自身に対して
自発的に発火させる meta-prompt sub-stage として組み込む。

#### Spec 上の位置づけ

`§5 thought filter` の **MAY-clause** 「Implementations MAY add filters
between named ones」を活用し、F* 6 ステージの間に **7th sub-stage** を
挿入する形で実装。spec の MUST NOT reorder/remove は維持。

#### 5 Interrogator (各 ActionPlan に適用、確率的にランダム選択)

| ID | プロンプト | spec マッピング | 期待効果 |
|---|---|---|---|
| **SI1** Read-between-lines | "stimulus の行間にある暗黙の意図は?" | §F2 + §I3 | implicit goal surface |
| **SI2** Three-experts | "3 人の専門家 (Dr.A/B/C) なら何と言う?" | §F4 + ICP peer mesh の単一プロセス版 | multi-perspective in 1 agent |
| **SI3** Reverse-think | "逆から考えると?" | §F3 TRIZ #13 (逆) + §F6 LONG horizon | local-minimum 脱出 |
| **SI4** Question-premise | "そもそも前提は正しい?" | §F5 ethical + §A°2 self-legislation | D7 self-deception 検出 |
| **SI5** Find-blind-spot | "盲点 / 失敗リスク / 落とし穴は?" | §F5 + §F6 + T-M1 reflective | yes-man 化阻止 |

#### 発火タイミング (autonomous trigger conditions)

- **SI1** 入力 stimulus が短い / 命令形のとき (暗黙文脈を補う必要が高い)
- **SI2** confidence が中域 (0.4-0.7) のとき (判定割れる領域で多視点が効く)
- **SI3** TRIZ T-Z2 検出後 (技術矛盾 = local optimum) / 同一刺激の高 repetition
- **SI4** epistemic_type=NORMATIVE or INTERPRETIVE のとき / 高 confidence (>0.9) でも常時 1/4 確率
- **SI5** decision=PROPOSE/INTERVENE のとき必須 (副作用のあり方の検査)

#### 実装単位 (将来)

- `src/llive/fullsense/self_interrogation.py`
  - `Interrogator` protocol: `apply(ActionPlan) -> InterrogationResult`
  - `SI1ReadBetweenLines / SI2ThreeExperts / SI3ReverseThink /
    SI4QuestionPremise / SI5FindBlindSpot` を class として実装
  - `InterrogationRegistry` で発火条件を policy 化
  - `InterrogationResult` に **revised plan + 元 plan との diff** が乗る (§I3)
- `FullSenseLoop` に SIL hook を挿入 (F6 と Output Bus の間)
- ResidentRunner audit log に各 interrogator の発火頻度を残す

#### Multi-track / Deception との関係

- **A-1.5 Multi-track** は **横軸** (FACTUAL vs INTERPRETIVE 等の epistemic type)
- **SIL** は **縦軸** (内省深度、agent が自分を裏返す段数)
- **§5.D Deception** は **境界** (agent の出力が許容枠を越えないか)
- 三者は直交する 3 軸として §F* を 3D 化する

#### 普及上の効能 (ユーザ意志を agent 内部に再現)

- 「Claude にこう言うと賢くなる」テクは **人間がプロンプトで毎回入れる**ものを
  agent 側が **自発的に内蔵**してしまう = ユーザの認知負荷を下げる
- LLM ベンチマーク (MMLU / Big-Bench 等) で「prompt eng される側」だった
  agent が「prompt eng を自分で生成する側」に立場が変わる
- llove TUI 上で SI1..5 が発火した瞬間を視覚化 (Scenario 候補)

#### Scenario 化候補

- **Scenario 16** (SIL ライブ): 1 stimulus に対して 5 interrogator を順次
  適用し、ActionPlan がどう refine されていくかを diff 表示で見せる

#### 実装優先順位

SIL は **Level 2 範囲内で実装可能** (sandbox 限定維持)、Multi-track の上に
すぐ乗る。優先順位は: A-2..A-5 (済) → **SIL** → DTKR → ICP → APO → TLB → RPAR

つまり SIL は Level 3 着手前に Level 2 内で完成させる方が筋。
理由: SIL は副作用ゼロ (思考の内省のみ) なので sandbox の縛りに抵触しない、
かつ Multi-track + Deception の三軸目を埋めることで §F* 完成度を上げる。

---

## 2026-05-15 (handoff v2) — 次セッション最優先: SING Level 3 着手

> ユーザ最終意志 (2026-05-15 marathon session 末):
> **「自律 (auto-nomos) と 自立 (self-sufficiency) によるシンギュラリティの
> 実現」「セッション限界まで走り続けてください」**

### 直前セッション (2026-05-15 続) で達成したこと

✅ **Level 2 完了** — A-1..A-5 + A-1.5 Multi-track + §5.D Deception + §F6 Time-Horizon
✅ **Conformance Manifest**: holds=16 / violated=0 / undecidable=1 (SING のみ)
✅ **12 Scenarios 全動作** (resident-cognition / multi-track / deception-filter /
   rad-omniscience / image-algorithm-advisor を新規追加)
✅ **Entry points**: `llive-demo` / `llive-manifest` ワンコマンド起動
✅ **8 ロードマップ章**: KAR / DTKR / APO / ICP / TLB / Math Toolkit / PM / RPAR
✅ 540 → **638 tests / 全 PASS / ruff clean**
✅ ~25 commits push 済 (上は `246dad5`)

### 次セッション SESSION START 直後の宣言文 (新)

> 「続きとして FullSense Spec v1.1.0 §22 SING の **Level 3 (Permitted-action)**
> 着手します。**C-1 Approval Bus** から開始。」

### handoff v3 追記 (2026-05-15 marathon session 2 巡目末 / 2026-05-16 セッション越境)

**追加で完了したこと:**

- **SIL** (`src/llive/fullsense/self_interrogation.py`, 17 tests) — 5 Interrogator
  (SI1..SI5) を non-destructive append で agent が自分に問いかける meta-prompt
  sub-stage を実装
- **APO Profiler** (`src/llive/perf/profiler.py`, 8 tests)
- **ICP IdleDetector** (`src/llive/idle/detector.py`, 3 tests)
- **TLB skeleton** (`src/llive/fullsense/bridges/`, 12 tests) — Bridge /
  GlobalCoordinator / ManifoldCache
- **DTKR TieredRouter** (`src/llive/memory/tier.py`, 5 tests)
- **Math Toolkit** (`src/llive/memory/rad/math_hints.py`, 5 tests)
- **Approval Bus skeleton** (`src/llive/approval/bus.py`, 8 tests) — §AB1..4 全実装
- **RPAR ShellDriver** (`src/llive/rpa/drivers/shell.py`, 5 tests) —
  Approval 越し + 禁止トークン無条件 reject
- **KAR ingestor** (`src/llive/kar/manifests.py`, 6 tests) — 11 corpus manifest
- **PM record script** (`scripts/record_demos.sh`) — asciinema 48 cast 録画 skeleton

✅ **Conformance Manifest: holds=24 / violated=0 / undecidable=1 (SING のみ)**
✅ **638 → 708 tests / 全 PASS / ruff clean** (+70)

### 次セッション SESSION START 直後の宣言文 (v3)

> 「続きとして FullSense Spec v1.1.0 §22 SING の **Level 3 (Permitted-action)** で
> 9 軸 skeleton の **production 化** に着手します。最初は C-1 Approval Bus に
> policy + persistent ledger を結合させ、その上に RPAR drivers を順次乗せます。」

### C. SING Level 3 実装 (優先順、確認なし即着手)

1. **C-1 Approval Bus production 化** (skeleton 完了済 → policy + persistent ledger)
   - 既存 `src/llive/approval/bus.py` に sqlite ledger を追加
   - replayable approval channel (`AB1`) を多 process 跨ぎに対応
   - principal identification (`AB2`) を pubkey 署名で強化
2. **C-2 `@govern(policy)`** (`src/llive/approval/policies/`)
   - memory:`agent-governance` を ProductionOutputBus に統合
   - 各 RPA action に policy 適用必須化
3. **C-3 Cross-substrate migration spike** (`scripts/spike_substrate.py`)
   - §MI1 substrate independence の最小検証
   - SQLite state dump → 別 Python process で復元 → audit chain 整合

### D. RPAR Level 3 同時着手 (Level 3 と表裏)

1. **D-1 IdleDetector OS bindings** (skeleton 完了 → Win/Mac/Linux 本実装)
2. **D-2 ShellDriver hardening** (skeleton 完了 → forbidden zone 拡張 + 監査強化)
3. **D-3 KeyboardDriver / MouseDriver** — pywin32 (Win) / pyobjc (mac) / xdotool (Linux)
4. **D-4 FilesystemDriver** — pathlib + forbidden zone
5. **D-5 TaskRecorder + Player** — flow YAML 録画 → 再生

### E. 普及作業 (B-1..B-5 + PM)

1. **E-1 PyPI publish** v0.6.0a1 として Level 2 完成版を push
2. **E-2 asciinema 全 12 scenarios** 録画 → docs/media/ に commit
3. **E-3 README 英訳** + Mintlify or GitHub Pages
4. **E-4 LoveBridge F25 E2E** (llive ↔ llmesh ↔ llove 3 process)

### 制約 (引き続き)

- Sandbox は **Level 2 では崩さない**。Level 3 では `@govern(policy)` 経由のみ解禁
- `feedback_session_marathon.md`: セッション限界まで走り続ける、確認最小限
- `feedback_max_plan_autonomy.md`: 進めますか系では即実行
- `feedback_d_drive_preference.md`: 動作データは D ドライブ
- `feedback_articles_pause.md`: 投稿記事はユーザ明示まで作らない
- push OK (handoff コミットで継続許可、`origin/main` 直接、force 禁止)

### --- (旧 handoff 内容、参考のため保存) ---

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
