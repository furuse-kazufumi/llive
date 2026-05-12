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

## 略語一覧

| 略語 | 正式 |
|---|---|
| BC | BlockContainer |
| BWT | Backward Transfer |
| CL | Continual Learning |
| CQRS | Command Query Responsibility Segregation |
| EDA | Event-Driven Architecture |
| ES | Event Sourcing |
| FR | Functional Requirement |
| FWT | Forward Transfer |
| HITL | Human-In-The-Loop |
| IFR | Ideal Final Result (TRIZ) |
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
