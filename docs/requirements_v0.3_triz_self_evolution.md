# llive 要件定義書 v0.3 追補章 — TRIZ 内蔵による自己進化

> v0.2 addendum に対する第 2 拡張。llive が **自分自身に TRIZ を適用してアイデア出しできる** ことを第一級要件として組み込む。

## 概要

v0.2 で「審査付き自己進化」の骨格は揃ったが、**mutation の発想元**は外部 LLM 任せだった。v0.3 では TRIZ 思考そのものをフレームワークに内蔵し、矛盾検出 → 40 原理引き → RAD 裏付け → CandidateDiff 生成までを自動化する。これにより llive は「自分の弱点を自分で見つけて改善案を出す」メタ機構を持つ。

## § 1. 動機

- 既存の `LLM-generated mutation` は無方向 / 確率的探索になりがち、計算コスト高い
- TRIZ の 40 原理 × 39×39 マトリクスは **既知発明パターンの圧縮表現**、発想空間を効率良くカバー
- llive 内のメトリクス (forgetting vs adaptability 等) から矛盾を **自動検出**でき、人手なしで TRIZ サイクルを回せる
- RAD コーパス (~6.5 万 docs, 30+ 分野) と組合せれば、各原理の **既存実装裏付け**を即時得られる

## § 2. 拡張要件 (FR-23 〜 FR-27)

### FR-23 Contradiction Detector

**目的**: llive 内のメトリクス時系列 / 現在の ContainerSpec / 過去 candidate の score_bundle から **矛盾 (improvement vs degradation のペア)** を自動抽出。

**入力**:
- `Metric stream` (Observability から)
- `Candidate score history` (Memory.parameter から)
- 手動指定 (`llive triz suggest --improve A --degrade B`)

**出力**:
```yaml
- contradiction_id: contra_20260513_001
  improve_attribute:
    name: speed
    triz_feature_id: 9                 # 39 工学特性 ID
    metric_ref: llive.pipeline.latency_ms.p50
    direction: down                    # latency 下げる = speed 上げる
  degrade_attribute:
    name: stability_of_composition
    triz_feature_id: 13
    metric_ref: llive.evolution.forgetting
    direction: up                      # forgetting 増 = 安定性低下
  severity: 0.8                        # 0.0-1.0 (矛盾の強さ)
  evidence:
    - run_id: run_20260513_042
      delta_improve: -15.2             # latency_ms 下がった
      delta_degrade: -3.4              # BWT 悪化 (-3.4%)
```

**検出ロジック**:
- 候補 A → B の variation で **片方の指標改善 + 他方の指標悪化** が同時発生したら矛盾候補
- Pareto frontier 上の隣接点間で勾配が反対符号な指標ペアを列挙
- 統計的有意性検定 (Mann-Whitney U 等) で false positive 抑制

### FR-24 TRIZ Principle Mapper

**目的**: 矛盾ペア → 40 原理から推奨候補を引く。

**内蔵リソース**:
- `specs/resources/triz_principles.yaml` (40 原理定義)
- `specs/resources/triz_matrix.yaml` (39×39 矛盾マトリクス)
- `specs/resources/triz_features.yaml` (39 工学特性 + llive 固有特性のマッピング)

**llive 固有特性マッピング**:

| TRIZ 標準特性 | llive metric | 補足 |
|---|---|---|
| 9. 速度 | `pipeline.latency_ms` | down direction |
| 13. 安定性 | `evolution.forgetting`, `router.entropy` | 維持方向 |
| 25. 時間損失 | `evolution.eval.duration_s` | down |
| 26. 物質の量 | `memory.nodes.count` | up |
| 27. 信頼性 | `candidate.rollback_rate` | down |
| 31. 有害な副作用 | `memory.pollution_ratio`, `security.zone_violations` | down |
| 35. 適応性 | `candidate.acceptance_rate`, `forward_transfer` | up |
| 36. 装置複雑さ | `container.subblock.count`, `nested_depth` | balanced |
| 37. 制御困難さ | `router.entropy` 上限超 | down |
| 38. 自動化レベル | `evolution.human_review_ratio` | up but capped |
| 39. 生産性 | `pipeline.throughput` | up |

**出力**:
```yaml
contradiction_id: contra_20260513_001
recommended_principles:
  - id: 19
    name: Periodic Action
    score: 0.92                        # 推奨度 (マトリクス + RAD 裏付け)
    rationale: "online/offline 分離は周期化の応用 → FR-12 と整合"
  - id: 13
    name: The Other Way Around
    score: 0.85
  - id: 7
    name: Nested Doll
    score: 0.78
```

### FR-25 RAD-Backed Idea Generator

**目的**: 推奨 TRIZ 原理 × RAD コーパスで具体アイデアを生成、CandidateDiff として出力。

**パイプライン**:
1. `(contradiction, recommended_principle)` を入力
2. 原理に紐づく RAD 分野リスト (`triz_principles.yaml` の `rad_domains` フィールド) を引く
3. 関連分野コーパスから semantic search で類似研究を抽出
4. LLM (claude-haiku) で `「現在の ContainerSpec を、原理 X を使って、RAD で見つかった手法 Y のように改変する CandidateDiff」` を生成
5. 自動的に `mutation_metadata.policy = triz_inspired` を付与

**RAD コーパス連携**:
- raptor の `.claude/skills/corpus/` をマウント (RAPTOR_CORPUS_DIR 環境変数)
- 各分野の INDEX.md と cluster summaries を検索
- 引用元 (source_id + cluster_id) を `provenance.derived_from` に記録

**出力例**:
```yaml
candidate_id: cand_20260513_t01_001
mutation_metadata:
  policy: triz_inspired
  contradiction_id: contra_20260513_001
  applied_principle:
    id: 19
    name: Periodic Action
  rad_evidence:
    - corpus: neural_signal_corpus_v2
      cluster: cluster_03_consolidation_replay
      doc_id: 2024.05.123
      relevance: 0.88
rationale:
  - "矛盾 (speed↑, stability↓) を周期化原理で解消"
  - "neural_signal RAD の海馬-皮質サイクル研究を sub-block 配置に転用"
changes:
  - action: insert_subblock
    target_container: adaptive_reasoning_v1
    after: memory_read
    spec:
      type: memory_write
      config:
        policy: surprise_gated
        schedule: { mode: periodic, every_n_steps: 1000 }   # 周期化
```

### FR-26 9-Window System Operator

**目的**: TRIZ の 9 画法（過去/現在/未来 × 上位系/対象系/下位系）で多時間軸・多階層の発想拡張。

**llive での 9 窓**:

|         | 過去 (history) | 現在 (state) | 未来 (projection) |
|---|---|---|---|
| **上位系** (host: research OS / multi-agent) | 過去の上位 system の限界 | 現在の上位需要 | 上位系の将来要件 |
| **対象系** (llive) | 過去の candidate 変遷 | 現在の container / metrics | 未来の性能予測 |
| **下位系** (sub-block / memory node) | 退役 sub-block の記録 | 現在の sub-block 構成 | sub-block 追加候補 |

**実装**:
- `WindowExtractor` が 9 セルそれぞれに対する snapshot を生成
- 矛盾ペアごとに **9 セルから 1 つ選んで mutation の素材**にする
- 例: "未来 × 下位系" を選ぶと「将来必要になりそうな sub-block を先取り追加」

### FR-27 ARIZ Pipeline

**目的**: TRIZ ARIZ 9 ステップを mutation 自動化フローへ機械的にマッピング。

| ARIZ ステップ | llive 内マッピング |
|---|---|
| 1. 問題分析 | Metric stream parsing |
| 2. 問題モデル化 | Contradiction Detector 出力 |
| 3. IFR 定義 | 目標メトリクス値 (config 由来) |
| 4. 物理矛盾特定 | 時間/空間/条件 分離可能性チェック |
| 5. 資源洗い出し | 現在の sub-block / memory / adapter 一覧 |
| 6. 発明標準解 | 40 原理 + RAD 既存実装 |
| 7. 物理効果 | sub-block 効果カタログ |
| 8. 解の評価 | Static Verifier + Shadow Eval |
| 9. 解の発展 | HITL + Reverse-Evolution Monitor |

これらを `EvolutionManager.run_ariz_cycle()` 一発で回せる。

## § 3. Mutation Policy としての登録

EP-04 (新 Evolution Policy) に `triz_inspired_mutation` を追加:

```yaml
mutation_policies:
  - id: template
    description: 事前定義テンプレートから
  - id: llm_generated
    description: 直接 LLM に diff 生成依頼
  - id: population_based
    description: 既存集団から evolutionary search
  - id: triz_inspired             # 新規
    description: 矛盾検出 + 40 原理 + RAD で発想
    config:
      contradiction_window_runs: 100     # 直近 N runs から矛盾検出
      max_principles_per_contradiction: 3
      use_9window: true
      use_ariz: true
      rad_corpus_dir: ${RAPTOR_CORPUS_DIR:-/c/Users/puruy/raptor/.claude/skills/corpus}
```

mutation policy 切替は Strategy パターン (P-04 設計原則)、他 policy と並列でも単独でも動作可能。

## § 4. Self-Reflection モード

llive が **自分自身に定期的に TRIZ を適用** するモード。

**起動条件 (いずれか)**:
- 定期 cron (例: 毎週日曜 03:00)
- メトリクス閾値超過 (例: forgetting > 5%)
- `llive triz brainstorm` 手動実行
- HITL から `request_triz_review` コマンド

**フロー**:
1. Contradiction Detector が直近 100 runs から矛盾を列挙
2. 上位 K 個を TRIZ Principle Mapper にかけて原理推奨
3. 各 (contradiction, principle) で RAD-Backed Idea Generator が CandidateDiff を生成
4. Static Verifier + Shadow Eval で足切り
5. 残った候補を llove HITL pane で表示
6. 人間が承認したものだけ promote へ

これにより llive は **自律的に発想 + 提案する** が、最終昇格は人間が握る (安全と創造性の両立)。

## § 5. CLI / Skill コマンド

```bash
# 矛盾検出 + アイデア生成 (Self-Reflection 1 サイクル)
llive triz brainstorm --window 100 --top-k 5

# 矛盾マトリクス / 原理一覧表示
llive triz inspect --principles 1,15,19,40
llive triz inspect --matrix improve=9 degrade=13

# マニュアル指定
llive triz suggest --improve speed --degrade stability_of_composition

# RAD コーパス連携の状態確認
llive triz rad-status

# ARIZ 完全実行
llive triz ariz --contradiction contra_20260513_001
```

将来 Claude Code から呼べる Skill も提供 (`/llive-triz`)。

## § 6. データモデル拡張

### Contradiction エンティティ

`data_model.md` に追加:

```yaml
type: Contradiction
id: string
improve_attribute:
  name: string
  triz_feature_id: integer
  metric_ref: string
  direction: enum [up, down]
degrade_attribute:
  name: string
  triz_feature_id: integer
  metric_ref: string
  direction: enum [up, down]
severity: float
detected_at: datetime
evidence: [object]
resolved_by_candidate: string | null   # promote 後に紐付け
```

### CandidateSpec 拡張

```yaml
mutation_metadata:
  policy: enum [llm_generated, template, population, neuroevolution, triz_inspired]
  # triz_inspired 時の追加フィールド
  contradiction_id: string | null
  applied_principle: { id: integer, name: string } | null
  rad_evidence: [RadEvidenceRef] | null
```

## § 7. Observability 追加

新メトリクス:

- `llive.triz.contradictions.detected.total` (Counter, labels: severity_bucket)
- `llive.triz.principles.applied.total` (Counter, labels: principle_id)
- `llive.triz.rad_evidence.hits.total` (Counter, labels: corpus)
- `llive.triz.brainstorm.duration_s` (Histogram)
- `llive.triz.candidates.acceptance_rate` (Gauge)

新 Event:
- `llive.triz.contradiction_detected`
- `llive.triz.brainstorm_session_started`
- `llive.triz.brainstorm_session_finished`

## § 8. 既存類似研究との位置づけ

| 類似系 | 範囲 | llive TRIZ の差別化 |
|---|---|---|
| AutoML-Zero (Google) | 機械学習構造の進化 | TRIZ 体系 + 矛盾マトリクスを **明示的に** 内蔵、発想に方向性 |
| LLMatic / LLM-as-NAS | LLM でアーキ探索 | RAD 裏付け + 形式検証 + 矛盾検出ループ |
| MetaPrompt 系 | LLM 自己改善 | フレームワーク全体に拡張、メトリクスベースの矛盾自動検出 |
| TRIZ × AI 学術論文 | 概念提案レベル | **動作する実装 + 産業 IoT 連携** が新規 |

「TRIZ + LLM 自己進化 + 産業 IoT 直結」の 3 軸交差点に **動作する実装**を出すのは、現時点で先行例がほぼ無い（要 prior art 調査）。

## § 9. Phase 統合

| Phase | TRIZ 関連 milestone |
|---|---|
| Phase 1 | `triz_principles.yaml` + `triz_matrix.yaml` リソース整備、CLI スケルトン |
| Phase 2 | FR-23 Contradiction Detector + FR-24 Principle Mapper |
| Phase 3 | FR-25 RAD-Backed Idea Generator + FR-26 9-Window + FR-27 ARIZ Pipeline |
| Phase 4 | Self-Reflection mode 自動運転 + llove TUI 統合 |

## § 10. リスクと対策

| リスク | 対策 |
|---|---|
| 矛盾検出が false positive 多発 | 統計的有意性検定 + 最小 evidence 件数 5 以上 |
| TRIZ 原理が抽象的すぎて diff 生成失敗 | 原理ごとに **llive 文脈での具体例 3 つ以上** を `triz_principles.yaml` に記載 |
| RAD コーパス検索ノイズ | 関連度スコア 0.7 以上のみ採用、複数 corpus 横断時は重み付け |
| Self-Reflection 暴走 | cron 頻度上限 + 1 サイクルあたり生成 candidate 数上限 + HITL ゲート必須 |
| LLM hallucination | Static Verifier (FR-13) で構造的整合性チェック先行 |
