# Core Evolution Master Survey — llive Transformer-Algorithm Evolution on CPU

調査日: 2026-05-28 ～ 2026-05-29  
Goal (ユーザー設定): 明日朝までにコア進化 (Transformer 本体に進化形態を与え異アルゴリズムへ進化させる) に必要な内容を徹底調査。  
規律: 一次情報 URL 必須。曖昧な引用は「要追跡」と明示。CPU 実機検証できない論点は honest 留保へ。

統合元:
- Agent A: `2026-05-28_presurvey_verified_arch_evolution.md` (非 Transformer 系 + Forward-Forward + AlphaEvolve + 学習則代替 + CPU 実機現実性) **完了**
- Agent B: `2026-05-28_presurvey_verified_evolution_existing.md` (Verified NAS × Z3 × 進化既存研究) **進行中**
- Agent C: `2026-05-28_presurvey_small_compute_evolution.md` (個人 compute での architecture/algo evolution 事例) **進行中**
- Agent D: `2026-05-28_presurvey_verifier_stack.md` (Lean 4 / Z3 / Marabou / 進化中 invariant 検査) **進行中**
- RAD コーパス横断 grep: 14 分野 (neural_network / deep_learning / llm / automated_theorem_proving / formal_methods / cognitive_ai / optimization / information_theory / mlops / agents / multimodal / diffusion / compiler / distributed_systems)
- llive 既存実装: `verifier.py` / `impl_chromosome.py` / `meta_chromosome.py` / `factor_hook.py` / `genome_3d.py` / `lldarwin_v2.py`

---

## §1. 結論先出し (この調査で確定したこと)

### 1.1 独自軸として立つ (gap 確定)
- **「進化探索の selection pressure に SMT/CROWN 検証を組込んだ先行研究 = 未発見」** (Agent A § 差別化マトリクス, 2026-05-28 検索時点)
- **「学習則 (Forward-Forward / Equilibrium-Prop / Predictive Coding / Hebbian) を gene として混在進化した明示先行 = 未発見」** (Agent A 同)
- **「factor_hook (認知状態 → SSM Δ 動的化) を実装した先行 = 未発見」** (RAD + Web)
- **「persona-indexed specialist 集団 with verifier」** (NAS は単一最良を探す、進化集団 × verifier は llive 独自)

### 1.2 最も近い先行 (差別化が要る)
- **AlphaEvolve** (DeepMind 2025-05) = LLM × evaluator で Strassen 4×4 を 56 年ぶり更新。**API LLM call 前提で「純 CPU only」でない** (Agent C verdict) → llive が CPU only を主張するなら **AutoML-Zero 系 (prim ベース) に軸足**
- **TorchLean** (Anandkumar/Caltech 2026-02, NeurIPS) = Lean 4 で NN の数学的健全性検証 (IEEE-754 Float32 / IBP / CROWN / Lyapunov controller)。**llive 差別化軸 = ChangeOp 構造変更の online verify**
- **Incremental NN Verification** (Marabou 2026-03) = branch-and-bound に conflict learning 追加、1.9x speedup。**llive への統合機会** (外部資産として使える)
- **CDGP** (Krawiec IJCAI/EvoComp 2018) = **唯一の "進化 × 形式手法" 直接 hit**。ただし記号プログラム合成 (LIA/SLIA) で NN ではない + 反例 → fitness フィードバック (**事後**) で llive の**事前 gate** と方向が逆 (Agent B verdict)
- **ShinkaEvolve** (Sakana 2025-09) = 150 sample で円パッキング SOTA、open-source、個人 compute に最も近い実装

### 1.4 Agent B/C 確定 verdict (撤退不要)
- **negation される work は確認できず** (Agent B verdict)
- Reluplex / Marabou / α,β-CROWN / ERAN / DeepPoly / NeuralSAT — すべて **学習後 NN の入出力性質検証**、アーキ変異列の事前 gate は誰もやっていない
- Lipschitz (Trockman & Kolter ICLR 2021) / Mamba 安定性 (Sparse Mamba, Lyapunov-stable Mamba 2024) / LTC Theorem 2 (Hasani AAAI 2021) は厚いが **進化ループ内 SMT gate への embedding は未踏**
- AutoML-Zero フォロー direct は **少ない = llive 未開拓領域**
- PBT / Sakana Evo Merge / AlphaEvolve / LLMatic (GECCO 2024) — **全て evaluator-based 事後 scoring**、事前 formal gate は不在

### 1.3 CPU 実装の現実線
- **最現実パス = RWKV-7 0.19B / 0.4B + Mamba-130M** (Apache-2.0 GGUF 確定、llama.cpp 取り込み済)
- 1B 級 scratch CPU 学習は **不現実** (TinyLlama 1.1B from scratch は $140k / 90日 / 16×A100, Agent C 実測引用)
- **BitMamba-2 (1.58-bit) が i3-12100F で 50 tok/s** = CPU LLM の最新到達点 (Agent C)
- **TinyStories 10M は CPU 数日で train 可能** (Agent C)
- NAS proxy task は **NAS-Bench-201 (15,625 arch pre-trained) + Zero-Cost Proxies** が de facto (Agent C)
- **WANN (Weight-Agnostic Neural Network) は Raspberry Pi 移植実証あり**、CPU 親和性高 (Agent C)
- **Forward-Forward は CIFAR 21% error (BP 劣勢)** honest disclosure (Agent C, Hinton NeurIPS 2022)

---

## §2. 非 Transformer 系 sequence model (Agent A 結果のサマリ)

(詳細は Agent A 出力ファイル `2026-05-28_presurvey_verified_arch_evolution.md` § A)

| # | モデル | CPU 可否 | ライセンス | llive 着地容易度 |
|---|---|---|---|---|
| A-1 | Mamba / Mamba-2 | ✓ (llama.cpp PR#5328/9126) | Apache-2.0* | factor_hook protocol 着地済、kernel 未接続 |
| A-2 | **RWKV-7 "Goose"** | ✓ (constant memory, GGUF 配布) | Apache-2.0 確定 | **rwkv_backend.py skeleton 着地、即着手可** |
| A-3 | RetNet | △ (公式 release 要追跡) | 要追跡 | 後回し |
| A-4 | Hyena | △ (FFT-conv は CPU 可、GGUF 未確認) | Apache-2.0* | 中期 |
| A-5 | Liquid NN / CfC | ✓ (pure PyTorch, 制御タスク) | 要追跡 | 別領域 (時系列) |
| A-6 | Modern Hopfield | ✓ (MLP 2 層相当) | repo ごと | factor_hook と直結する可能性大 |

*Apache-2.0 印は HF/GitHub 表記、LICENSE 直接確認は Agent A の honest 留保 (要追跡)。

**注目**: RAD `cluster_01_mamba_attention` (145 docs) は Vision Mamba 中心で純粋 LM 用は少。RWKV-7 が **CPU + Apache-2.0 + GGUF 三拍子揃った唯一の選択**。

---

## §3. アーキテクチャ進化系 (Agent A § B 要約)

| # | 研究 | 主張 | CPU 個人 compute での到達点 |
|---|---|---|---|
| B-1 | AutoML-Zero (Real 2020) | 基本演算から ML 進化発見 | 学習則レベルは cluster 規模、個人で部分再現は困難 |
| B-2 | DARTS (Liu 2018) | continuous relaxation で勾配 NAS | 高速だが local minimum 危険 |
| B-3 | ENAS (Pham 2018) | weight sharing で NAS 高速化 | 個人 compute で動く |
| B-4 | AmoebaNet (Real 2019) | regularised evolution | 高 compute |
| B-5 | **AlphaEvolve** (DeepMind 2025-05) | LLM × evaluator で algorithm 発見、Strassen 4×4 を 56 年ぶり更新 | 個人で再現は困難 |
| B-6 | Sakana Evolutionary Model Merge (2024) | モデル合体を進化探索 | OSS 公開、個人で動く |

**llive 差別化**: Z3 verifier-gate, Approval Bus, persona-indexed specialist 集団。AlphaEvolve は LLM 中心だが llive は genome + structural verifier 中心。

---

## §4. 学習則代替 (Agent A § C 要約)

| 規則 | 一次出典 | CPU 可否 | llive 既存 |
|---|---|---|---|
| Forward-Forward (Hinton 2022) | NeurIPS 2022 keynote, [arxiv 2212.13345](https://arxiv.org/abs/2212.13345) | ✓ (小モデル) | 未実装 |
| Equilibrium Propagation (Bengio) | [arxiv 1602.05179](https://arxiv.org/abs/1602.05179) | ✓ (収束遅) | 未実装 |
| Predictive Coding (Friston/Millidge) | [Whittington & Bogacz 2017](https://www.cell.com/trends/cognitive-sciences/abstract/S1364-6613(18)30246-6) | ✓ | **cognitive_mesh で予告のみ、配線未** |
| Hebbian / STDP | 古典 + [Magotra & Kim 2020](https://arxiv.org/abs/2002.07642) | ✓ | 未実装 |

**RAD 発見**: `cognitive_ai_corpus_v2/cluster_02_bayesian_brain/c_02_coding_bp_neural` (9 docs) = predictive coding × NN の鉱脈。  
**重要 paper**: Zwol 2026-03 [arxiv 2603.06142](https://arxiv.org/abs/2603.06142) "Predictive Coding Graphs are a Superset of Feedforward Neural Networks" = **PCG は MLP の数学的 superset** = llive の方向性に学術的根拠。

**独自軸候補**: 「学習則を impl_chromosome の gene として混在進化」(Agent A も未発見と verdict)。

---

## §5. 形式検証 × NN (RAD + Agent D 結果)

### 5.1 RAD `automated_theorem_proving_corpus_v2` 直接ヒット

#### **TorchLean** (arxiv 2602.22631, Anandkumar et al., NVIDIA/Caltech 2026-02, NeurIPS)
- Lean 4 で PyTorch-style verified API、Float32 IEEE-754 executable kernel、IBP + CROWN/LiRPA bound propagation、proof-relevant rounding model
- end-to-end 実証: certified robustness / PINNs / Lyapunov controller / mechanized universal approximation theorem
- **llive verifier.py との関係**: 別レイヤ。TorchLean = NN 内部の数値健全性、llive = ChangeOp の構造保存。**補完可能**

#### **Incremental NN Verification via Learned Conflicts** (arxiv 2603.12232, Katz et al. 2026-03, Marabou 拡張)
- branch-and-bound verifier に conflict learning 追加、infeasible activation phase 組合せを再利用、SAT solver で consistency 検査
- 1.9x speedup
- **llive への統合可能性**: 進化ループ内で「architecture 変異後の verification」を高速化する**外部資産**

#### **Formal verification of tree-based ML** (arxiv 2603.16983, Krishna Kumar 2026-03)
- SMT で tree ensemble の物理制約検証 (water table depth / PGA monotonicity 等)
- 「verify-fix-verify」エンジニアリングループ提案
- **llive との関係**: 概念的に一致。tree 系を NN architecture 進化に拡張する道筋

### 5.2 補足 RAD 発見
- TorchLean 関連の Lean 4 × NN 系統: Nazrin (GNN for theorem proving), TorchLean が中核
- `formal_methods_corpus_v2` は AI Safety / LLM verification 中心、純粋 NN architecture 検証は少
- `cognitive_ai_corpus_v2/cluster_02_bayesian_brain` = predictive coding × NN の鉱脈

### 5.3 Agent D 結果 (進行中、ここに統合予定)
> [Agent D の `2026-05-28_presurvey_verifier_stack.md` 完了後マージ]

---

## §6. llive 既存実装の現状解析 (実装読込結果)

### 6.1 `src/llive/evolution/verifier.py` (EVO-04 / FR-13)
- **構造的検査** (常時 on, dep なし): min_blocks (1) / max_blocks (64) / essential_types (pre_norm, causal_attention, ffn_swiglu) / require_attention / require_memory_pair (read 必須なら write も) / unique name
- **SMT 層** (opt-in, z3): state vector = (n_blocks, has_attention, has_memory_read, has_memory_write) を ChangeOp 列で追跡
- **ChangeOp 種別**: InsertSubblock / RemoveSubblock / ReplaceSubblock / ReorderSubblocks
- **最終状態のみ検査** (中間状態は許容 = 進化の途中状態に優しい)
- **未対応**: 数値安定性、Lipschitz 境界、SSM state norm 有界性、固有値制約 = **state update 規則の数学的不変量は手付かず**

### 6.2 `src/llive/perf/evolutionary/impl_chromosome.py` (EV-13 柱 A-1)
- gene 8 種: impl_language / algorithm_family / parallel_strategy / agi_usage_ratio / orchestration_mode / memory_backend / selector_class / judge_model
- **AutoML-Zero と Promptbreeder を参照に明記** (docstring)
- **status: skeleton**, 実 EvolutionLoop 統合は EV-14 以降
- **拡張余地**: **`learning_rule` gene (backprop / FF / EP / PCN / Hebbian)** と **`state_update_kernel` gene (SSM / RWKV / Hyena / Hopfield / linear-attention)** の追加が L4/L5 路線

### 6.3 `src/llive/perf/evolutionary/meta_chromosome.py` (EV-21)
- 進化アルゴリズム**自体**を遺伝対象: 層別 mutation rate / crossover strategy / selection pressure / novelty weight / cluster quota / meta mutation decay / algorithm_id
- algorithm_id 既知値: tournament_gauss / tournament_meta / nsga2_novelty / map_elites_niche / self_adaptive_sigma
- **Schmidhuber Gödel Machines / Hutter AIXI / AutoML-Zero / Promptbreeder を参照**
- **status: skeleton**, sandbox AST 実行 + EvolutionLoop 統合は EV-22 以降

### 6.4 `src/llive/llm/factor_hook.py` (非 Transformer ROADMAP case C)
- 10 思考因子 (structurize / reconstruct / closed_loop / self_extension / uncertainty / exploration / integrate / provenance / perspective / reality_contact) を `FactorSnapshot` で保持
- `ThoughtFactorDeltaHook` Protocol: `delta_for(snapshot) -> float` (Δ 乗法係数)
- `NoopFactorHook` (常に 1.0) / `HeuristicFactorHook` (uncertainty 高 → 小 Δ / integrate+structurize 高 → 大 Δ)
- **設計**: Mamba SSM kernel 接続が Phase 5 deferred、RWKV-7 接続は最現実
- **未配線**: RwkvPyBackend / MambaBackend ともに factor_hook を **consume していない**

### 6.5 結合済資産
- `lldarwin_v2.py` = ε-lexicase + novelty + 適応難易度 + factor-subspace QD + 中立貯蔵庫 + MAP-Elites
- `quality_diversity.py` (MAPElitesGrid + FactorSubspaceNovelty)
- `lineage_reservoir.py` (絶滅系統 re-inject)
- `pressures.py` (proxy 5 苦手軸) + `real_pressures.py` (実 LLM 評価)
- `evolution/wiki_change_op.py` (LLW-05) — Wiki + ChangeOp = ラッパー脱却の動作中経路

---

## §7. 差別化マトリクス (確定版)

| 主張 | 既存 (overlap 度) | llive 独自度 | 論文化価値 |
|---|---|---|---|
| **Z3 で architecture 変異 online gate** | TorchLean 静的検証 / tree ML 単発 (中) | **完全独自** (進化ループ内 online) | ★★★ |
| **学習則を gene として混在進化** | AutoML-Zero (基本演算) / Sakana Merge (重み) (低) | **完全独自** (規則そのもの) | ★★★ |
| **factor_hook 認知駆動 Δ** | 予告は予測符号化系にあるが実装は未発見 (低) | **完全独自** | ★★★ |
| **persona-indexed specialist 集団 × verifier** | NAS = 単一最良 (なし) | **完全独自** | ★★ |
| **Lipschitz / 数値安定 制約進化** | TorchLean が CROWN/LiRPA (中) | LLM 全体でなく SSM state update に絞れば独自 | ★★ |
| **Approval Bus = fitness の 1 dim 化** | RLHF / HITL 系 (一部) | architecture 進化での HITL は未発見 | ★★ |
| **RWKV state update rule の進化** | RWKV 系列改良は人手 (なし) | **完全独自** | ★★★ |
| **Wiki + ChangeOp による認知主体移し替え** | Karpathy LLM Wiki 着想 (低) | **完全独自実装** | ★ (動作中) |

---

## §8. CPU 実装パスの提案 (Stage 0-2)

### Stage 0: 今夜〜1 週間で踏み込める (CPU 完結)

#### Path 0-α: **factor_hook × RWKV-7 受け取り側実装** (Task #3)
- `src/llive/backend/rwkv_backend.py` で `ThoughtFactorDeltaHook` を consume
- RWKV-7 の time-mixing / channel-mixing の decay 係数を Δ 比例で動かす
- NoopFactorHook で既存挙動と等価、HeuristicFactorHook で測定可能変化
- 実 weight は不要 (純数式で hook 効果テスト可)
- 価値: factor_hook protocol を「skeleton + テスト」から「動作 + 計測可能」に格上げ

#### Path 0-β: **L4 状態保持の進化 PoC** (Task #4)
- `scripts/poc_state_update_evolution.py` 新規追加
- RWKV state update を少パラメータ式 (decay / gate / mix の有理表現) で表現
- impl_chromosome に `state_update_kernel` gene を**追加配線** (= L4 を本配線)
- lldarwin_v2 で進化、fitness = 合成 sequence recall / copy / addition (CPU 完走)
- 価値: 「state update を gene として進化」の動作実証 = 論文 §3 PoC

#### Path 0-γ: **Z3 verifier の state-update 不変量制約** (Task #5)
- `evolution/verifier.py` を拡張
- 進化生成された state update 規則について Z3 で:
  - 数値安定性: `state_norm ≤ K * input_norm` の satisfiability
  - decay 非負: `decay >= 0`
  - mix 係数和: `sum(mix_i) <= 1`
  - 固有値制約: `|eigenvalue| < 1` (Hurwitz 安定性, 近似)
- 破綻変異を機械的排除 → 進化探索効率上昇 = **llive 独自軸の論文化材料**

#### Path 0-δ: **学習則進化の gene 追加** (新規 Task)
- `impl_chromosome.py` に `learning_rule` gene (backprop / FF / EP / PCN / Hebbian)
- 各規則の実装は CPU 完結の minimal (Hinton FF 2022, Bengio EP)
- PoC: MNIST/CIFAR-10 char-level small NN で各規則の収束を進化集団で比較
- 価値: もう 1 本の独自軸 (Agent A も先行未発見と verdict)

### Stage 1: 新 PC 着任後 (1-3 ヶ月)
- Mamba CUDA kernel × factor_hook 実接続
- 100M-1B 級小モデルで進化ループ、ベースライン (固定 Transformer) 実測超え検証
- NAS-Bench で proxy task 進化計算の baseline

### Stage 2: 研究としてのスケール (3-12 ヶ月)
- L6 (AutoML-Zero × Z3 verifier) を限定領域で挑戦
- L5 (学習則進化) を 100M 級小モデルで PoC
- 論文投稿 (TMLR / GECCO / NeurIPS workshop / AAAI verifier 系)

---

## §9. 残課題 / 未確認領域

### 9.1 まだ走行中の Agent (明朝までに統合)
- Agent B: Verified NAS × Z3 既存研究の overlap 深掘り (TorchLean / Marabou との関係、VNN-COMP 2024-2025)
- Agent C: 個人 compute での architecture/algo evolution 事例 (AlphaEvolve / Sakana / GECCO best papers)
- Agent D: Lean 4 / Z3 × NN 最新到達点 (TorchLean 深掘り + llive verifier.py 拡張計画)

### 9.2 未確認 (Agent A honest 留保 + 私の追加)
- Mamba / safari / mergekit / CfC の LICENSE ファイル直接確認 (Apache-2.0 推定)
- RetNet 公式 CPU release / Forward-Forward Hinton 公式実装の所在
- "Verified Architecture Evolution as Selection Pressure" の Google Scholar / OpenReview / GECCO 直当たり
- Windows CPU で 100M-1B 級 scratch 学習の実測一次資料
- VNN-COMP 2024/2025 の online / incremental 検証カテゴリの存在有無
- 「Lipschitz 制約 NAS」の最新

### 9.3 PoC が必要 (CPU で着手可)
- PoC #4 candidate: RWKV-7 0.19B + α,β-CROWN small-cell の feasibility 1 日 spike
- PoC #5 candidate: factor_hook × RWKV-7 の Δ 比例 time-decay 効果計測
- PoC #6 candidate: Z3 で state update 規則の satisfiability 確認

---

## §10. 投稿先候補と研究計画書のスケルトン

### 10.1 投稿先 (差別化が立つ前提)
- **TMLR** (peer review, no hard deadline) — 研究計画書を磨いて投稿
- **GECCO 2026** (Evolutionary Computation, July, abstract deadline ~ Jan/Feb) — 「Verified Architecture Evolution」直球
- **NeurIPS 2026 workshop** (verification × ML) — TorchLean と並ぶ枠
- **AAAI 2027** (formal methods × ML)
- **ICLR 2027** (本丸、long shot)

### 10.2 タイトル案
- "Verified Neural Architecture Evolution: Z3-Gated Selection Pressure for State-Update Rule Discovery on CPU"
- "Cognition-Driven Adaptive Computation: Thought-Factor Hooks for Selective State Space Models"
- "Mixing Learning Rules in Evolutionary Search: Backprop, Forward-Forward, Predictive Coding as Genes"

### 10.3 1-page abstract 骨格
- 動機: LLM の重みは凍結が標準だが、コア計算アルゴリズム自体は人手設計に固定
- アプローチ: lldarwin_v2 進化集団 × Z3 verifier-gate × persona-indexed specialist
- 寄与 1: state update 規則を遺伝子化、CPU で安全に進化
- 寄与 2: Z3 で構造変異の数値安定性を online gate
- 寄与 3: 学習則 (FF/EP/PCN/Hebb) を gene として混在進化
- 実験: RWKV-7 0.19B 級、合成 sequence task + 小規模 MNIST/CIFAR
- 限界: スケールは GPU 待ち、本論文は CPU で動く機構実証

---

## §11. 次のアクション (明朝に向けた)

1. Agent B/C/D 完了通知を待ち、各成果物を **§5.3 / §3 / §6 拡張** にマージ
2. 統合確定後、研究計画書 (Task #2) を 1 本に: `2026-05-29_research_plan_core_evolution.md`
3. 実装着手 (Task #3 → #4 → #5): factor_hook × RWKV 受け取り → state update 進化 PoC → Z3 不変量
4. memory に `project_core_evolution_survey_2026_05_28` を 1 行追加 (差別化軸の保存)

---

## §12. honest 留保 (この doc の制限)

- Agent B/C/D 完了前の中間 doc。最終版は明朝。
- 一次情報 URL は Agent A 出力ベース、自分で開いて再確認していないものは Agent A の honest 留保を継承
- RAD 横断 grep は 14 分野に対して 7 grep のみ実行。残り (industrial_iot / cryptography / hci / aerospace / multimodal / diffusion / agents) は時間が許せば追加
- 「未発見」と verdict した独自軸は「Web + RAD で見つけられなかった」という意味で、絶対的な不在を主張するものではない
