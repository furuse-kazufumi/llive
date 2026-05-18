# llive 用語集

> v0.1 + v0.2 で導入された全用語の完全リスト。略語、対応英文、初出文書、関連用語を相互リンク。

## A

### Adapter
sub-block / layer 単位で挿入される **差分重み**。LoRA / IA3 / DoRA 等を含む包括的呼称。
- 関連: [AdapterProfile](#adapterprofile), [Signed Adapter](#signed-adapter), [Parameter Memory](#parameter-memory)
- 初出: requirements_v0.1 § 用語定義

### AdapterProfile
Adapter のメタデータ + 重み + 評価結果 + 署名を 1 セットにした永続エンティティ。
- 関連: [SBOM](#sbom), [Signed Adapter](#signed-adapter)
- 初出: data_model.md § 2.6

### Aggregate (DDD)
ドメイン駆動設計の集約概念。llive では **1 概念 = 複数 MemoryNode の集合** に適用。
- 初出: requirements_v0.2_addendum § 3

### ARIZ
Algorithm of Inventive Problem Solving。TRIZ の体系的問題解決アルゴリズム。
- 初出: triz-ideation スキル

## B

### Block Container
Transformer block 相当の処理単位。複数 sub-block を持つ可変長コンテナ。
- 関連: [Sub-block](#sub-block), [Composite pattern]
- 初出: requirements_v0.1

### Backward Transfer (BWT)
継続学習で旧タスク精度の変化量。 $ \text{BWT} = \frac{1}{K-1}\sum_{j=1}^{K-1} (a_{K,j} - a_{j,j}) $
- 初出: evaluation_metrics § 3.2

## C

### Candidate
構造進化の単位。`CandidateSpec` + `CandidateDiff` で表現。
- 関連: [CandidateDiff](#candidatediff), [Evolution Manager](#evolution-manager)

### CandidateDiff
candidate を表現する差分仕様。`ChangeOp` の配列。
- 初出: yaml_schemas.md § 4

### Candidate Arena (FR-20)
llove F16 マルチゲームアリーナ抽象を **candidate vs candidate** の継続学習対局に転用した評価環境。Elo / TrueSkill で ranking。
- 初出: requirements_v0.2_addendum § 1

### CQRS
Command Query Responsibility Segregation。read / write を分離するパターン。Memory Fabric で適用。
- 初出: requirements_v0.2_addendum § 3

### Composite Pattern
木構造を一様に扱うパターン。BlockContainer の nested_container に適用。
- 初出: requirements_v0.2_addendum § 3

### Consolidation
Episodic memory を Semantic / Structural / Parameter memory へ replay-based に凝集する処理。
- 関連: [Hippocampal Consolidation Scheduler](#hippocampal-consolidation-scheduler), [FR-12]
- 初出: requirements_v0.2_addendum

### Core Model
ベースとなる Decoder-only LLM。固定運用。
- 初出: requirements_v0.1 § 用語定義

## D

### Dead Block
N 回の推論で一度も発火しなかった sub-block。prune 候補。
- 初出: evaluation_metrics § 5.1

### Decoder-only LLM
Transformer Decoder のみで構成された自己回帰言語モデル。Qwen, Llama, GPT 系等。
- 初出: requirements_v0.1

## E

### Episodic Memory
時系列イベント列としての経験記憶層。append-only。
- 関連: [Event Sourcing](#event-sourcing)
- 初出: requirements_v0.1 § 用語定義

### Event Sourcing
状態を append-only event の積分として表現するパターン。Episodic memory で適用。
- 初出: requirements_v0.2_addendum § 3

### Evolution Manager
構造候補の生成・評価・昇格・rollback を担う制御層 (L6)。
- 関連: [Saga](#saga), [State pattern]
- 初出: requirements_v0.1

## F

### Failed-Candidate Reservoir (FR-15)
rejected candidate の `(diff, failure_mode, score_vector)` を保持する専用記憶層。mutation policy の学習データ化。
- 初出: requirements_v0.2_addendum

### Forgetting Score
継続学習で旧タスク精度がどれだけ落ちたかの指標。BWT の負側。
- 初出: requirements_v0.1 / evaluation_metrics § 3.2

### Forward Transfer (FWT)
継続学習で未来タスクへの正の転移。
- 初出: evaluation_metrics § 3.3

## H

### Hexagonal Architecture (Ports & Adapters)
Domain を I/O から分離するアーキテクチャパターン。llive 全体の原則 P-01。
- 初出: requirements_v0.2_addendum § 3

### Hippocampal Consolidation Scheduler (FR-12)
海馬-皮質 consolidation cycle を模した周期処理。online は episodic write、夜間 batch で semantic / parameter へ replay 凝集。
- 関連: [Consolidation](#consolidation), [neural_signal_corpus]
- 初出: requirements_v0.2_addendum

### HITL (Human-In-The-Loop)
人間レビューを介在させる仕組み。llive では昇格前 staging + llove TUI で実装。
- 初出: requirements_v0.1 FR-11

## L

### llive
本プロジェクトの名称。Self-evolving modular memory LLM framework。PyPI 名は `llmesh-llive`。
- 関連: [llmesh](#llmesh), [llove](#llove), [llmesh-suite](#llmesh-suite)

### llmesh
マルチプロトコル LLM ゲートウェイ。MQTT / OPC-UA / 産業 IoT 対応。llive の memory backend として接続可能。
- 関連: [Sensor Bridge](#llmesh-sensor-bridge-fr-19)

### llmesh-suite
llmesh + llove のメタパッケージ。将来 llive も追加予定。

### llmesh Sensor Bridge (FR-19)
llmesh sensor stream を llive episodic memory へ直接書込む統合点。
- 初出: requirements_v0.2_addendum

### llove
TUI ベース dashboard。memory link 可視化と HITL レビューに利用。
- 関連: [Candidate Arena](#candidate-arena-fr-20)

## M

### Memento Pattern
状態スナップショットを保持してロールバックを可能にするパターン。Evolution Manager で適用。
- 初出: requirements_v0.2_addendum § 3

### Memory Fabric
4 層メモリ (semantic / episodic / structural / parameter) を統合する Layer 5。
- 初出: requirements_v0.1

### Memory Pollution Ratio
retrieve しても答えに寄与しなかった node の割合。
- 初出: evaluation_metrics § 6.1

### Memory Phase Manager (FR-16)
episodic → semantic → archive → erase の段階遷移を管理。
- 初出: requirements_v0.2_addendum

### Microkernel Architecture
コアカーネル + プラグインで構成するパターン。llive 全体の原則 P-02。
- 初出: requirements_v0.2_addendum § 3

### Multi-precision Shadow Evaluation (FR-14)
INT8 / 4bit で並列評価し上位のみ FP16 本評価する評価帯。
- 初出: requirements_v0.2_addendum

## P

### Parameter Memory
Adapter / LoRA / 差分重みを管理する記憶層。
- 関連: [AdapterProfile](#adapterprofile), [Signed Adapter](#signed-adapter)
- 初出: requirements_v0.1 § 用語定義

### Provenance
出所・根拠・署名を含むメタデータ。全永続エンティティに必須。
- 初出: data_model § 1

### Pipes & Filters
パイプライン構成パターン。L2 推論経路で適用。
- 初出: requirements_v0.2_addendum § 3

## Q

### Quarantined Memory Zone (FR-17)
untrusted source からの write を隔離するメモリ zone。cross-zone read には署名検証必須。
- 関連: [Signed Adapter](#signed-adapter)
- 初出: requirements_v0.2_addendum

## R

### RAD (Research Aggregation Directory)
Raptor の論文・文書コーパス。約 6.5 万 documents、30+ 分野。
- 関連: [project_corpus_overnight_2026_05_12](memory)

### Reverse-Evolution Monitor (FR-22)
forgetting score 悪化方向の変更を自動 rollback する継続監視機構。
- 関連: [Memento](#memento-pattern), [Saga](#saga)
- 初出: requirements_v0.2_addendum

### Router
入力特徴と context から container / sub-block / adapter / memory policy を決定する機構。
- 初出: requirements_v0.1 § 用語定義

## S

### Saga Pattern
多段トランザクションを補償付きで実行するパターン。Evolution の promote / rollback で適用。
- 初出: requirements_v0.2_addendum § 3

### SBOM (Software Bill of Materials)
ソフトウェアの構成成分一覧。CycloneDX 形式を採用。
- 初出: security_model § 4

### Semantic Memory
埋め込み検索主体の知識記憶層。
- 初出: requirements_v0.1 § 用語定義

### Signed Adapter
Ed25519 署名 + SBOM manifest を持つ adapter。llmesh 経由で P2P 配布可能。
- 関連: [FR-18 Signed Adapter Marketplace]
- 初出: requirements_v0.2_addendum / security_model § 4

### Static Verifier (FR-13)
candidate spec の構造的不変量を Lean / Z3 / TLA+ で機械検証する pre-LLM gate。
- 初出: requirements_v0.2_addendum

### Structural Memory
グラフ構造・依存関係中心の記憶層。
- 初出: requirements_v0.1 § 用語定義

### Sub-block
attention / FFN / memory_read 等の再利用可能な最小機能要素。
- 初出: requirements_v0.1 § 用語定義

### Surprise Score
想定外度・既存知識での説明困難度を示す指標。memory write の閾値判定や route depth に利用。
- 関連: [Surprise-Bayesian Write Gate (FR-21)]
- 初出: requirements_v0.1 § 用語定義

### Surprise-Bayesian Write Gate (FR-21)
surprise score を scalar から Bayesian uncertainty に拡張した write gate。動的閾値。
- 初出: requirements_v0.2_addendum

## T

### TRIZ
Theory of Inventive Problem Solving。発明的問題解決理論。40 原理 + 39×39 矛盾マトリクス + ARIZ + 9 画法。
- 初出: triz-ideation スキル

### TTL (Time To Live)
記憶ノードの有効期限。Memory Phase Manager の archive / erase 判定に使用。

## Y

### YAML schema
ContainerSpec / SubBlockSpec / CandidateDiff の宣言形式。JSON Schema Draft 2020-12 で検証。
- 初出: yaml_schemas.md

## Z

### Zero-cost proxy
学習なしで candidate 性能を予測する代替指標群（NAS 文脈）。llive では Static Verifier + Multi-precision Shadow Eval が代替。
- 初出: requirements_v0.1

## v0.8 Cognitive Mesh 用語 (2026-05-18 追加)

### Proactive Loop
`FullSenseLoop` を自発的に起動する周期/イベント駆動ループ。4 モード
(timer / event / curiosity / consistency)。能動発話の出口。
- 初出: requirements_v0.8_cognitive_mesh / COG-MESH-06
- 関連: Quiet Hours / Gift Value / Default Mode Network

### Quiet Hours
時刻に基づいて能動発話・自律実装・周期トリガを抑止する時間帯。
env `LLIVE_QUIET_HOURS_*` で設定。**fail-closed** (時刻取得失敗 / TZ 不明 /
env 欠落のいずれでも抑止側に倒す)。
- 初出: requirements_v0.8_cognitive_mesh / COG-MESH-07
- 既定: JST 22:00 - 翌 08:00

### Quiet Hours Guard
Quiet Hours 判定を提供するクラス。`ProactiveLoop` / `IdleTrainingScheduler`
の **必須依存** (コンストラクタで注入されないと起動失敗)。
- 公開 API: `in_quiet_hours()`, `next_active_window()`, `allow(category)`

### Gift Value
能動発話の「プレゼントとしての価値」を 4 因子 (novelty / relevance /
risk_avoidance / cost_to_listener) で見積もる発話前 gate の出力。
低価値発話は **黙る**。
- 初出: requirements_v0.8_cognitive_mesh / COG-MESH-05
- 由来: 「プレゼンテーション = プレゼント」語源論 (user_cognitive_mesh_model §14)

### Foreshadow / Title Recall
起承転結の「起」段で立てた **伏線 Annotation**。`TitleRecallPlanner` が
「結」段で recall_rate (0..1) を採点。プレゼン品質指標。
- 初出: requirements_v0.8_cognitive_mesh / COG-MESH-02
- Annotation namespace: `cog.foreshadow_set`, `cog.foreshadow_recovered`

### Tonic Risk Monitor
別スレッドで常時動く危険予測 (KYT 風)。閾値超で `ApprovalBus.intervene`
を能動 emit。**小脳的常時 KYT** の architectural 反映。
- 初出: requirements_v0.8_cognitive_mesh / COG-MESH-03
- エッジ実装: 別チップ (NPU / MCU) も視野

### Idle Training Scheduler
Quiet Hours 外の空き時間に外部情報源 (RSS / arXiv / GitHub trending /
RAD 差分) を ingest し、Quarantined Memory + Ed25519 経由で semantic
memory へ lift。
- 初出: requirements_v0.8_cognitive_mesh / COG-MESH-04
- 安全境界: SEC-01/02 経由必須

### Brief Deque / Brief Map / Brief Tree
flat list ではなく **入れ替え可能 + ブランチ分岐対応** の STL 相当
コンテナ群でセッションを保持。`MultiBriefCoherenceManager` の内部表現。
- 初出: requirements_v0.8_cognitive_mesh / COG-MESH-08
- 由来: ユーザ「STL コンテナ」言語化 (user_cognitive_mesh_model 追記)

### Multi-Brief Coherence Manager
複数 Brief を並列保持し、相互更新する coherence_graph (networkx)。
Annotation Channel `cog.cross_brief_impact` を emit。
- 初出: requirements_v0.8_cognitive_mesh / COG-MESH-01
- 由来: ユーザ「頭の中に複数セッションが常にある状態」(認知モデル §11)

### Grammar Layer
固定埋め込みでなく **継続学習対象** としての文法層。時代変化を追跡
(`grammar_v_2020`, `grammar_v_2026`)、自己進化 (EVO-04/06/07) と接続。
言語別 (ja / en / zh / ko) に独立 layer。
- 初出: requirements_v0.8_cognitive_mesh / COG-MESH-09

### Mesh 5W1H
思考の 5W1H メッシュ表現。ノード = Who / What / When / Where / Why / How。
Annotation Channel namespace `mesh.{who,what,...}` に対応。
- 初出: requirements_v0.8_cognitive_mesh / COG-MESH-10
- 由来: ユーザ「思考が 5W1H メッシュ状に繋がる」(認知モデル §12)

### Granularity Hierarchy (言語化粒度階層)
内部表現で並走する 6 階層: word < phrase < clause < sentence < paragraph
< topic。各粒度で異なる更新コストとブランチ確率を持つ。
- 初出: requirements_v0.8_cognitive_mesh / COG-MESH-10
- 由来: ユーザ「単語 / 句 / 文節 / 文 / 段 / 主題」(認知モデル 追記 22:55)

### Default Mode Network (DMN)
人間の脳が idle 時に自発的に activate する神経回路。llive の能動発話
モードは DMN 相当の architectural 写像。
- 出典: feedback_brain_like_trigger_periodic / feedback_proactive_llm_speech
- 関連: ProactiveLoop curiosity mode

## 略語一覧

| 略語 | 正式 |
|---|---|
| BC | BlockContainer |
| BWT | Backward Transfer |
| CABT | Cognitive-aware Transformer Block (v0.8 低レイヤ要件群) |
| CL | Continual Learning |
| COG-MESH | Cognitive Mesh (v0.8b 高レイヤ要件群) |
| CQRS | Command Query Responsibility Segregation |
| DMN | Default Mode Network |
| EDA | Event-Driven Architecture |
| ES | Event Sourcing |
| FR | Functional Requirement |
| FWT | Forward Transfer |
| HITL | Human-In-The-Loop |
| IFR | Ideal Final Result (TRIZ) |
| KYT | 危険予測 (Kiken Yochi Training) |
| LoRA | Low-Rank Adaptation |
| MoE | Mixture of Experts |
| NAS | Neural Architecture Search |
| NFR | Non-Functional Requirement |
| RAD | Research Aggregation Directory |
| RAG | Retrieval-Augmented Generation |
| SBOM | Software Bill of Materials |
| SLO | Service Level Objective |
| SPC | Statistical Process Control |
| SWR | Sharp-Wave Ripple (海馬の replay 信号) |
| TUI | Text User Interface |
| TZ | Time Zone |
