# Verified Neural Architecture Evolution — Verifier Stack Survey

**作成日**: 2026-05-28
**担当**: Agent D (verifier stack)
**並列担当**: Agent A (非 Transformer) / Agent B (Verified NAS) / Agent C (個人 compute)
**目的**: llive `src/llive/evolution/verifier.py` (Z3 ベース構造不変量検査、既存実装) と既存研究の overlap/gap を確定し、論文化可能な独自軸を抽出する。

---

## A. TorchLean 詳細 (arxiv 2602.22631)

**一次情報**:
- 論文: <http://arxiv.org/abs/2602.22631v1> (George, Cruden, Zhong, Zhang, Anandkumar; 2026-02-26 投稿; Caltech/UIUC 系)
- 実装: <https://github.com/nktkt/leanx> (TorchLean: Formalizing Neural Networks in Lean 4 — IBP, CROWN, α,β-CROWN verification framework)
- RAD: `D:/docs/automated_theorem_proving_corpus_v2/2602.22631_TorchLean_*.md`

**主張**: NN を Lean 4 の一級数学対象として扱い、実行と検証で同一 semantics を共有させる枠組み。「定義された network」と「検証された artifact」の semantic gap (演算子セマンティクス、tensor layout、preprocessing、浮動小数点 corner case) を Lean 4 で閉じる。

**形式化範囲**:
1. **PyTorch 風 verified API**: eager / compiled 両モードが同一 op-tagged SSA/DAG 計算グラフ IR に落ちる
2. **Float32 semantics**: IEEE-754 binary32 を実行可能 kernel として Lean 内に実装 + proof-relevant rounding model
3. **検証 backend**: IBP (Interval Bound Propagation) + CROWN / LiRPA 風 bound propagation + certificate checking
4. **検証ずみ応用**: certified robustness, PINN の residual 上界, Lyapunov 風 neural controller, universal approximation theorem の mechanized 証明

**llive 既存 (Z3 verifier) との関係**:
- TorchLean は **値領域** (weights / activations / float corner case) の formal verification
- llive は **構造領域** (subblock 数 / type / attention-memory 整合性) の SMT 検査 — 抽象度が直交
- ⇒ **競合ではなく合流余地あり**: TorchLean は「あるアーキ A が robustness 不変量を満たすか」、llive は「アーキ A → B 変異が essential type 不変量を破らないか」

**統合可能性 (具体的)**:
1. **layer 1**: llive Z3 で構造変異 (subblock 増減) を gate (現状)
2. **layer 2**: 変異後アーキを TorchLean IR に lower、CROWN bound で robustness 不変量を再確認 (拡張案)
3. ただし TorchLean は LirPA/CROWN を Lean 内で証明付き計算するため **計算コストが極めて高い** (執筆時点で MNIST/CIFAR スケール)。1000 世代 × 数 ms の進化ループに直接 inline するのは不可。Tier B sampling 検証 (10 世代に 1 回) が現実的。

---

## B. Incremental NN Verification via Learned Conflicts (arxiv 2603.12232)

**一次情報**:
- 論文: <http://arxiv.org/abs/2603.12232v1> (Elsaleh, Davis, Wu, Katz; 2026-03-12 投稿; Hebrew U / Stanford / Amherst 系 = Katz 系列)
- RAD: `D:/docs/automated_theorem_proving_corpus_v2/2603.12232_Incremental*.md`
- 実装: Marabou に統合 (Marabou 2.0 の CDCL 拡張系列、<https://link.springer.com/chapter/10.1007/978-3-031-65630-9_13>)

**何を漸進的に行うか**:
- 「同じ network に対する **連続した関連 verification query** (例: robustness radius 探索の二分探索、入力分割、minimal sufficient feature 抽出)」での **conflict 再利用**
- Branch-and-bound 中に「ReLU activation phase の infeasible な組合せ」(= conflict) を学習・記録し、**次の query に持ち越す**
- Refinement relation を形式化し、「ある query の conflict は refined query でも sound」と証明 → conflict inheritance
- 継承された conflict は SAT solver に渡し、consistency check + propagation で 早期 prune

**結果**: non-incremental baseline 比で最大 **1.9× speedup** (3 タスク: local robustness radius / input splitting / minimal sufficient feature)

**進化ループ内 online 検証への応用可能性**:
- 進化ループは「同じ系統の network に対する **連続 query 列**」を生成する → **正に Incremental の前提が一致**
- 親アーキ verifier session の conflict を **子アーキ verifier session が継承**できれば理論的に高速化
- ただし論文は「同一 network・異なる input region」が前提。「異なる構造 (subblock 追加/削除)」での refinement relation は **論文範囲外** = llive 側で sound な拡張定義が必要 ← **論文化可能な独自軸**
- llive の `ReorderSubblocks` (count 不変) は trivially sound、`InsertSubblock` (count 増加) は新規 ReLU phase が conflict と独立であることの証明が要る

---

## C. VNN-COMP 2024 / 2025 結果

**一次情報**:
- 公式: <https://sites.google.com/view/vnn2024> (結果は GitHub repo 経由)
- 結果 repo: <https://github.com/ChristopherBrix/vnncomp2024_results>
- summary 論文: <https://arxiv.org/abs/2412.19985> (Brix et al.)
- α,β-CROWN VNN-COMP doc: <https://github.com/Verified-Intelligence/alpha-beta-CROWN/blob/main/complete_verifier/docs/vnn_comp.md>

**スケール**: 5th edition、8 teams、12 regular + 8 extended benchmarks

**ranking (確認できた範囲)**:
- **優勝**: α,β-CROWN (VNN-COMP **2021 / 2022 / 2023 / 2024 / 2025** 5 年連続優勝 — README 明記)
- 主要参加: CORA, Marabou, NeVer2, PyRAT
- α,β-CROWN は GPU 加速 linear bound propagation + branch-and-bound、Marabou は SMT 系 (CDCL 統合中)

**検証スケール**:
- ベンチマークは画像認識 (CIFAR-100 等)、cyber-physical system、ACAS Xu 等を含む
- 個別ネットワークの parameter 規模 (上限) は公開 spreadsheet で個別確認が必要だが、現代の VNN-COMP は **MNIST / CIFAR / ImageNet 小規模** が中心 (LLM スケールは現状不可)
- **honest 留保**: 4o/Llama スケールの **billion-parameter 検証** はまだ未踏。llive の小型アーキ (subblock 数 ≤ 64) は逆に **十分に検証可能なスケール** に収まる

**"incremental" / "online" / "NAS" カテゴリの有無**:
- VNN-COMP 2024 公開 summary・α,β-CROWN doc・関連レビューを精査した範囲では **incremental / online / NAS カテゴリは存在しない**
- 全ベンチマークは「固定ネットワーク + 入力領域 robustness」が前提
- ⇒ **「進化中の online 検証」は VNN-COMP の評価対象外 = 新規ベンチ提案余地あり** (llive 論文化の補助軸)

---

## D. Z3 × NN 系統 (Reluplex → Marabou → DNNV) と evolution × SMT

**系統樹**:
1. **Reluplex** (Katz 2017): Simplex を ReLU 対応に拡張、SMT theory として ReLU を持つ。元祖。
2. **Marabou** (Katz et al. 2019-): Reluplex の後継、より広いアクティベーション対応。**Marabou 2.0** (CAV 2024, <https://arxiv.org/abs/2401.14461>) で CDCL 機構統合中。Incremental conflict 学習 (B) の実装基盤。
3. **DNNV** (Shriver, Elbaum, Dwyer; CAV 2021, <https://arxiv.org/abs/2105.12841>): 統合フレームワーク。Reluplex / planet / MIPVerify / Neurify / ERAN / BaB / Marabou / nnenum / verinet を共通入出力で統一。benchmark 互換性 30% → 74%。

**SMT 系 vs 抽象解釈系**:
- **SMT 系** (Reluplex/Marabou): complete (sat/unsat 確定可能) だが scalability に難
- **抽象解釈系** (DeepPoly / CROWN / α,β-CROWN): incomplete (over-approximation) だが GPU 加速可能・大規模対応
- 現代の主流は **両者ハイブリッド**: bound propagation で over-approx → tight になったら branch-and-bound → 個別 split で SMT 風 exact reasoning (例: 2512.24379 "Incremental Certificate Learning for Hybrid NN Verification" <https://arxiv.org/html/2512.24379>)

**進化 / 探索ループ内で SMT を呼ぶ事例**:
- WebSearch + RAD クロスチェックでは **NAS / 進化アルゴリズム内で SMT を gate に使う論文は見当たらない**
- 隣接: 「Loop Invariant Generation with LLM + SMT」(ASE 2024, <https://arxiv.org/html/2508.00419>) — 但しこれは program verification、NN 構造ではない
- 隣接: 「Let a NN be your invariant」(Giacobbe; hardware model checking) — NN が invariant 生成器、検証対象ではない
- **llive の「進化ループ内で構造不変量を Z3 で online check」は SMT × evolutionary loop の希少例** = ★★★ 独自軸候補

---

## E. Lean 4 × NN の最新到達点

**到達点 (2026-02 〜 2026-03)**:
1. **TorchLean** (前述、2602.22631): IBP/CROWN を Lean 4 内で実装、Lyapunov controller / PINN まで mechanized
2. **Nazrin** (Aniva, Oikawa, Dill, Barrett; 2602.18767, <http://arxiv.org/abs/2602.18767v2>): **逆向き** — GNN を Lean 4 の theorem prover として使う。Atomic tactics (Lean で証明可能な任意命題を表現する有限小集合) + ExprGraph (Lean 表現の簡潔 graph 表現) + Transposing atomization (任意証明 → atomic tactic 列) + Nazrin Prover (GNN ベース) で consumer-grade hardware (個人 GPU 1 枚) で訓練・評価可能。Mathlib 標準ライブラリ定理を実証。
3. **Hopfield / Boltzmann** (2512.07766): Hopfield 収束証明 + Hebbian learning を Lean 4 で formalize、PhysLean (mathlib ベース physics ライブラリ) に PR 提出済
4. **Statistical Learning Theory** (2602.02285): Empirical processes を Lean 4 で from scratch 構築 = NN 一般化理論の土台

**Mathlib 内 NN 関連**:
- 完全形の NN 定義は **mathlib 本体には未統合**。tensor 表現の scalable 形式・sound differentiation・実行と接続できる数値 semantics の 3 つが gap として明示されている (TorchLean discussion 参照)
- ⇒ Lean 4 × NN は **2026 初頭時点でなお黎明期**、llive が今飛び込めば early mover

**"Verified backpropagation" 系**:
- 厳密 backprop 形式化は (執筆時点で確認できる範囲では) **TorchLean が proof-relevant rounding model + executable IEEE-754 kernel で最も近い**
- 純粋 backprop の機械検証 (Coq/Lean) は教科書例レベルで止まっており、現実 PyTorch op との bridge は TorchLean が最先端

---

## F. 「進化中に invariant 検査」既存事例

**結論 (honest)**: 私の手の届く範囲では **該当論文ゼロ**。

調査経路:
1. WebSearch: `"online verification" "neural architecture search" SMT solver invariant 2024` → 全て **loop invariant / hardware invariant 系**、NAS 内 online 検証は **ヒット無し**
2. WebSearch: `"Verified NAS" OR "Safe NAS" Lipschitz constrained` → 関連: **RACL** (Adversarially Robust NAS with Confidence Learning, <https://arxiv.org/pdf/2009.00902>) — Lipschitz 定数 *approximation* を NAS objective に組込み、但し **形式検証 (SMT/Lean) は使っていない**
3. WebSearch: `"approval bus" OR "human in the loop" verified NAS safe evolution 2025` → PBG (Population-Based Guiding) や EENA、GPT-NAS が出るが **HITL × verifier × evolution の 3 つを同時に持つ研究は見当たらない**
4. SSM 側: **L2RU** (<https://arxiv.org/pdf/2503.23818>) が L2-bound を parametrization 段階で保証、Lyapunov stability ベース parallelizable nonlinear SSM (<https://www.arxiv.org/pdf/2508.16817>) が出ているが、**これらは固定アーキの安定性保証**。「進化中の状態更新検査」とは交わらない

**意味**:
- 「進化 × 形式検証」は隣接領域 (Robust NAS, L2RU, TorchLean, Incremental NN verification) は埋まっているが **直交軸の組合せに gap**
- llive の Z3 verifier はこの gap に **既に実装で踏み込んでいる** (構造変異を Z3 で gate、Approval Bus で HITL gate) = 論文化価値あり

---

## G. llive 既存 verifier.py 解析

**ファイル**: `D:/projects/llive/src/llive/evolution/verifier.py` (243 行、Apache-2.0)

**現状検証している事**:
1. **構造的 pre-check (常時 on、外部依存なし)**:
   - subblock 参照数のカウント (`_signature`)
   - 禁止変異検出: 空 container / 必須 type の最後の block 削除 / 名前重複 / 参照を落とす reorder
   - 不変量: `min_blocks=1`, `max_blocks=64`, `essential_types=(pre_norm, causal_attention, ffn_swiglu)`, `require_attention`, `require_memory_pair` (memory_read あれば memory_write 必須)

2. **SMT layer (opt-in、Z3 import 可能なら)**:
   - 各 `ChangeOp` (`InsertSubblock` / `RemoveSubblock` / `ReplaceSubblock` / `ReorderSubblocks`) の state vector (`n_blocks`, `has_attention`, `has_memory_read`, `has_memory_write`) への影響を Z3 制約として encode
   - 初期 state + 各 op の transition + final state の不変量 を solver.add() → `solver.check() == sat` で trajectory が合法か確認
   - **重要**: 中間 state ではなく **final state のみ** で不変量を pin (memory_read insert → memory_write insert の二段で中間が transient に違反するのを許す)
   - Z3 未 install 時は `smt_used=False` で structural のみにフォールバック (degrade gracefully)

**設計の良いところ**:
- **2 層構造** (structural always-on / SMT opt-in) は VNN-COMP 系 hybrid アーキ (over-approx → exact) のミニチュア
- **final-state only invariant** は branch-and-bound の途中で transient 違反を許す現代 verifier 哲学と一致
- ChangeOp 単位の small-step transition は **Incremental Verification の `refinement relation` を定義しやすい構造** (B 論文の拡張余地)

**拡張可能な軸 (具体的)**:
1. **意味的不変量の追加**:
   - 現状は count ベース (n/a/r/w)。**Lipschitz 上界・robustness margin・Lyapunov stability** 等の量的不変量を Z3 + Real 算術で追加可能
   - 例: `InsertSubblock(activation=gelu)` 後の累積 Lipschitz 定数が閾値以下である ことを Z3 (Real arithmetic) で check
2. **Conflict inheritance (B の応用)**:
   - 親アーキの Z3 solver が学んだ unsat core を 子アーキ session に継承
   - 必要: ChangeOp の refinement relation 定義 (Insert は monotone refinement、Remove は inverse)
3. **TorchLean bridge (A の応用)**:
   - 構造 gate を通過した変異候補に対し、TorchLean の CROWN bound で robustness 不変量を別 layer で確認 (sampling)
4. **意味論完全性**:
   - 現在 SMT layer は state vector の影響のみ encode。`ReorderSubblocks` の **意味 (順序が attention masking 等に与える影響)** は trivially 保存扱い → 厳密化余地
5. **HITL ゲート連携**:
   - `VerificationResult.smt_model` (counterexample) を Approval Bus に流す経路は未配線 → 自然な拡張

---

## 独自軸チェックリスト (llive で論文化可能か)

| 軸 | 既存研究 | llive で先行できるか |
|---|---|---|
| Z3 を進化ループ内で **online 呼出し** architecture 変異を gate | **既存無し** (loop invariant 系は別)。L2RU/RACL は parametrization で保証、online SMT gate は希少 | **★★★ 強い独自軸** (既に実装あり、論文化が早ければ first paper) |
| **Lipschitz 制約付きの SSM state update 進化** | L2RU (2503.23818) が parametrization で L2-bound、但し **進化と未統合**。RACL は CNN 系で Lipschitz approx | **★★ 中独自** (L2RU を子モジュールに、進化選択 fitness に Lipschitz を組込めば差別化) |
| **Approval Bus 経由で HITL gate された architecture 進化** | PBG/EENA/GPT-NAS は population-based だが **HITL は無い**。Verified NAS の HITL も見当たらない | **★★★ 強い独自軸** (FullSense Approval Bus 哲学そのもの、llive の Independence Principle と整合) |
| **persona-indexed specialist 集団 with verifier** | Multi-population NAS は多数あるが、**persona-conditioned (Friston / 磯村 / furuse-調査者 等) × verifier gate** は未踏 | **★★★ 強い独自軸** (memory `project_persona_genome_integration` で実装着地済) |

---

## 推奨次ステップ

### A. llive verifier.py 拡張 (短期 1-2 週)

1. **Lipschitz quant 不変量を追加**: `Invariants` に `max_lipschitz: float | None` を導入、各 ChangeOp の Lipschitz 寄与を Z3 Real 算術で encode (L2RU の parametrization を参考にして閉形式の bound を持つ ops のみ厳密、その他は upper bound)
2. **Conflict cache の試験実装**: 連続変異列で前 query の unsat core を `pickle` 保持、次 query の前段で `solver.add(unsat_core)` 再投入 (Incremental 論文 B の最小実装)
3. **Approval Bus 連携**: `VerificationResult.ok == False` のときは `smt_model` (counterexample) を Approval Bus イベントに変換、HITL gate へ昇格

### B. TorchLean / Marabou 統合の選択

- **TorchLean**: **自前実装不可、bridge のみ**。Lean 4 環境の用意 + `leanx` repo の API stability を確認、進化 sampling 検証 (10 世代に 1 回) で robustness 不変量を別 layer で
- **Marabou**: **opt-in dependency 化**。Z3 と並列の SMT backend として、より広い semantic (activation phase) を扱える。CDCL conflict 学習 (Marabou 2.0) を直接利用可能 = B 論文の実装が落ちている
- **自前実装**: ChangeOp level の small-step transition 自体は llive 独自軸 → コアは自前維持、value-level verification のみ外部に委譲

### C. 実証実験の minimum spec

1. **対象**: llive `BlockSpec` × 1000 世代 × 4 persona (Friston / Millidge / 磯村 / furuse-調査者)
2. **比較条件 (A/B)**:
   - A: 現状 (structural + Z3 count 不変量のみ)
   - B: + Lipschitz quant 不変量
   - C: + Conflict inheritance
   - D: + Approval Bus HITL gate (5% sampling で人間判断)
3. **計測指標**:
   - 各世代の verifier latency (ms / generation)
   - reject rate (構造段 / SMT 段 / HITL 段 別)
   - 最終 fitness (proxy fitness、後段で実 LLM 比較 stub と相関)
   - **counterexample 品質**: Z3 が返す model が人間にとって意味があるか (Friston ペルソナ視点で predictive coding 違反を示せるか)
4. **比較対象**: random mutation (no verifier) / structural-only / RACL 風 Lipschitz objective (verifier ではなく fitness)
5. **論文ドラフト**: VNN-COMP 2026 workshop / SAIV co-located workshop に「Online SMT-Gated Architecture Evolution」として投稿候補 (VNN-COMP は 5 年連続 α,β-CROWN 優勝で固定領域、workshop は新規軸歓迎の素地あり)

---

## honest 留保

1. **VNN-COMP 2024 詳細 ranking spreadsheet を一次情報まで降りていない**: WebFetch では `sites.google.com/view/vnn2024` 本体・`arxiv.org/abs/2412.19985` 本文が full text 取得できず、α,β-CROWN README + レビュー記事 (themoonlight.io) 経由の確認に留まる。「優勝 = α,β-CROWN」「parameters 規模 = MNIST/CIFAR 中心」は α,β-CROWN README と一般知識から合致するが、上位 3 位以下の正確な score・最大ネットワーク parameter 数は **公式 GitHub repo `ChristopherBrix/vnncomp2024_results` を直接確認すること** を残作業とする
2. **「F. 進化中に invariant 検査が既存ゼロ」は探索の限界**: 私のキーワード組合せ (`"online verification" "neural architecture search"` 等) でヒットしないことを示しただけ。中国語圏・japanese 文献・workshop 論文 (CAV / SAIV / NSV / FoMLAS 等の非 main track)・industry preprint には未走査。**「該当無し」は強い主張だが**、Agent B (Verified NAS) と査読クロスチェック推奨
3. **Lean 4 × NN は 2026 時点で黎明期**: TorchLean / Nazrin / Hopfield 等の論文は **全て 2026 年 (2602.xxx / 2512.xxx)** に集中、エコシステムが流動的。llive で Lean 4 を採用すると **依存先が 1 年以内に大きく動く可能性**を honest disclosure として残す
4. **llive verifier.py の SMT 部の完全性**: 現状の state vector encoding は **type signature の保存** であって **計算 graph 等価性** ではない。例えば「`ReorderSubblocks` が attention mask の causality を破る」ような意味論的バグは現状 Z3 layer は捕まえられない (`_check_invariants_now` の name 重複 check が拾うのみ)。Lipschitz 拡張は **この限界の延長線上**にあり、根本治療ではなく漸増である点を honest に記す
5. **proxy fitness と実 LLM 比較**: 上記実証実験の minimum spec は proxy fitness を主軸にしているが、`feedback_llive_measurement_purity` の on-prem only 規律と `feedback_benchmark_honest_disclosure` (異常に良い結果が出たら内訳を疑う) を運用上守ること
