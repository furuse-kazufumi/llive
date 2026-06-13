# Research Plan — Verified Neural Architecture Evolution on CPU

起草日: 2026-05-29  
著者: 古瀬 和文 (Kazufumi Furuse) — llive / FullSense  
位置付け: 投稿用研究計画書 (TMLR 本命 + GECCO short paper)  
依拠: `2026-05-29_core_evolution_master_survey.md` (Agent A-D + RAD 14 分野 + llive 実装読み)

---

## §0. Working Title (3 案、決定保留)

1. **"Verified Neural Architecture Evolution: Z3-Gated Selection Pressure for State-Update Rule Discovery on CPU"** ← **第 1 推奨**
2. "Cognition-Driven Adaptive Computation: Thought-Factor Hooks for Selective State Space Models"
3. "Mixing Learning Rules in Evolutionary Search: Backprop, Forward-Forward, Predictive Coding as Genes"

第 1 推奨を本論文、#2/#3 は本論文内の "Application" 章に組込む。後続論文として別出しも可。

---

## §1. Motivation (1-page abstract 骨格)

### 1.1 問題
LLM の重みは事前学習後に凍結が標準だが、**コア計算アルゴリズム自体 (attention 機構 / 状態保持 / 学習則 / トークン処理) は人手設計に固定**されている。AutoML-Zero (Real 2020) / NAS (DARTS 2018) / Sakana Evolutionary Model Merge (2024) / AlphaEvolve (DeepMind 2025) など architecture/algorithm 探索は進んだが:

1. **計算リソースが個人 compute では不可能** (TinyLlama 1.1B from scratch = $140k / 90 日 / 16×A100)
2. **探索中の安全性保証なし** = 数値不安定な architecture を生み出して時間を浪費
3. **検証付き探索の研究は静的 verification (Reluplex / Marabou / α,β-CROWN) と分断** — 進化ループの中で SMT/CROWN を online gate として使う研究は **未発見**

### 1.2 提案
**lldarwin_v2 進化集団** × **Z3 verifier-gate (online)** × **persona-indexed specialist** を組合せた CPU 完結の architecture evolution フレームワーク。寄与は 3 本:

1. **Z3 を進化ループ内で online 呼出し architecture 変異を事前 gate** — Agent B/D 確認の独自軸、negation work なし
2. **state update 規則を遺伝子化 (RWKV-7 backbone)** — Apache-2.0 GGUF で CPU 完結、論文化可能な PoC
3. **学習則 (Forward-Forward / Equilibrium-Prop / Predictive Coding / Hebbian) を gene として混在進化** — 先行未発見の独自軸

### 1.3 実験
- Backbone: **RWKV-7 0.19B** (Apache-2.0, CPU GGUF 配布) + 100M 級小 MLP (NAS-Bench-201 proxy)
- 進化 selector: lldarwin_v2 (ε-lexicase + novelty + 適応難易度 + factor-subspace QD + 中立貯蔵庫)
- Verifier: Z3 (構造) + Marabou Incremental (数値) bridge
- Task: 合成 sequence (recall / copy / addition) + TinyStories 10M + NAS-Bench-201 zero-cost proxy
- Baseline: 固定 RWKV-7 / DARTS / NAS-Bench-201 best
- 計測: best-of-population coverage / 系統多様性 / 進化進捗曲線 / 検証 reject 率

### 1.4 honest 留保
- 1B 級 scratch CPU 学習は不可能 = 機構実証 (mechanism feasibility) に絞る
- AlphaEvolve / TorchLean レベルの強さは目指さない、**CPU で動く verified 進化フレーム** が貢献軸

---

## §2. Background & Related Work

### 2.1 非 Transformer sequence models (Master Survey §2)
- Mamba/Mamba-2 (Gu & Dao 2023-2024, [arxiv 2312.00752](https://arxiv.org/abs/2312.00752))
- RWKV-7 "Goose" (Peng et al. 2025-03, [arxiv 2503.14456](https://arxiv.org/abs/2503.14456), Apache-2.0)
- RetNet (Sun et al. 2023, [arxiv 2307.08621](https://arxiv.org/abs/2307.08621))
- Hyena Hierarchy (Poli et al. 2023, [arxiv 2302.10866](https://arxiv.org/abs/2302.10866))
- Liquid NN / CfC (Hasani et al. 2022, [arxiv 2106.13898](https://arxiv.org/abs/2106.13898))
- Modern Hopfield (Ramsauer 2020, [arxiv 2008.02217](https://arxiv.org/abs/2008.02217))

### 2.2 Architecture search & evolution (Master Survey §3)
- AutoML-Zero (Real et al. 2020, [arxiv 2003.03384](https://arxiv.org/abs/2003.03384))
- DARTS (Liu et al. 2018, [arxiv 1806.09055](https://arxiv.org/abs/1806.09055))
- ENAS (Pham et al. 2018), AmoebaNet (Real et al. 2019)
- AlphaEvolve (DeepMind 2025-05) — API LLM call 前提
- ShinkaEvolve (Sakana 2025-09) — 150 sample で円パッキング SOTA
- WANN (Weight-Agnostic NN, Gaier & Ha 2019) — Raspberry Pi 移植実証あり

### 2.3 Verified ML (Master Survey §5)
- Reluplex (Katz 2017) → Marabou (Katz 2019-2024) → α,β-CROWN (UCLA, VNN-COMP 2021-2025 連続優勝)
- TorchLean (Anandkumar et al. 2026-02, [arxiv 2602.22631](https://arxiv.org/abs/2602.22631), NeurIPS 2026)
- Incremental NN Verification (Katz et al. 2026-03, [arxiv 2603.12232](https://arxiv.org/abs/2603.12232))
- Lipschitz NN (Trockman & Kolter ICLR 2021), Lyapunov-stable Mamba (2024)

### 2.4 Alternative learning rules (Master Survey §4)
- Forward-Forward (Hinton NeurIPS 2022, [arxiv 2212.13345](https://arxiv.org/abs/2212.13345)) — CIFAR 21% error (BP 劣勢, honest)
- Equilibrium Propagation (Bengio 2017, [arxiv 1602.05179](https://arxiv.org/abs/1602.05179))
- Predictive Coding (Whittington & Bogacz 2017, Zwol 2026-03 [arxiv 2603.06142](https://arxiv.org/abs/2603.06142) "PCG ⊃ MLP")
- Hebbian / STDP (古典)

### 2.5 Gap (差別化軸 — Master Survey §7)
- **進化ループ内 SMT/CROWN online gate** = WebSearch + RAD で**ヒットゼロ** (Agent A/B/D 確認)
- **学習則を gene として混在進化** = 先行**未発見** (Agent A/C verdict)
- **factor_hook (認知状態 → SSM Δ)** = 実装した先行**未発見**
- **persona-indexed specialist 集団 × verifier** = NAS は単一最良、進化集団 × verifier は**完全独自**

---

## §3. Method (詳細設計)

### 3.1 全体アーキテクチャ
```
[user task] → brief/ → cognitive_mesh (思考因子) → factor_hook (snapshot)
                                                        ↓
                            ┌── persona_evolution.run_persona_evolution ──┐
                            │  Genome3D (c_prompt + c_impl + c_meta)      │
                            │  + impl_chromosome (state_update_kernel,    │
                            │    learning_rule, persona_index)            │
                            │  ↓                                          │
                            │  lldarwin_v2 (ε-lexicase + novelty + ...)   │
                            │  ↓                                          │
                            │  ChangeOp 列                                │
                            │  ↓                                          │
                            │  ★ Z3 verifier-gate (online)              │
                            │  ├─ 構造 invariants (既存)                  │
                            │  ├─ 数値安定性 invariants (新規)            │
                            │  │  - state norm 有界                       │
                            │  │  - Lipschitz 制約                        │
                            │  │  - Hurwitz 固有値                        │
                            │  └─ Marabou Incremental bridge (新規)       │
                            │  ↓                                          │
                            │  ★ Approval Bus (HITL gate, 既存)          │
                            │  ↓                                          │
                            │  promotion to next generation               │
                            └─────────────────────────────────────────────┘
                                          ↓
                            backend/rwkv_backend.py (Δ hook 受信, 新規配線)
                                          ↓
                            evolution/verifier.py が ChangeOp を承認/棄却
```

### 3.2 寄与 1: Z3 verifier-gate (online)
- 既存 `verifier.py` (構造のみ) を以下で拡張:
  - **数値安定性 Z3 制約**: `state_norm <= K * input_norm` を Real 変数で encode
  - **Lipschitz 定量制約**: weight matrix の operator norm 上界を Z3 制約に
  - **Hurwitz 安定性**: SSM の transition matrix 固有値の |λ| < 1 を近似制約 (実装: 行列ノルム上界)
- 世代毎の online 呼出し: ChangeOp 列が SMT unsat → 個体棄却 (fitness 0)
- **Marabou Incremental bridge**: world越え conflict cache (refinement relation の sound 拡張)

### 3.3 寄与 2: state update 規則の遺伝子化
- `impl_chromosome.py` に新 gene 追加:
  - `state_update_kernel`: enum (rwkv_v7 / mamba_selective / hyena_conv / linear_attention / hopfield_dense / custom_rational)
  - `state_decay_form`: 有理関数族 (exponential / polynomial / sigmoid_gated / ...)
- 各 kernel の parameter 5-10 個を gene として配線
- `lldarwin_v2` で進化、fitness = 合成 sequence task (CPU 完結)
- 進化後の best individuals を `backend/rwkv_backend.py` で実機計測

### 3.4 寄与 3: 学習則の混在進化
- `impl_chromosome.py` に `learning_rule` gene 追加:
  - enum: backprop / forward_forward / equilibrium_prop / predictive_coding / hebbian
- 各規則の minimal CPU 実装 (100M 級以下):
  - Forward-Forward: Hinton 2022 のオリジナル goodness function
  - Equilibrium Propagation: Bengio 2017 の収束反復
  - Predictive Coding: Whittington & Bogacz 2017 の prediction error 更新
  - Hebbian: 古典 + STDP-like time window
- 同じ task で各規則の収束を進化集団内で混在比較 (Agent C honest: FF は CIFAR で BP に劣る)

### 3.5 factor_hook × RWKV-7 配線 (Path 0-α)
- `src/llive/backend/rwkv_backend.py` の time-mixing / channel-mixing の decay 係数を `ThoughtFactorDeltaHook.delta_for(snapshot)` で動的調整
- NoopFactorHook で baseline 等価、HeuristicFactorHook で測定可能変化
- 実 weight は不要 (純数式で hook 効果テスト)

---

## §4. Experimental Plan (CPU 完結)

### 4.1 Tasks
1. **Synthetic sequence** (Mamba/RWKV 標準): selective copy / induction head / addition / parity
2. **TinyStories 10M** (Agent C): CPU で train 可能、generation quality
3. **NAS-Bench-201** (Agent C): 15,625 pre-trained arch + Zero-Cost Proxies (snip / synflow / etc.) で proxy task

### 4.2 Baselines
- 固定 RWKV-7 0.19B (Apache-2.0, GGUF)
- DARTS (NAS-Bench-201)
- ShinkaEvolve (個人 compute 最有力先行)
- WANN baseline (CPU + 進化系の reference)

### 4.3 Metrics
- best-of-population coverage (task pass rate)
- 系統多様性 (lineage entropy)
- 進化進捗曲線 (best fitness 経時)
- **検証 reject 率** (Z3 gate でのフィルタ率 = 探索効率指標)
- wall-clock (CPU only)

### 4.4 Ablation
- Z3 gate ON/OFF (探索効率への寄与確認)
- factor_hook ON/OFF (Δ 動的化の効果)
- learning_rule fixed (backprop) vs evolved (混在進化)
- persona-indexed ON/OFF (specialist 維持効果)

### 4.5 HONEST 規律
- ベースライン側を不当に弱めない (固定 RWKV-7 は GGUF 公式重み)
- 異常に良い結果は内訳を疑う ([[feedback_benchmark_honest_disclosure]])
- on-prem only / measurement purity ([[feedback_llive_measurement_purity]])
- proxy task と実機の乖離を明示
- Forward-Forward は CIFAR で BP 劣勢の honest を再現

---

## §5. Timeline & Milestones

| Phase | 期間 | 内容 | Output |
|---|---|---|---|
| **Stage 0-α** | 1-2 week | factor_hook × RWKV-7 配線 | `rwkv_backend.py` + tests |
| **Stage 0-β** | 1-2 week | L4 state update 進化 PoC | `poc_state_update_evolution.py` + 数値結果 |
| **Stage 0-γ** | 2-3 week | Z3 verifier 数値不変量 | `verifier.py` 拡張 + tests |
| **Stage 0-δ** | 3-4 week | 学習則進化 gene 追加 | `impl_chromosome.py` 拡張 + PoC |
| **Stage 0-ε** | 4-6 week | Marabou Incremental bridge | `marabou_bridge.py` + sound 拡張証明スケッチ |
| **Stage 0-final** | 6-8 week | TMLR draft + GECCO short | 投稿 |
| **Stage 1** | 新 PC 後 1-3 mo | 100M 級小モデル実機検証 | full paper |
| **Stage 2** | 3-12 mo | L5/L6 拡張、VNN-COMP 新カテゴリ提案 | follow-up paper |

---

## §6. Venue Strategy

### 6.1 Primary: TMLR (Transactions on Machine Learning Research)
- peer review, no hard deadline
- 「実装 + 実験 + theory」のバランスを評価する伝統あり
- 投稿準備: §3 method + §4 experiments + Stage 0 結果が揃ったら

### 6.2 Secondary: GECCO short paper (or workshop)
- Evolutionary Computation コミュニティで visibility
- "Verified Architecture Evolution" は新規性訴求しやすい
- abstract deadline 通常 Jan/Feb → 2027 GECCO を狙う

### 6.3 Possible: NeurIPS 2026 workshop (verification × ML)
- TorchLean と並ぶ枠
- llive verifier.py + Marabou bridge を「online 検証」枠で

### 6.4 Long shot: AAAI 2027 (formal methods × ML), ICLR 2027 (main track)

---

## §7. Differentiation from concurrent work

### 7.1 vs AlphaEvolve (DeepMind 2025-05)
- AlphaEvolve: LLM × evaluator、API call 前提
- llive: **CPU only**、**verifier-gated**、persona-indexed 進化集団
- 質的差別化: AlphaEvolve は「正しいか証明された後の fitness」、llive は「**正しさが進化選択圧そのもの**」

### 7.2 vs TorchLean (Anandkumar 2026-02)
- TorchLean: 学習済 NN の入出力性質を Lean 4 で証明 (値領域)
- llive: ChangeOp 列の構造変更を Z3 で gate (構造領域)
- **直交、合流可能** (Agent D verdict): TorchLean を高優先度個体の full verification に使う

### 7.3 vs ShinkaEvolve (Sakana 2025-09)
- ShinkaEvolve: 150 sample で SOTA、open-source、個人 compute に最も近い
- llive: 同じ sample efficient + **verifier prune** で更に探索空間を絞る

### 7.4 vs CDGP (Krawiec 2018)
- CDGP: 記号プログラム合成、反例 → fitness フィードバック (**事後**)
- llive: NN architecture、**事前** Z3 gate (反対方向)

---

## §8. Open Questions (明朝確認用)

1. RWKV-7 の time-mixing decay 係数を factor_hook で動かす際、**学習済 weight の robustness** は保たれるか? (純数式 hook なら影響なしと想定だが要実証)
2. Z3 で SSM state norm 有界性を表現する **計算量** が進化ループに耐えるか? (1 個体あたり <1 sec を目標)
3. 学習則 (FF/EP/PCN) 混在の **fairness 評価**: 同じ task で fair に比較する protocol が必要
4. Marabou Incremental の refinement relation を「異なる構造」に拡張する **soundness 証明** はどこまで詰めるか?
5. TMLR の reviewer に対する「CPU only」の弱点弁明 (機構実証であってスケール実証ではない、新 PC 後に Stage 1 で扱う)

---

## §9. Linked Memory

- [[project_llive_optimization_cycle]] — llive 最適化フェーズ
- [[project_lldarwin]] — 選択圧コンポーネント
- [[goal_surpass_mythos_evolutionary]] — 棚上げ goal、本研究計画書はその継続派生
- [[project_persona_genome_integration]] — persona × ペルソナ × verifier 実装着地済
- [[feedback_qwen_commercial_barrier]] — RWKV-7 軸足の根拠 (Qwen 脱却)
- [[feedback_benchmark_honest_disclosure]] — 実験規律
- [[feedback_llive_measurement_purity]] — on-prem only 純度

---

## §10. Honest 留保 (この計画書の制限)

- Agent A-D は WebSearch + RAD で確認したが、未公開社内研究の存在は排除不能
- "online architecture evolution verification" の正式な survey は未経由 (Google Scholar 直当たり / OpenReview 通覧は別 session で)
- Marabou Incremental の "異なる構造" への refinement relation 拡張は **本計画書ではスケッチのみ**、soundness 証明は実装段階で詰める
- Stage 0 の wall-clock 見積もり (week 単位) は経験則、laptop CPU での実測未取得
- 投稿先優先順 (TMLR > GECCO > NeurIPS workshop) は私の判断、co-author / advisor 不在で peer review が必要

---

**Status**: 計画書 v1 完成 (2026-05-29 朝)。次は Stage 0-α (factor_hook × RWKV-7 配線) 実装着手。
