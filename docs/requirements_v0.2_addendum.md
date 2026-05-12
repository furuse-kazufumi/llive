# llive 要件定義書 v0.2 追補章

> v0.1 (`requirements_v0.1.md`) に対する拡充。TRIZ 矛盾解消アイデア、設計パターン、llmesh / llove 統合、差別化軸を追加。

## 概要

v0.1 で明示された 3 つの矛盾に対し TRIZ ベースで原理を当て、拡張要件 FR-12〜FR-22 を導出した。あわせて、全体構造を 6 層 → **8 層**に再構成し、各層の責務をデザインパターンで明確化する。llmesh / llove との接続点を独立した層として位置付け、既存ファミリーとの統合を第一級要件とする。

---

## § 1. TRIZ 由来 拡張要件

### 矛盾 A: 安定 vs 速い適応

| 改善特性 | 悪化特性 | 物理的矛盾の分離 |
|---|---|---|
| #9 速度、#35 適応性 | #13 安定性、#27 信頼性 | **時間で分離** (online は安定優先、offline で適応) |

#### 採用 TRIZ 原理 → 拡張要件

| # | TRIZ 原理 | 拡張要件 ID | 内容 |
|---|---|---|---|
| #19 | 周期化 | **FR-12 Hippocampal Consolidation Scheduler** | online は episodic-write 主体、低負荷時間に episodic → semantic/structural/parameter への replay-based consolidation を実行 |
| #13 | 逆転 | **FR-22 Reverse-Evolution Monitor** | forgetting score 悪化方向の変更を自動 rollback、改善方向のみ二重審査で promote。`hidden_remap` sub-block でコア凍結のまま入力側を再射影 |
| #7 | 入れ子 | **FR-02 補強** | BlockContainer 内に nested mini-container を許容（条件下展開）。Composite パターンの再帰適用 |
| #22 | 災い転じて福 | **FR-12 拡張** | catastrophic forgetting の発生を「不要記憶 prune シグナル」として再利用 |

### 矛盾 B: 探索広い vs 評価コスト低い

| 改善特性 | 悪化特性 | 物理的矛盾の分離 |
|---|---|---|
| #35 適応性、#6 多用途性 | #25 時間の損失 | **条件で分離** (足切り帯 vs 本評価帯) |

#### 採用 TRIZ 原理 → 拡張要件

| # | TRIZ 原理 | 拡張要件 ID | 内容 |
|---|---|---|---|
| #24 | 仲介 | **FR-13 Static Verifier Layer** | candidate spec を Lean / Z3 / TLA+ の不変量にコンパイルし、LLM 評価前に構造的反例を機械検出 |
| #26 | コピー | **FR-14 Multi-precision Shadow Evaluation** | candidate を INT8 / 4bit で N 倍並列評価 → 上位のみ FP16 で本評価 |
| #23 | フィードバック | **FR-15 Failed-Candidate Reservoir** | rejected candidate を `(diff, failure_mode, score_vector)` として `candidate_episodic_memory` に保持、次回 mutation policy の学習データ化 |
| #18 | 振動 | **EP-04 補強** | 評価が頭打ちになった候補に温度スケジュール付き高分散変化を加え、探索範囲を周期的に拡大 |
| #6 | 多用途化 | **FR-04 補強** | 1 candidate を複数タスクで同時評価、task-conditioned router で 1 forward 内に N タスク混在 |

### 矛盾 C: 記憶増 vs 汚染 / 忘却抑制

| 改善特性 | 悪化特性 | 物理的矛盾の分離 |
|---|---|---|
| #26 物質の量 | #31 有害な副作用 | **空間で分離** (memory layer / zone ごとの policy) |

#### 採用 TRIZ 原理 → 拡張要件

| # | TRIZ 原理 | 拡張要件 ID | 内容 |
|---|---|---|---|
| #36 | 相変化 | **FR-16 Memory Phase Manager** | episodic → semantic 昇格、semantic → archive 降格、archive → erase の各 phase 遷移を独立スケジューラで管理 |
| #39 | 不活性雰囲気 | **FR-17 Quarantined Memory Zone** | untrusted source の write は `quarantine` zone に隔離、cross-zone read は `adapter_signed` 属性必須 |
| #24 + #39 | 仲介 + 不活性 | **FR-18 Signed Adapter Marketplace** | 各 adapter / candidate に Ed25519 署名 + SBOM manifest、llmesh ノード間で P2P 配布、署名検証なし load 拒否 |
| #35 | パラメータ変化 | **FR-21 Surprise-Bayesian Write Gate** | surprise score を scalar から Bayesian uncertainty (Variational / Ensemble) へ拡張、write 閾値 θ を動的設定 |
| #3 | 局所的性質 | **FR-05 補強** | semantic は厳格 dedup、episodic は時系列保持、structural は graph 一貫性、parameter は版管理、と layer ごとに pollution policy を変える |

### 矛盾横断: llmesh / llove 接続

| 拡張要件 ID | 名前 | 内容 |
|---|---|---|
| **FR-19** | llmesh Sensor Bridge | llmesh の sensor stream（温度 / 振動 / 電流 / カメラ）を episodic memory の非言語 channel として直接書込。LLM × 産業 IoT 完全閉ループ |
| **FR-20** | Candidate Arena (llove HITL) | llove F16 マルチゲームアリーナ抽象を candidate vs candidate の継続学習対局へ転用、Elo / TrueSkill で ranking、HITL レビューを TUI で完結 |

---

## § 2. 拡張要件まとめ表（v0.1 FR-XX への補強関係）

| 新 ID | 名前 | 由来 TRIZ 原理 | 関連 RAD コーパス | 補強する v0.1 FR |
|---|---|---|---|---|
| FR-12 | Hippocampal Consolidation Scheduler | #19, #22 | neural_signal, cognitive_ai | FR-05, FR-06 |
| FR-13 | Static Verifier Layer | #24 | formal_methods, automated_theorem_proving | FR-07 |
| FR-14 | Multi-precision Shadow Evaluation | #26 | tinyml, distributed_systems | FR-07, FR-08 |
| FR-15 | Failed-Candidate Reservoir | #23, #22 | reinforcement_learning | FR-07 |
| FR-16 | Memory Phase Manager | #36, #3 | cognitive_ai | FR-05, FR-06 |
| FR-17 | Quarantined Memory Zone | #39 | cryptography, hacker_corpus | FR-05, NFR-06 |
| FR-18 | Signed Adapter Marketplace | #24, #39 | cryptography | NFR-06 |
| FR-19 | llmesh Sensor Bridge | #6, #17 | industrial_iot, multimodal | EP-05 |
| FR-20 | Candidate Arena (TUI HITL) | #26, #18 | game_ai, reinforcement_learning | FR-10, FR-11 |
| FR-21 | Surprise-Bayesian Write Gate | #35 | neuromorphic, neural_signal | FR-06 |
| FR-22 | Reverse-Evolution Monitor | #13, #23 | reinforcement_learning, formal_methods | FR-07, FR-08 |

---

## § 3. 設計パターンと構造原則

### 全体アーキテクチャ原則

| 原則 ID | 名前 | 内容 |
|---|---|---|
| **P-01** | Hexagonal (Ports & Adapters) | Domain（model + memory + evolution）を中心、Ports = MCP / REST / llmesh / llove を外側に。単体テスト容易 |
| **P-02** | Microkernel | コアカーネル + プラグイン（sub-block / memory backend / mutation policy / modal encoder）。EP-01〜EP-05 の根拠 |
| **P-03** | Event-Driven Architecture | memory write / route decision / promotion event を全体で配信。**llmesh の MQTT を直接イベントバスに採用** |
| **P-04** | CQRS + Event Sourcing | memory 全層で read / write を分離、episodic は append-only event stream |
| **P-05** | Pipes & Filters | 推論経路全体（preproc → retrieval → router → container → write）を pipeline 化 |
| **P-06** | Actor Model | per memory zone, per candidate evaluation。並列・隔離 |
| **P-07** | Clean Architecture | Interface / Application / Domain / Infrastructure の依存方向固定 |

### コンポーネント別 パターン適用表

#### Layer 1: Interface
| パターン | 適用部位 | 効果 |
|---|---|---|
| Facade | CLI / Web / MCP / REST / Batch の I/F 統合 | 上位を単一エントリへ |
| Command | タスク投入 = Command オブジェクト化 | 再実行 / リプレイ / バッチ化 |
| Chain of Responsibility | auth → quota → validation → dispatch | 横断的関心の分離 |

#### Layer 2: Orchestration
| パターン | 適用部位 | 効果 |
|---|---|---|
| Pipes & Filters | preproc → retrieval → router → container → write | 各段独立、差し替え自在 |
| Mediator | container / router / memory / observability の調停 | 直接結合を防ぐ |
| Template Method | 推論パイプラインの共通骨格 | 経路分岐は hook で吸収 |

#### Layer 3: Core Model Adapter
| パターン | 適用部位 | 効果 |
|---|---|---|
| **Adapter** | HF Transformers / vLLM / TGI の差異吸収 (FR-01) | バックエンド切替 |
| Proxy | lazy loading / device dispatch / precision 自動選択 | 透過的最適化 |
| Facade | 複雑なロード手順を `load(model_id)` 一行に | DX 向上 |

#### Layer 4: Block Container Engine（設計の核）
| パターン | 適用部位 | 効果 |
|---|---|---|
| **Composite** | BlockContainer ⊃ sub-block、nested_container 再帰 | FR-02 + TRIZ #7 入れ子 |
| **Strategy** | sub-block タイプ（attention / FFN / memory_read…）の差替 | FR-03 plugin の基礎 |
| Chain of Responsibility | sub-block 列の順次処理、早期 return 可 | skip / branch / 条件分岐 |
| **Builder** | YAML ContainerSpec → 実行プラン compile | runtime overhead 削減 |
| Interpreter | ContainerSpec DSL の解釈エンジン | AI が生成しやすい宣言形 |
| Specification | schema validation（未知属性 / 順序違反 / 必須欠落） | NFR-04 |
| Visitor | hidden state を sub-block 列で巡回して情報収集 | dead block / route trace |
| Plugin / Registry | `SubBlockRegistry` の動的登録 | EP-01 |
| Abstract Factory | sub-block 型ごとの factory | trainable / config 差異吸収 |

#### Layer 5: Memory Fabric
| パターン | 適用部位 | 効果 |
|---|---|---|
| Repository | 各 memory 型の永続化抽象 | NFR-01 backend 差替 |
| Facade | 4 層を統一 read/write API へ | 上位 simplification |
| **CQRS** | read (retrieval) と write (consolidation) 分離 | TRIZ #19 周期化と整合 |
| **Event Sourcing** | episodic は append-only event stream | provenance / time-travel |
| Aggregate (DDD) | 1 概念 = 複数 memory node の集合 | 整合境界の明示 |
| Observer | write event を consolidation scheduler / observability が購読 | 疎結合 |
| **Proxy** | cross-zone access の access control (FR-17) | TRIZ #39 不活性雰囲気 |
| Specification | write 条件（surprise / novelty / confidence drop）の組合せ判定 | FR-06 |

#### Layer 6: Evolution Manager
| パターン | 適用部位 | 効果 |
|---|---|---|
| **Command** | CandidateDiff = Command (apply / undo / replay) | rollback の自然な実装 |
| **Memento** | promotion 前後のスナップショット | TRIZ #11 緩衝 |
| **State** | candidate lifecycle (draft → proposed → eval → staging → prod / rejected / rolled_back) | 状態管理 |
| **Saga** | 多段昇格を補償付きトランザクションへ | 失敗時の部分巻き戻し |
| Specification | 昇格基準（quality ∧ no_forgetting ∧ no_pollution ∧ human_ok） | FR-07 補強 |
| Template Method | 評価パイプラインの骨格、メトリクスは hook | benchmark 拡張 |
| Strategy | mutation policy（template / LLM / population-based） | EP-04 |
| Prototype | 既存 candidate の clone から mutation 生成 | 探索効率化 |

#### Layer 7: Observability & Benchmark
| パターン | 適用部位 | 効果 |
|---|---|---|
| Decorator | 実行 / メモリ / router をラップしてログ採取 | コア侵襲ゼロ |
| Observer / Pub-Sub | OpenTelemetry 互換イベントバス | NFR-03 |
| Chain of Responsibility | ログ enrichment（trace_id → span_id → run_id → candidate_id） | トレーサビリティ |

#### Layer 8: llove HITL（新規）
| パターン | 適用部位 | 効果 |
|---|---|---|
| MVVM | TUI review pane の状態管理 | テスト容易、Textual と相性 |
| Command | HITL 承認 / 却下を Command として記録 | 監査可能性 |
| Observer | candidate state 変化を TUI が購読 | reactive UI |

#### llmesh I/O Bus（新規、層を跨ぐ横断）
| パターン | 適用部位 | 効果 |
|---|---|---|
| Adapter | MQTT / OPC-UA → memory event 形式へ変換 | FR-19 の基礎 |
| Bridge | transport（MQTT/OPC-UA/AMQP）と domain（memory event）の分離 | 通信層変更の影響を遮断 |
| Pub/Sub | sensor stream → memory write event | P-03 EDA との整合 |

### 拡張点とパターン互換性

新規拡張時の遵守事項:

- 新 **sub-block** 追加: Strategy + Plugin + Specification を守る
- 新 **memory backend** 追加: Repository + Adapter で接続
- 新 **mutation policy** 追加: Strategy として登録、Command との互換性確保
- 新 **modal encoder** 追加: Bridge + Adapter で接続
- 新 **transport** 追加 (llmesh 拡張): Bridge + Adapter + Pub/Sub

---

## § 4. 全体アーキテクチャ (8 層構成)

```
┌─────────────────────────────────────────────────────────────┐
│ L8: llove HITL Layer  (TUI review, memory viz, arena)       │ ← MVVM + Command + Observer
├─────────────────────────────────────────────────────────────┤
│ L7: Observability & Benchmark                               │ ← Decorator + Observer + CoR
├─────────────────────────────────────────────────────────────┤
│ L6: Evolution Manager  (proposal / mutation / promote / RB) │ ← Command + Saga + State + Memento
├─────────────────────────────────────────────────────────────┤
│ L5: Memory Fabric                                           │ ← Facade + CQRS + Repository + ES
│   ├─ semantic  ├─ episodic  ├─ structural  ├─ parameter     │
├─────────────────────────────────────────────────────────────┤
│ L4: Block Container Engine                                  │ ← Composite + Strategy + Builder
├─────────────────────────────────────────────────────────────┤
│ L3: Core Model Adapter  (HF / vLLM / TGI)                   │ ← Adapter + Proxy
├─────────────────────────────────────────────────────────────┤
│ L2: Orchestration  (pipeline + router + scheduler)          │ ← Pipes&Filters + Mediator
├─────────────────────────────────────────────────────────────┤
│ L1: Interface  (CLI / MCP / REST / Batch)                   │ ← Facade + Command
└─────────────────────────────────────────────────────────────┘
         ↕
   llmesh I/O Bus  (MQTT / OPC-UA)  ← Adapter + Bridge + Pub/Sub
```

---

## § 5. 既存類似研究との差別化軸

| 既存系 | 重なる範囲 | llive の差別化点 |
|---|---|---|
| MemGPT | 階層メモリ | 4 層分離 + 生物学的 phase transition + 署名 zone |
| LongMem | retrieval augmented memory | structural memory graph + provenance + **llmesh 分散ホスト** |
| AutoML-Zero, NAS for LLMs | 構造探索 | **形式検証 gate** + multi-precision shadow + 失敗データ化 |
| Self-Refine, Reflexion | 自己批評 | online / offline 分離 + **llove TUI による HITL staging** |
| MERA, ModularLLM | モジュラー化 | 可変長 BlockContainer YAML + sub-block plugin registry |
| AutoGPT, AgentBench | エージェント | **llmesh 産業 IoT 直結** + llove TUI HITL |

差別化の総合命題:

> **"生物学的記憶モデル × 形式検証 × 産業 IoT メッシュ × TUI HITL"** の 4 軸交差点に座る LLM 自己進化基盤。
> どれか 1〜2 軸の研究は多数存在するが、4 軸を一体化した実装は類例ほぼ無し。

---

## § 6. llmesh / llove 統合シナリオ

### llmesh 統合
- **memory backend** として MQTT / OPC-UA を採用 (FR-19)
- **MTEngine / XbarRChart / CUSUMChart** で memory access latency / write rate / pollution の SPC モニタ
- **フェアネス機構** で複数 candidate 間の memory 公平アクセス保証
- **signed adapter P2P 配布** (FR-18) を llmesh ノード間で実施

### llove 統合
- **F16 マルチゲームアリーナ抽象**を candidate vs candidate 継続学習対局へ転用 (FR-20)
- **F15 (Markdown / SVG / Mermaid / 折り畳み)** で memory link graph と route trace を可視化
- **F11 HITL レビュー画面**を candidate 昇格 staging で利用
- **F23 PowerShell 互換シェル / F24 Claude Code 統合**で開発者体験統合

### 統合運用フロー
1. 産業 IoT センサ → llmesh → llive episodic memory（自動 write）
2. surprise score 高い event を semantic memory へ phase transition
3. consolidation サイクルで parameter memory（adapter）を更新候補生成
4. Static Verifier で structural 反例検出 → 早期 reject
5. Multi-precision shadow eval で計算劣線形化
6. 上位候補を llove HITL でレビュー
7. 署名付き adapter として llmesh P2P 配布
8. Reverse-Evolution Monitor で forgetting 監視、悪化なら自動 rollback

---

## § 7. 推奨実装順序（更新版）

v0.1 のフェーズ分けを維持しつつ、各 Phase に拡張要件を割当：

### Phase 1: Minimal Viable Research Platform
v0.1 範囲 + 以下を含める
- **FR-13 Static Verifier (簡易版)**: ContainerSpec の YAML schema validation のみ
- **P-01 Hexagonal** ディレクトリ構造の確立

### Phase 2: Adaptive Modular System
v0.1 範囲 + 以下
- **FR-12 Hippocampal Consolidation Scheduler**
- **FR-16 Memory Phase Manager**
- **FR-21 Surprise-Bayesian Write Gate**
- **FR-20 llove HITL の最小可視化**（route trace のみ）

### Phase 3: Controlled Self-Evolution
v0.1 範囲 + 以下
- **FR-14 Multi-precision Shadow Evaluation**
- **FR-15 Failed-Candidate Reservoir**
- **FR-22 Reverse-Evolution Monitor**
- **FR-13 Static Verifier (Lean/Z3 連携版)**

### Phase 4: Multimodal / Production
v0.1 範囲 + 以下
- **FR-17 Quarantined Memory Zone**
- **FR-18 Signed Adapter Marketplace**
- **FR-19 llmesh Sensor Bridge**
- **FR-20 llove HITL の本格実装**（Candidate Arena 含む）

---

## § 8. 用語追加

| 用語 | 定義 |
|---|---|
| Hippocampal Consolidation | episodic memory を semantic / structural / parameter memory へ replay-based 凝集する周期処理 (FR-12) |
| Static Verifier | candidate spec の構造的不変量を Lean / Z3 / TLA+ で機械検証する pre-LLM ゲート (FR-13) |
| Multi-precision Shadow Eval | INT8 / 4bit 並列評価で zero-cost proxy を補強する評価帯 (FR-14) |
| Failed-Candidate Reservoir | rejected candidate の特徴を保持する専用記憶層 (FR-15) |
| Memory Phase Transition | episodic → semantic → archive → erase の段階遷移 (FR-16) |
| Quarantined Memory Zone | untrusted source 隔離 zone、cross-zone read に署名検証必須 (FR-17) |
| Signed Adapter | Ed25519 署名 + SBOM manifest 付きの差分重み (FR-18) |
| llmesh Sensor Bridge | llmesh sensor stream → episodic memory 直接書込口 (FR-19) |
| Candidate Arena | llove F16 抽象を流用した candidate 対局評価環境 (FR-20) |
| Reverse-Evolution Monitor | forgetting 悪化方向の変更を自動 rollback する監視機構 (FR-22) |
