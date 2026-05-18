# llive 要件定義 v0.8 — Cognitive Mesh / Proactive Loop / Quiet Hours

**Drafted:** 2026-05-18
**Status:** **要件追加（実装は段階的、Phase 5 で骨格 / Phase 6 以降で本格化）**
**Type:** Cognitive architecture addendum (proactive / multi-session / safety)
**Trigger:** ユーザ言語化「主セッション＋複数並列＋5W1Hメッシュ＋伏線回収＋小脳的KYT」と
能動発話・周期トリガ・Quiet Hours の三点セット (2026-05-18 一連メモ)

---

## 0. 経緯と本書の位置づけ

> **書誌的注記**: 本書 (`docs/requirements_v0.8_cognitive_mesh.md`) は
> `docs/requirements_v0.[1-7]*.md` シリーズの続巻として置く。GSD ワークフロー
> 用の `.planning/REQUIREMENTS.md` には別途 **v0.8 CABT** (Cognitive-aware
> Transformer Block 群) が定義されており、本書 (cognitive mesh) とは
> **直交する別レイヤ**である:
>
> - `.planning/REQUIREMENTS.md` の v0.8 CABT = **Transformer ブロック内部**の
>   attention / routing / token を認知的に拡張する低レイヤ
> - 本書 v0.8 cognitive mesh = **FullSenseLoop の周囲**で並列 Brief / 能動発話 /
>   Quiet Hours を扱う高レイヤ
>
> CABT と COG-MESH は補完関係。`.planning/REQUIREMENTS.md` 側にも本書要件を
> `v0.8b COG-MESH 群` として転記する (本書 §11 参照)。

2026-05-18 のセッションでユーザ自身が認知モデルを言語化し、また Claude Code /
llive に対する **能動性 / 周期性 / 静音時間帯** の要望を一連で出した。出典:

- `user_cognitive_mesh_model` (主セッション＋複数並列＋5W1Hメッシュ＋伏線回収＋小脳的KYT＋STLコンテナ＋6階層粒度＋文法層)
- `feedback_brain_like_trigger_periodic` (脳の周期振動と Default Mode Network)
- `feedback_proactive_llm_speech` (能動発話 4 パターン: timer / event / curiosity / consistency)
- `feedback_quiet_hours` (就寝時間帯の能動行動抑止、env `LLIVE_QUIET_HOURS_*`)
- `project_proactive_llive_demo` (「勝手に話しかけてくる llive」デモ)
- `feedback_response_timing` (完璧主義の抑制、70 点で出す)

これらは「llive はクラウド AI には不可能な動きをする」という FullSense
ブランドの差別化軸 (`feedback_competitor_benchmark`) と直結する。
個別 feedback / project memory として埋もれさせず、**設計思想の中核要件**
として v0.8 に固定する。

v0.6 (Concurrency) / v0.7 (Rust Acceleration) と独立だが、Phase 5 以降で
それらの上に乗る。

---

## 1. 動機 — 人間が構造的に AI より優位な 3 点を埋める

ユーザの観察に基づき、llive が乗り越えるべき構造的ギャップ:

| 人間優位の側面 | LLM 既定 | llive で埋める手段 |
|---|---|---|
| 常時並列セッション | 1 セッション固定 | **COG-MESH-01** MultiBriefCoherenceManager |
| 長射程の伏線回収 | 1 セッション内のみ | **COG-MESH-02** TitleRecallPlanner |
| 小脳的常時 KYT | 明示コードが必要 | **COG-MESH-03** TonicRiskMonitor |
| 空き時間の自発学習 | 入力待ちで停止 | **COG-MESH-04** IdleTrainingScheduler |
| 発話前の価値見積もり | しゃべりすぎ | **COG-MESH-05** GiftValueEstimator |
| 周期駆動 (Default Mode Network) | 受動応答のみ | **COG-MESH-06** ProactiveLoop |
| 就寝中の沈黙 | 区別なし | **COG-MESH-07** QuietHoursGuard |
| ブランチ可能なセッション保持 | flat list | **COG-MESH-08** BriefDeque / BriefMap |
| 文法の時代変化への追従 | 固定埋め込み | **COG-MESH-09** GrammarLayer |
| 5W1H メッシュ表現 | 暗黙 | **COG-MESH-10** Mesh5W1H + 言語化粒度階層 |

FullSense 哲学「責任所在を architecture level に持ち込む」(CLAUDE.md グローバル
規約) の延長で、上記 10 点をプロンプト工学ではなく **クラスとプロトコル** で
解決する。

---

## 2. 戦略原則

| 原則 | 内容 |
|---|---|
| **倫理が architecture の一部** | Quiet Hours / Gift Value / Risk gating は後付けではなく `ProactiveLoop` の必須依存 |
| **意味論先行・最適化後追従** | v0.6/v0.7 と同じく Python 純粋実装で意味論を固めてから Rust 化検討 |
| **段階的能動性** | timer 駆動 → event 駆動 → curiosity 駆動 → consistency 違反駆動 の 4 段階で能動性を獲得 |
| **HITL ゲート維持** | 能動発話は ApprovalBus を迂回しない。`@govern` policy に proactive 通知用 channel を追加 |
| **fail-closed in Quiet Hours** | 時刻取得失敗 / TZ 不明 / Quiet Hours 設定欠落のいずれでも、自発行動は **抑止側に倒す** |
| **on-prem 完結** | 能動発話の content 生成は on-prem LLM のみで完結。cloud LLM 経由の能動発話は明示的 opt-in |
| **エッジ対応を意識** | Mesh / TonicRiskMonitor / Quiet Hours は MCU / NPU 上で動く軽量実装も視野に置く (`project_llmesh_neuro_long_term` と合流) |
| **完璧主義を architectural にも抑制** | 「未完成のまま出す」「70 点で commit」は design 工程にも適用、`feedback_response_timing` を docs / Brief level でも遵守 |

---

## 3. 要件 (COG-MESH-XX シリーズ)

### COG-MESH-01: MultiBriefCoherenceManager (Phase 5 候補)

複数 Brief を **並列保持** し、相互更新を可能にする。

- 内部状態:
  - `briefs: dict[BriefId, BriefRunner]`
  - `coherence_graph: networkx.Graph` (Brief 間の相互参照)
  - `update_interval: float` (tick 周期、既定 5 s)
- 公開 API:
  - `attach(brief: Brief) -> BriefId`
  - `detach(brief_id: BriefId)`
  - `tick() -> list[CoherenceEvent]` — 全 Brief の memory を読み、別 Brief への
    impact を計算、強い impact があれば Annotation Channel `cog.cross_brief_impact`
    で notify
  - `freeze(brief_id) / thaw(brief_id)` — 一時凍結
- 制約:
  - 各 Brief の thread-safe 性は v0.6 CONC-01 を継承
  - memory access はバッチ化、ロック粒度は Brief 単位
- 軽量実装ヒント:
  - 各 Brief 個別 state を持たず **共有メモリビュー** で表現できれば RAM 節約
  - `BriefDeque` / `BriefMap` (COG-MESH-08) に bind

### COG-MESH-02: TitleRecallPlanner (Phase 5 候補)

「起承転結 + 伏線回収 + タイトル回収」を実装に持ち込む。

- 起 (`setup`) 段で立てた **伏線 Annotation** を Channel に積む
- 結 (`closure`) 段で **回収率** (recall_rate) を 0..1 で採点
- 公開 API:
  - `setup(brief) -> list[Annotation]` (Foreshadow tag を必須)
  - `evaluate_recall_rate(brief) -> float`
  - `unrecovered_foreshadows(brief) -> list[Annotation]` (回収漏れ通告)
- 採点に使う特徴:
  - 伏線テキスト ⇔ 最終出力テキストの semantic similarity
  - 伏線 token の最終出力での出現
  - Annotation Channel `cog.foreshadow_recovered` の発火数
- 用途:
  - プレゼン品質指標 / 記事執筆 / ドキュメンテーション品質ゲート

### COG-MESH-03: TonicRiskMonitor (Phase 5-6)

別スレッドで常時動く危険予測。**主セッションに割込む権限**を持つ。

- 内部状態:
  - `risk_models: list[RiskModel]` (KYT ヒューリスティクス)
  - `interrupt_threshold: float`
  - `tick_interval: float` (既定 0.5 s)
- 公開 API:
  - `register(model: RiskModel)`
  - `start() / stop()`
  - `latest_scores() -> dict[ModelId, float]`
- 出力チャンネル:
  - `Annotation` namespace `cog.risk_alert`
  - 閾値超で `ApprovalBus.intervene(...)` を能動発話
- 軽量実装ヒント:
  - **別チップ (NPU / MCU)** で動かし、主 LLM とは非同期通信、というハード分割を視野
  - エッジ展開では `LLIVE_TONIC_RISK_BACKEND=mcu|cpu|gpu` env で切替

### COG-MESH-04: IdleTrainingScheduler (Phase 5)

Quiet Hours 外の空き時間に外部情報を ingest し semantic memory を拡張する。

- 内部状態:
  - `sources: list[InfoSource]` (RSS / arXiv / GitHub trending / RAD 差分など)
  - `quiet_hours_guard: QuietHoursGuard` (COG-MESH-07 必須依存)
  - `last_ingest: dict[SourceId, datetime]`
  - `idle_threshold_seconds: int` (既定 60)
- 公開 API:
  - `should_ingest() -> bool`
  - `tick()` — 条件成立時に 1 source を ingest
  - `pause() / resume()`
- 安全境界:
  - ingest した content は Quarantined Memory (SEC-01) に着地
  - PII redaction / Ed25519 Signed Adapter (SEC-02) を経て semantic に lift

### COG-MESH-05: GiftValueEstimator (Phase 5、ProactiveLoop の必須依存)

能動発話の **「プレゼントとしての価値」** を見積もる発話前ゲート。
低価値の発話は **黙る**。

- 公開 API:
  - `estimate(candidate_utterance: str, listener_state: dict) -> GiftValue`
  - `GiftValue` フィールド:
    - `novelty: float` (新規性、既出済発話との重複度の逆)
    - `relevance: float` (現在 brief / 主セッションへの関連性)
    - `risk_avoidance: float` (KYT 由来の重要度)
    - `cost_to_listener: float` (時刻 / 集中度合 / Quiet Hours 等の負荷)
    - `aggregate: float` (上記の重み付け、閾値で gate)
- 既定閾値: `aggregate >= 0.6` で発話、未満は **黙る**
- 副作用記録: 抑制した発話は `cog.suppressed_utterance` Annotation で残す
  (後でログ解析、過剰抑制を検出できるように)

> **由来**: ユーザ「プレゼンテーション = プレゼント、語源同じ。価値を提供
> しないといけない」(`user_cognitive_mesh_model` §14)。

### COG-MESH-06: ProactiveLoop (Phase 5、demo 品質先行)

`FullSenseLoop` を**自発的に**起動する周期/イベント駆動ループ。
能動発話 4 パターン (timer / event / curiosity / consistency) を統合。

- 内部状態:
  - `tick_interval: float` (既定 60-120 s)
  - `quiet_hours_guard: QuietHoursGuard` (必須)
  - `gift_value_estimator: GiftValueEstimator` (必須)
  - `mode: {timer, event, curiosity, consistency}`
- 公開 API:
  - `start() / stop()`
  - `register_event_source(src: EventSource)`
  - `latest_utterances(n) -> list[ProactiveUtterance]`
- 安全境界 (発話前 gate):
  1. Quiet Hours 中 → 抑止 (緊急 risk_alert を除く)
  2. GiftValueEstimator の閾値未満 → 抑止
  3. ApprovalBus が approval mode のとき → 人間に提示後 gate
  4. 直近同一発話 hash が cooldown 内 → 抑止
- demo 連携: `llive.demo.proactive` モジュールが本要件を最小実装で具体化
  (`project_proactive_llive_demo` Phase 0 が直接マップ)

> **由来**: `feedback_brain_like_trigger_periodic` (脳の周期振動と Default
> Mode Network) + `feedback_proactive_llm_speech` (4 パターン)。

### COG-MESH-07: QuietHoursGuard (Phase 5、最優先)

時刻に基づいて能動行動を抑止するガード。COG-MESH-04 / 06 の必須依存。

- 設定 env:
  - `LLIVE_TZ` (既定 `Asia/Tokyo`)
  - `LLIVE_QUIET_HOURS_START` (既定 22)
  - `LLIVE_QUIET_HOURS_END` (既定 8)
  - `LLIVE_QUIET_HOURS_ENABLED` (既定 1)
- 公開 API:
  - `in_quiet_hours(now: Optional[datetime] = None) -> bool`
  - `next_active_window() -> tuple[datetime, datetime]`
  - `allow(category: Literal["proactive", "ingest", "risk_alert", "audit_alert"]) -> bool`
- 抑止対象:
  - 能動発話 (COG-MESH-06)
  - 周期トリガからの自動 prompt 投入
  - 自律実装モードの長時間 commit ループ
  - HITL Approval Bus からの notification (Risk Score 高は例外)
- 許可対象 (Quiet Hours 中でも):
  - ユーザ明示の受動応答
  - 真に緊急の audit alert (`cross_border_warning` 等) は cooldown 後
  - セキュリティ脆弱性検知
- fail-closed: 時刻取得失敗 / TZ 不明時は **常に Quiet Hours 中扱い**

> **由来**: `feedback_quiet_hours`。Quiet Hours 違反 = 信頼破壊。一度でも
> 深夜に勝手に動いて環境を変えると信頼が崩れる。

### COG-MESH-08: BriefDeque / BriefMap (Phase 5)

セッション保持を flat list ではなく **入れ替え可能 + ブランチ分岐対応** の
STL 相当コンテナで設計する。

- `BriefDeque`: 両端 push/pop。最新主セッション + 直近サブセッションを高速操作。
- `BriefMap`: `topic -> Brief 配列` 多重マップ。主題による横断検索。
- `BriefTree`: ブランチ分岐構造 (1 Brief から複数 child Brief)。
- 公開 API:
  - `push_front(brief) / pop_front()`
  - `push_back(brief) / pop_back()`
  - `branch(parent_brief_id, child_brief) -> BriefId`
  - `merge(child_brief_ids) -> Brief` (子から親へ知見集約)
- COG-MESH-01 (MultiBriefCoherenceManager) の内部表現として採用

> **由来**: ユーザ「セッションをどのように持つかも重要。入れ替えや
> ブランチを考慮した STL で言うコンテナに入れないといけない」
> (`user_cognitive_mesh_model` 追記 22:55)。

### COG-MESH-09: GrammarLayer (Phase 6 候補、研究的)

固定埋め込みではなく **継続学習対象** としての文法層。
時代変化 (古典 ↔ 現代口語、若者言葉、新語) を追跡する。

- 内部状態:
  - `versions: dict[str, GrammarSnapshot]` (例: `grammar_v_2020`, `grammar_v_2026`)
  - `language: Literal["ja", "en", "zh", "ko", ...]`
  - `evolution_log: list[GrammarChangeEvent]`
- 公開 API:
  - `parse(text, version) -> ParseTree`
  - `propose_change(observation: UsageEvidence) -> ProposedChange`
  - `promote(change: ProposedChange) -> GrammarSnapshot` (EVO-04/06/07 と接続)
- 自己進化 (Phase 3 既存) と接続:
  - 新しい用法観測 → 候補追加 → 形式検証 → promotion のフローを共有
- 言語別実装: `ja` / `en` / `zh` / `ko` は v0.8 では別 layer (将来統合)

> **由来**: ユーザ「世界中の言語に文法があり、時代によって変化があるので
> 常に学習」(`user_cognitive_mesh_model` 追記 23:00)。

### COG-MESH-10: Mesh5W1H + 言語化粒度階層 (Phase 5)

思考の **5W1H メッシュ表現** と、6 階層の言語化粒度を明示的に持つ。

- メッシュノード: `Who`, `What`, `When`, `Where`, `Why`, `How`
- 各ノードは互いに edge を持ち、Annotation Channel の namespace
  (`mesh.who`, `mesh.what`, ...) に対応
- 言語化粒度 (内部表現で並走):
  1. **word** (単語)
  2. **phrase** (句)
  3. **clause** (文節)
  4. **sentence** (文)
  5. **paragraph** (段)
  6. **topic** (主題)
- 各粒度で異なる更新コストとブランチ確率を持つ
- llive 内部表現 (`Stimulus` / `Brief` / `Annotation` / `Thought`) を
  この階層に揃える検討フックを置く
- 公開 API:
  - `annotate_5w1h(text) -> Mesh5W1H`
  - `granularity_of(token) -> Granularity`
  - `link(from_node, to_node, weight)`

> **由来**: ユーザ「思考が 5W1H メッシュ状に繋がる」「単語 / 句 / 文節 / 文 /
> 段 / 主題」(`user_cognitive_mesh_model` §12, 追記 22:55)。

---

## 4. 既存 FR との対応・ギャップ表

| 既存 FR / 設計 | v0.8 で拡張する点 |
|---|---|
| FullSenseLoop (6 stage: salience → curiosity → thought → ego/altruism → plan → output) | **能動側 trigger** を `ProactiveLoop` が供給 |
| `_salience_gate` / `_curiosity_drive` | 内発的好奇心の探索発話 (`COG-MESH-06` mode=curiosity) で実装 |
| `_decide_action` PROPOSE/INTERVENE | 能動発話の出口、GiftValueEstimator gate を通る |
| Annotation Channel | `cog.proactive`, `cog.foreshadow_*`, `cog.cross_brief_impact`, `cog.suppressed_utterance` namespace 追加 |
| ApprovalBus | proactive 用 category 追加 (Risk Score でゲート) |
| Quarantined Memory (SEC-01) | IdleTrainingScheduler の ingest 着地点 |
| Ed25519 Signed Adapter (SEC-02) | ingest を semantic memory に lift する際の署名検証 |
| SqliteLedger (SEC-03) | proactive 発話・抑制・risk alert を hash chain で監査 |
| TRIZ 40 原理 (FR-23〜27) | アイデア起点トレーニングの素材として COG-MESH-04 から呼ぶ |
| 4 層メモリ (semantic/episodic/structural/parameter) | coverage 計算のソース (proactive のネタ源) |
| OKA-FX 岡潔フレームワーク | 情緒 / 行き詰まり / 文章化を proactive の発話品質に統合可能 |
| VRB-FX (MBA 言語化) | GiftValueEstimator の novelty / relevance 採点に活用 |
| COG-FX 10 思考因子 | TonicRiskMonitor / TitleRecallPlanner の特徴量に流用 |

---

## 5. 段階導入計画

### Phase 5 (v0.5.0) — 骨格

- COG-MESH-07 (QuietHoursGuard) — **最優先、最小実装**
- COG-MESH-05 (GiftValueEstimator) — 閾値ベース、特徴量は naive
- COG-MESH-06 (ProactiveLoop) — timer モードのみ、demo 品質
- COG-MESH-04 (IdleTrainingScheduler) — 1 source (RAD 差分) のみ
- COG-MESH-08 (BriefDeque / BriefMap) — 最小 dict + deque 実装

### Phase 5.x — demo 化

- `project_proactive_llive_demo` の Phase 0 を完了
- llove F25 連携経由で TUI 表示
- asciinema 録画 + LinkedIn / Qiita 公開素材化 (`project_f25_demo_polish` 整合)

### Phase 6 — 拡張

- COG-MESH-02 (TitleRecallPlanner) — 採点アルゴリズム実装
- COG-MESH-03 (TonicRiskMonitor) — KYT 3 model + 別スレッド
- COG-MESH-10 (Mesh5W1H + 粒度階層) — Annotation namespace 拡張
- COG-MESH-06 ProactiveLoop — event / curiosity モード追加

### Phase 7 — 研究的

- COG-MESH-01 (MultiBriefCoherenceManager) — coherence_graph 本実装
- COG-MESH-09 (GrammarLayer) — 言語別 layer 設計、自己進化と接続
- エッジ展開 (`project_llmesh_neuro_long_term` と合流)

---

## 6. 安全 / 倫理境界 (本書全体に適用)

| 懸念 | 対策 |
|---|---|
| 「話しかけすぎ」問題 | GiftValueEstimator (`COG-MESH-05`) + cooldown |
| prompt injection 増幅 | IdleTrainingScheduler の ingest 経路は Quarantined Memory + Ed25519 |
| 深夜の侵入 | QuietHoursGuard fail-closed |
| 暴走発話 | 発話 hash chain + 同一発話 cooldown |
| コンテキスト消費 | 周期トリガ毎の SESSION_SUMMARY ベース継続必須 |
| 長時間自律のドリフト | 帰宅後の議論モードで方向修正できる構造維持 |
| 「停止できない」状態 | `/rotate clear` / Stop hook clear / ProactiveLoop.stop() の 3 重停止 |
| 完璧主義による設計肥大 | `feedback_response_timing` を docs / Brief 工程でも適用、70 点で commit |

---

## 7. ベンチマーク方針 (FullSense portal `/benchmarks/policy/` 整合)

- 系列ラベル: **C 系列 (llive on-prem)** に proactive demo を載せる
- 段階測定: xs / s / m / l / xl で「黙る / 喋る」の比率を測る
- honest disclosure: 過剰発話 / 過剰抑制を必ず本文に残す
- ベースライン: GiftValueEstimator off (常時発話) vs on (gate 付き) を併記

---

## 8. Qiita / 論文ネタ (派生、`reference_article_idea_inventory` §9 に追加候補)

| タイトル候補 | クロス分野 | 訴求 |
|---|---|---|
| 「黙っている LLM に話しかけさせる: llive の能動発話アーキ」 | 認知科学 + アーキ | コンセプト記事 |
| 「Default Mode Network 相当の機能を LLM に持たせる」 | 脳科学 + アーキ | 学会論文 |
| 「クラウド AI には絶対できない『勝手に話しかける』ローカル AI」 | on-prem 差別化 | 普及論 |
| 「就寝中は黙る AI: Quiet Hours 設計」 | 倫理 + 実装 | 普及論 |
| 「人間の頭の中には常に複数セッションがある: llive MultiBrief 設計」 | 認知科学 + アーキ | 設計記事 |
| 「小脳的 KYT を LLM に持たせる: TonicRiskMonitor の設計」 | 脳科学 + 産業安全 | 学会論文 |
| 「プレゼン = プレゼント語源論 × LLM 能動発話の価値ゲート」 | 言語学 + アーキ | コンセプト記事 |
| 「エッジコンピュータで動く認知メッシュ AI の最小構成」 | エッジ + 軽量 LLM | 技術記事 |
| 「5W1H メッシュ思考を LLM 内部表現に持ち込む」 | 言語学 + アーキ | 研究 |
| 「伏線回収を意識する LLM: TitleRecallPlanner の論文化」 | 物語論 + ML | 研究 |

---

## 9. 関連文書

- `requirements_v0.1.md` 〜 `requirements_v0.7_rust_acceleration.md` — 既存要件群
- `architecture.md` — FullSenseLoop / 4 層メモリ / Annotation Channel
- `security_model.md` — SEC-01〜03 (Quarantined Memory / Signed Adapter / Ledger)
- `glossary.md` — Brief / Stimulus / Annotation / Thought の定義
- `proposals/brief_api_design.md` — Brief API (v0.7 完了)
- `fullsense_spec_eternal.md` — FullSense ™ 公式 spec
- maintainer memory (出典):
  - `user_cognitive_mesh_model`
  - `feedback_brain_like_trigger_periodic`
  - `feedback_proactive_llm_speech`
  - `feedback_quiet_hours`
  - `project_proactive_llive_demo`
  - `feedback_response_timing`
  - `feedback_autonomous_daytime_work`
  - `feedback_competitor_benchmark`
  - `feedback_llive_measurement_purity`
  - `project_f25_demo_polish`

---

## 10. 次アクション (本要件導入後の運用) — 進捗 checklist

要件導入後の運用 (2026-05-18 → 2026-05-19 早朝で達成):

- [x] `architecture.md` の章末に「v0.8 cognitive mesh 拡張ポイント」短セクションを追記 — **§8 として配備済**
- [x] `roadmap.md` の Phase 5 / 6 / 7 マイルストーンに COG-MESH-XX を割り付け — **Phase 8 として CABT と双子配備、Skeleton 完了状態反映済**
- [x] `glossary.md` に Proactive / Quiet Hours / Gift Value / Foreshadow / Mesh5W1H 用語を追加 — **24 用語 + 5 略語追加済**
- [x] `tests/` 配下に COG-MESH-07 (QuietHoursGuard) の単体テスト雛形を先行配備 — **11 シナリオで先行配備、その後本実装で全 PASS 化**

追加で達成 (2026-05-19 早朝の実装ラッシュ):

- [x] **COG-MESH-01〜10 全 10 件の最小実装** (107 新規テスト、1379 PASS、regress 無し)
- [x] 統合 demo CLI (`py -3.11 -m llive.cognitive_mesh.demo` で 5 サブシステム連動)
- [x] `__init__.py` で公開 API を整理 (`__all__` に 30+ シンボル)

次フェーズ (Phase 5/6/7 本実装):

- [ ] M8.1 ProactiveLoop を llove F25 経由で TUI 表示、asciinema 録画
- [x] M8.2 IdleTraining ingest を Quarantined Memory (SEC-01) +
      Ed25519 (SEC-02) と統合 — **完了 2026-05-19** (quarantined_memory.py +
      idle_training.quarantine 注入対応、16 件テスト追加)
- [x] M8.3 BriefDeque/Map/Tree を実 Brief / BriefRunner と接続 — **完了 2026-05-19**
      (brief_runner_bridge.BriefDequeRunnerBridge、6 件テスト)
- [x] M8.4 TitleRecall を semantic similarity (token match → embedding) で本実装
      — **完了 2026-05-19** (embedding_similarity.EmbeddingSimilarityFn +
      TitleRecallPlanner.similarity_fn 注入、9 件テスト)
- [x] M8.5 TonicRiskMonitor を threading 化 + ApprovalBus.intervene 配線
      — **完了 2026-05-19** (threading 化は 0878f81 で先行、
      intervention.RiskInterventionAdapter で配線、5 件テスト)
- [x] M8.6 Mesh5W1H を実 Annotation Channel と統合 — **完了 2026-05-19**
      (mesh_annotator.Mesh5W1HAnnotator、7 件テスト)
- [x] M8.7 ProactiveLoop に event / curiosity / consistency モード追加
      — **完了 2026-05-19** (ProactiveEvent / ConsistencyViolation +
      tick_event / tick_consistency + _on_timer 分岐、12 件テスト)
- [x] M8.8 MultiBriefCoherenceManager を networkx + 実 Brief 統合 —
      **完了 2026-05-19** (自前 BFS / DFS / centrality で先行、networkx
      は将来 swap 候補。`register_brief()` で実 Brief 統合、14 件テスト)
- [x] M8.9 GrammarLayer を EVO-04/06/07 と接続、言語別 layer 設計 —
      **完了 2026-05-19** (GrammarChangeSink Protocol + MultilingualGrammar
      で ja/en/zh/ko 自動 bootstrap、8 件テスト。EVO への実配線は Phase 7)

---

**Status:** **IMPLEMENTED-FULL — 2026-05-19, M8.2〜M8.9 本実装完了。
残るは M8.1 (llove TUI 統合) のみ — llove F25 連携基盤待ち。**

更新履歴:
- 2026-05-18: 要件追加 (DRAFT)
- 2026-05-19 早朝: COG-MESH-01〜10 全件 skeleton 完了 (IMPLEMENTED-SKELETON)
- 2026-05-19 朝: M8.2〜M8.7 本実装完了、1393 → 1448 PASS
- 2026-05-19 昼前: M8.8 + M8.9 本実装完了、1448 → 1470 PASS (IMPLEMENTED-FULL)

---

## 11. CABT との対応・統合視点

`.planning/REQUIREMENTS.md` v0.8 CABT (Cognitive-aware Transformer Block) と
本書 (cognitive mesh) は **直交するレイヤ** であり、両者を組み合わせて
初めて「人間の認知に並ぶ AI」が成立する想定。

| 側面 | CABT (低レイヤ) | COG-MESH (高レイヤ) |
|---|---|---|
| 対象 | Transformer ブロック内部 (attention / routing / token) | FullSenseLoop の周囲 (Brief / 発話 / 時刻) |
| 介入点 | forward pass の hook | Loop の tick / Stimulus 注入 / Annotation Channel |
| 例 | CABT-04 Salience-gated Attention | COG-MESH-03 TonicRiskMonitor |
| 例 | CABT-06 Approval-gated Decoding | COG-MESH-05 GiftValueEstimator |
| 実装段階 | Phase 8 (S2-S6 段階で導入) | Phase 5 (骨格) → Phase 6/7 (拡張) |
| 依存方向 | COG-MESH 6 から CABT 4 の surprise を参照する経路あり | 逆方向は基本不要 |

統合ポイント (将来):

- CABT-04 (Salience-gated Attention) の token-level surprise log は
  COG-MESH-06 ProactiveLoop の curiosity mode で発話ネタとして再利用可能
- CABT-06 (Approval-gated Decoding) の policy 違反 token sequence は
  COG-MESH-03 TonicRiskMonitor の RiskModel として登録可能
- CABT-07 (Memory-augmented Residual) の 4 層メモリ embedding は
  COG-MESH-04 IdleTrainingScheduler の ingest-coverage 計算に直接使える

> 結論: CABT と COG-MESH は分離して進める方が良い。両者の version 番号
> 衝突は **意図的** で、「同じ v0.8 期に着手すべき双子の要件群」を示唆。
