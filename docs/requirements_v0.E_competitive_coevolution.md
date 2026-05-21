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
