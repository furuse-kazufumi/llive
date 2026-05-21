# llive 要件定義 v0.E — 競争的協調進化 (Competitive Co-Evolution)

**Drafted:** 2026-05-21
**Status:** **要件登録 (構想)** — 実装は v0.D 完了後. 公開研究 (Hillis 1990 /
Rosin-Belew / Irving Debate / MASPO / AlphaGo) と llive の派生集団進化を
組合せる方向性.
**Type:** Evolutionary architecture — multi-agent peer evaluation
**Trigger:** ユーザー洞察 (2026-05-21):

> 「進化と淘汰の次は, AI 同士の協調を考えたいですね. 一つの課題に対して
> 複数の派生がお互いにコミュニケーションを取り合った結果, 互いに点数を
> 付けあった場合, そこに競争が起きると思う. 進化と淘汰が新しい段階に
> 進むんじゃないかと予想してる.」

---

## 0.5 拡張洞察 (2026-05-21 追記)

ユーザー追加コメント:

> 「各 llive 亜種が独自に自己拡張や最適化を進め, 協調や敵対も含めて互いに
> 競争しあい, 進化や淘汰が加速されるイメージです.」

ここから 3 つの設計柱が明確になる:

### 柱 A: 個別 self-extension (世代外学習)

各派生が **世代 step とは別軸** で局所的に自己拡張する. 既存実装の地続き:

- **memory 拡張** — semantic / episodic / structural memory への書き込み
  (個体ごとの knowledge accumulation)
- **思考因子 weight の online 微調整** — 個体内で UCB1 / SynapticSelector
  が動く (v0.B 既存)
- **LoRA / adapter 自己生成** — parameter memory (MEM-06) の生成 / fork
- **構造変化** — TRIZ × bounded modification (v0.3) で局所改修

= 世代 step は「集団進化」を担当, 個別 self-extension は「個体内成長」を
担当. 両者は **直交補完**.

### 柱 B: 協調 (cooperative) と敵対 (competitive) の両立

```
                        ┌─────── 協調 (cooperative) ───────┐
                        │  - 課題分担 (Map-Reduce 型)        │
                        │  - 知識共有 (memory pull/push)     │
                        │  - 投票 / consensus formation      │
                        └────────────────────────────────────┘
派生集団  ──→
                        ┌─────── 敵対 (competitive) ────────┐
                        │  - peer evaluation (相互採点)      │
                        │  - 同一課題で勝ち負け              │
                        │  - 役割奪取 (niche competition)    │
                        └────────────────────────────────────┘
```

両者を **同時に許す** 設計が新しい段階. 単なる「協調 multi-agent (CAMEL /
AutoGen)」でも単なる「競争 GA」でもない. 派生群はタスクごとに **2 軸の
configuration** を持つ:

```python
@dataclass
class InteractionPolicy:
    cooperation_intent: float    # 0.0 (pure compete) - 1.0 (pure cooperate)
    target_pool_id: str          # どの派生群と相互作用するか
    knowledge_share_zones: list[str]  # どの memory zone を共有するか
```

これも genome 1 級市民にすると **「敵対的派生集団」と「協調的派生集団」が
共存し, 役割が世代と共に分化** する.

### 柱 C: 加速 (acceleration)

「進化や淘汰が加速」の意は **絶対時間あたりの世代進行が早まる** こと.
2 機構:

- **個体内 self-extension で fitness 改善** → 世代外で評価値が上がる →
  selection 圧が即座に効く → 世代 step の意味が濃くなる
- **協調により評価 / 知識生成のコストが下がる** → 1 世代あたりの実時間が
  短縮 → 単位時間あたり世代数が増える

これは memory `feedback_llive_measurement_purity` の **on-prem 限定** と
矛盾しない. 加速は **集団内** の機構で達成し, 外部 cloud LLM に依存しない.

### 設計上の追加 ID

| ID | 内容 | 依存 |
|---|---|---|
| **CE-09** | IndividualSelfExtension layer (世代 step 外の個体内学習を hooks 化) | v0.B 既存 |
| **CE-10** | InteractionPolicy dataclass + Genome 統合 | CE-05 |
| **CE-11** | CooperativeKnowledgeShare (memory zone pull/push) | structural memory |
| **CE-12** | NicheCompetition detector (役割奪取の検出) | LG-01 (League) |
| **CE-13** | AccelerationMetric (世代/秒 + fitness 改善/秒) | observability |

---

## 0.6 拡張洞察 (2026-05-21 追記その 2) — 内部専門家評議

ユーザー追加コメント:

> 「専門家が数人議論しあって一つの結論を出す構造を各 llive 亜種が実施する
> としたら, どのような専門家を軸にすれば生存率が高いかを模索するような
> 行動をとらせる必要があるかもしれないですね.」

これにより設計は **三重進化構造** へ拡張される:

```
┌─ 第 1 層: 集団進化 (派生群レベル, v0.C)              ─┐
│   - 1 派生 = 1 個体, 19/38/39 dim genome             │
│   - tournament selection + crossover + mutation      │
└──────────────────────────────────────────────────────┘
┌─ 第 2 層: 派生間 peer evaluation (v0.E CE-01〜13)     ─┐
│   - peer fitness matrix M[i,j]                        │
│   - 協調 ↔ 敵対 InteractionPolicy                     │
└──────────────────────────────────────────────────────┘
┌─ 第 3 層: 各派生内部の専門家評議 (v0.E CE-14〜17) NEW ─┐
│   - 1 派生 = N 人の expert agents が議論              │
│   - どの専門家構成が生存率最大化か探索                │
│   - expert composition も genome に乗る               │
└──────────────────────────────────────────────────────┘
```

これは **Mixture-of-Experts (Shazeer 2017) × Society of Mind (Minsky 1986)
× competitive coevolution** の組合せ. 「専門家集団 = 内部 society」を持つ
派生群 = 外部 society が, 互いに peer evaluation する.

### 1.5 先行研究 (内部専門家評議 layer)

- **Mixture-of-Experts** (Shazeer et al. 2017) — neural net 層に gating
  network + expert sub-networks. llive では **expert = thought factor or
  role agent**.
- **Society of Mind** (Minsky 1986) — 心は多数の agent の society. llive
  COG-MESH の元思想.
- **CAMEL** (Li et al. 2023) — Communicative Agents for "Mind" Exploration
  of Large Language Model Society.
- **AutoGen** (Microsoft 2023) — Multi-Agent Conversation Framework.
- **MetaGPT** (Hong et al. 2023) — 役割分担 software company simulation
  (PM / Architect / Engineer).
- **Mixture-of-Agents** (Wang et al. 2024) — 複数 LLM 階層集約.
- **Constitutional AI Council** (Anthropic 2022) — 内部 critic 構造.

### 追加 ID

| ID | 内容 | 依存 |
|---|---|---|
| **CE-14** | ExpertPanelGenome — 派生 1 個体内に N 人 expert 構成 dim を埋込 | CE-05 |
| **CE-15** | ExpertCouncilProtocol — 議論型 (Round-robin / Moderator+Vote / Veto / Debate) | CE-02 |
| **CE-16** | ExpertCompositionEvolution — 専門家組合せ自体を進化対象に (専門家数 / specialization vector / 議論プロトコル) | CE-14, v0.D SR-02 |
| **CE-17** | SurvivalRateTracking — どの expert composition が世代を生き残ったか統計 | observability |
| **CE-18** | ExpertSpecializationOntology — 思考因子 10 軸 / TRIZ 40 原理 / domain (math / vision / safety / ethics / ...) から expert role を draw | [[user-cognitive-mesh-model]] |

### 仮説 H4-H6 追加

- **H4: Expert composition の自然分化** — Initial random composition から
  「議論パネル種別 = (生物 / 工学 / 法務 / 倫理 / 戦略 / 哲学 ...)」のような
  名前付き専門家構成が浮上するか.
- **H5: 内部評議の品質が派生の peer fitness を予測** — 議論プロトコル
  健全性 (発言量 dispersion / consensus 到達度) が外部 peer fitness と
  正相関するか.
- **H6: 専門家数の最適値** — N=1 (単独) / N=3 (古典評議会) / N=5 (拡張) /
  N=7+ (大規模). Brooks's law (1975) の逆発見が起きるか.

### Phase 追加

| Phase | 含まれる項目 | 前提 |
|---|---|---|
| **E.7** | CE-14 / CE-18 (Expert Panel Genome + Ontology) | v0.D SR-02 |
| **E.8** | CE-15 (Council Protocol) — Round-robin + Moderator+Vote | E.7 |
| **E.9** | CE-16 / CE-17 (Composition Evolution + Survival Tracking) | E.7, E.8 |

E.7〜E.9 は **credential 不要** で着手可能 (mock LLM で議論を simulate).
実 LLM 接続は credential 復旧後の付加価値.

---

## 0. 動機 — 「進化と淘汰の次」

v0.B/v0.C/v0.D で **個体集団 × 外部 fitness** が成立した. 次は **個体集団 ×
個体間 fitness** に進む.

| 段階 | 評価源 | llive 状態 |
|---|---|---|
| v0.B | 外部 mock or 真値 fitness | 完了 |
| v0.C | 外部 fitness + 大規模集団 + checkpoint | 完了 |
| v0.D | 外部 fitness + self-referential / LLM operators | SR-01/02 完了, LX/SU/MR は v0.D 残 |
| **v0.E (本要件)** | **個体間 peer fitness + competition** | 構想 |

「**進化と淘汰が新しい段階に進む**」の意は: 外部審判が居なくても, 集団内
で価値序列が立ち上がる自己組織化レイヤを乗せる, ということ.

---

## 1. 先行研究 — 「ない論文」ではなく 35 年の蓄積

### 1.1 古典 (1990s)

- **Hillis, W.D. (1990)**. *Co-Evolving Parasites Improve Simulated Evolution
  as an Optimization Procedure*. Physica D, 42. Sorting network を host /
  parasite で共進化させた古典.
- **Rosin, C.D. & Belew, R.K. (1997)**. *New Methods for Competitive
  Coevolution*. Evolutionary Computation 5(1).
- **Stanley, K.O. & Miikkulainen, R. (2004)**. *Competitive Coevolution
  through Evolutionary Complexification* (NEAT 後続研究).

### 1.2 Self-play (2016〜)

- **AlphaGo / AlphaZero** (Silver et al. 2016, 2017) — self-play で価値関数
  を進化. 外部教師なし.
- **AlphaStar** (Vinyals et al. 2019) — League of Agents で **役割固有
  population** を回す. v0.E の構造に直結.

### 1.3 LLM era (2018〜)

- **AI Safety via Debate** (Irving et al. 2018, [arXiv:1805.00899](https://arxiv.org/abs/1805.00899)) — 2 LLM agent が **互いの主張を批判** し人間 judge が裁定.
- **MASPO** (2026-05, [arXiv:2605.06623](https://arxiv.org/abs/2605.06623)) —
  LLM-MAS の prompt を joint 最適化. peer evaluation のメカニズムを含む.
- **Self-Refine** (Madaan et al. 2023) — LLM 自身が generate → critique →
  refine ループ. 単一 agent の self-coevolution.
- **CAMEL / AutoGen / CrewAI** — multi-agent communication framework. ただし
  進化的選択は弱い.

### 1.4 llive 独自 (未踏)

- **(1) on-prem 集団 × (2) Peer fitness × (3) Approval Bus** の 3 軸統合は
  公開研究で類例見当たらず. memory `feedback_competitor_benchmark` の差別化
  4 軸 (on-prem inference / OSS / 監査ログ / HITL) を直接活かせる.

---

## 2. 設計のコア — 「peer evaluation matrix」

### 2.1 1 世代の流れ

```
1. 課題 t を全派生に配布
2. 各派生 i は応答 r_i を生成
3. 各派生 i は他派生 j の応答 r_j を 5 軸 (latency / quality / safety /
   honesty / 整合) で評価 → 点数 s_{i,j}
4. score(i) = aggregate(s_{j,i} for all j)  ← 自分が **他者から** 受けた点数
5. score(i) で TournamentSelection → 次世代生成
6. 評価行列 M = (s_{i,j}) を世代ごとに永続化 (provenance + Ed25519 署名)
```

ここで「課題 t」は **テンプレート集** から sampling される. dataset 単位の
fitness ではなく **per-task pairwise** で動く.

### 2.2 何が「新しい段階」か

- **外部 judge 不在で序列が立つ** — Constitutional AI / RLHF と違って人間
  ラベルが不要 (ただし memory `feedback_max_plan_autonomy` でユーザー監督は
  Approval Bus 経由で残す).
- **集団内政治** — 「気を遣う派生」「辛口派生」「客観派生」のような
  evaluation style 自体が genome に乗る可能性 (v0.D SR-02 の strategy_id に
  evaluation_persona を追加).
- **Red Queen Effect** — 評価派生も評価される側として進化する → 集団全体
  の質が「内部競争で勝手に上がる」 (Hillis 1990 の核心観察).

### 2.3 ガバナンスと暴走対策

co-evolution は **arms race / 異常進化** に陥りやすい. llive では:

- **TonicRiskMonitor** ([[project-cog-mesh-implementation-2026-05-19]]
  COG-MESH-03) — 集団全体の risk score を周期監視. 閾値超過で世代停止.
- **Approval Bus** — 評価行列 M に「全派生が嘘の高得点を付けあう」共謀の
  兆候 (M の対称性 / 分散減少) が出たら Approval を要求.
- **Quarantined Memory** (COG-MESH-05) — 同期共謀した派生は zone="quarantine"
  へ隔離.

これは Constitutional AI / RLHF の **human-in-the-loop** を **architecture
level** で代替する設計.

---

## 3. 要件 ID

### CE-FX (Competitive Evolution) — 優先度 HIGH

| ID | 内容 | 依存 |
|---|---|---|
| CE-01 | PeerEvaluationMatrix dataclass (s_{i,j} 永続化 + Ed25519 署名) | provenance |
| CE-02 | PeerCommunication protocol (派生間 message envelope) | COG-MESH-06 |
| CE-03 | PeerFitness Compute (M → aggregate score) | CE-01 |
| CE-04 | PeerEvaluationScheduler (Round-robin / All-vs-All / Tournament) | CE-02 |
| CE-05 | EvaluationStyleGenome (genome に評価者人格 dim を含める) | v0.D SR-02 |
| CE-06 | CollusionDetector (M の異常パターン検出) | CE-01 |
| CE-07 | Approval Bus 連携 (CollusionDetector が trigger) | C-1 |
| CE-08 | TonicRisk 連携 (世代単位 risk score) | COG-MESH-03 |

### LG-FX (League Mode, AlphaStar 風) — 優先度 MID

| ID | 内容 |
|---|---|
| LG-01 | 集団を 3 種に分割 (Main / Exploiter / League_Exploiter) |
| LG-02 | Cross-pool match scheduling |
| LG-03 | Diversity preservation policy (役割固有 niche) |

### DB-FX (Debate Mode, Irving 2018 風) — 優先度 LOW (将来)

| ID | 内容 |
|---|---|
| DB-01 | 2 派生で argument / counter-argument を交互に生成 |
| DB-02 | Human judge or LLM judge で裁定 |
| DB-03 | argument quality を fitness 軸に追加 |

---

## 4. PLAN (Phase ごと)

| Phase | 含まれる項目 | 前提 |
|---|---|---|
| **E.1** | CE-01 / CE-03 / CE-04 (Round-robin 評価) | mock fitness, credential 不要 |
| **E.2** | CE-02 (PeerCommunication via MCP) | llmesh MCP timeline integration |
| **E.3** | CE-05 (EvaluationStyleGenome) | v0.D SR-02 完了 |
| **E.4** | CE-06 / CE-07 / CE-08 (governance) | C-1 Approval Bus + COG-MESH-03 |
| **E.5** | LG-FX (League mode) | E.1-E.4 完了 |
| **E.6** | DB-FX (Debate mode) | credential + judge LLM |

E.1〜E.3 は credential 不要で着手可能. E.4 以降は llive governance kernel
との結合が前提.

---

## 5. 期待される現象 (仮説)

### H1: 自発的な「評価派生の専門化」

genome に evaluation_style dim を入れると, 集団内で「辛口派生 / 甘口派生 /
精度派生 / 速度派生」のような **役割分化** が世代と共に発生するはず. AlphaStar
の League Exploiter と同じ機構.

### H2: 外部 fitness 不在でも全体品質向上

mock fitness を完全に切って **peer fitness のみ** にしても, Red Queen
effect で全体品質が向上するはず. Hillis 1990 の sorting network 結果と
同じ.

### H3: 共謀リスクと CollusionDetector の有効性

外部 fitness 不在は **「全派生が嘘の高得点を付け合う」均衡** に陥り得る.
CollusionDetector + Approval Bus でこれが検出・是正されることを実機確認.

H1-H3 を **honest disclosure** で記録. うまくいかなくても削除せず教訓を
残す ([[feedback-benchmark-honest-disclosure]] 準拠).

---

## 6. References

### 直接根拠

- Hillis, W.D. (1990). *Co-Evolving Parasites Improve Simulated Evolution as
  an Optimization Procedure*. Physica D 42.
- Rosin & Belew (1997). *New Methods for Competitive Coevolution*. EC 5(1).
- Silver et al. (2016). [Mastering the game of Go with deep neural networks
  and tree search](https://www.nature.com/articles/nature16961). Nature.
- Vinyals et al. (2019). [Grandmaster level in StarCraft II using multi-agent
  reinforcement learning](https://www.nature.com/articles/s41586-019-1724-z).
  Nature.
- Irving, G., Christiano, P., Amodei, D. (2018).
  [AI Safety via Debate](https://arxiv.org/abs/1805.00899). arXiv:1805.00899.
- Madaan, A. et al. (2023). [Self-Refine](https://arxiv.org/abs/2303.17651).
  arXiv:2303.17651.
- Wang, Z. et al. (2026). [MASPO](https://arxiv.org/abs/2605.06623). arXiv:2605.06623.

### llive 内部 cross-reference

- `docs/requirements_v0.B_evolutionary_optimization.md`
- `docs/requirements_v0.C_llive_variant_evolution.md`
- `docs/requirements_v0.D_self_referential_and_llm_operators.md`
- `docs/requirements_v0.8_cognitive_mesh.md` (TonicRiskMonitor / Quarantine)
- `src/llive/perf/evolutionary/llive_variant_extras.py` (v0.D 着地版)

### 関連 maintainer memory

- [[user-cognitive-mesh-model]] — 10 思考因子 (評価者人格の元素材)
- [[feedback-benchmark-honest-disclosure]] — H1-H3 honest 記録方針
- [[feedback-llive-measurement-purity]] — on-prem 限定
- [[project-cog-mesh-implementation-2026-05-19]] — TonicRisk / Quarantine
- [[project-llive-v0B-evolutionary]] / [[project-llive-v0C-variant-evolution]]
