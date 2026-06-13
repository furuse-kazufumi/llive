# Verified Neural Architecture Evolution — Existing Work Survey

調査日: 2026-05-28
スコープ: Z3 / SMT / formal methods × NN architecture 進化探索の交差点で、
llive (`src/llive/evolution/verifier.py` + `src/llive/approval/` + `src/llive/perf/evolutionary/lldarwin_v2.py`) の主張
「**破綻させずに architecture を進化させる基盤**」と一次情報をぶつける。

---

## A. Formal verification × NN（学習後 NN の robustness 検証側）

代表系列（一次出典 URL 付き）:

1. **Reluplex** (Katz, Barrett, Dill, Julian, Kochenderfer, CAV 2017)
   <https://arxiv.org/abs/1702.01135>
   ReLU 入りの DNN を SMT (simplex 拡張) で検証する最初の本格枠組み。ACAS Xu (45 機の衝突回避 DNN、8 層 / 300 ReLU) で robustness の安全性質を検証。
   **できること**: 固定された NN の入力境界に対する出力性質の sat/unsat 判定。
   **できないこと**: 学習中/進化中の構造変化、layer 追加/削除のような「アーキ変異の合法性」検証は対象外。

2. **Marabou** (Katz et al., CAV 2019, Hebrew U + Stanford)
   <https://arxiv.org/abs/1903.06758> / <https://theory.stanford.edu/~barrett/pubs/KHI+19.pdf> / repo <https://github.com/NeuralNetworkVerification/Marabou>
   Reluplex の後継。複数活性化関数、複数入力形式 (TF protobuf)、並列実行に対応。Proof Production 拡張版あり (<https://arxiv.org/abs/2206.00512>)。
   **同じく**「学習後 NN の入出力性質」が対象であり、構造編集 (insert / remove / replace subblock) は守備範囲外。

3. **α,β-CROWN** (Verified-Intelligence, UIUC ほか)
   repo <https://github.com/Verified-Intelligence/alpha-beta-CROWN> / 2024 BICCOS 拡張 <https://arxiv.org/abs/2501.00200>
   VNN-COMP 2021/2022/2023/2024/2025 連続優勝。Branch-and-bound + 線形 bound propagation + GPU 加速。Lyapunov 安定性の検証もカバー（制御系向け）。
   **対象**: robustness、Lyapunov stability、reachability。**構造進化はスコープ外**。

4. **ERAN / DeepPoly** (Singh, Gehr, Püschel, Vechev, POPL 2019, ETH Zurich)
   論文 <https://files.sri.inf.ethz.ch/website/papers/DeepPoly.pdf> / repo <https://github.com/eth-sri/eran>
   Abstract interpretation (polyhedra ∩ intervals) で robustness を sound に証明。SMT ではなく抽象解釈系だが、同じ「学習後 NN を検証する」目的。

5. **NeuralSAT** (2024 系列の DPLL(T) ベースの NN 検証器)
   <https://link.springer.com/chapter/10.1007/978-3-031-98679-6_19>
   SMT + DPLL(T) で α,β-CROWN と競合。

6. **VNN-COMP** (年次競技、2020–2025)
   公式 <https://sites.google.com/view/vnn2024> ほか。ベンチマークは ACAS Xu / MNIST / CIFAR / ResNet / GPT-style まで拡張中だが、**全ベンチマークが「固定アーキの NN を検証する」設定**で、進化中アーキは含まれない。

**A の総括**: 既存研究は **学習後/デプロイ後 NN の入出力性質 (robustness / reachability / Lyapunov)** を sound に検証する流れ。**アーキ構造そのものを書き換える進化操作の合法性 (essential subblock の喪失、memory_read/write ペア破綻、container 空化) を ChangeOp 列で SMT 検証する work は見つからなかった**。llive の verifier はこの隙間に位置する。

---

## B. 進化 × 形式手法 の交差

直接 hit する系列は **CDGP (Counterexample-Driven Genetic Programming)** のみ:

- **CDGP** (Krawiec et al., IJCAI 2018 / Evolutionary Computation 2018)
  <https://direct.mit.edu/evco/article/26/3/441/1070> / <https://www.ijcai.org/proceedings/2018/0742.pdf>
  GP で生成した候補プログラムを SMT で formal verification し、反例をテストケースに変換して fitness を更新。LIA / SLIA で「証明可能に正しい」プログラム合成。
  **llive との重要な差**:
  - CDGP は **記号プログラム合成** (linear integer arithmetic / 文字列操作) であり、**NN architecture ではない**
  - 「反例 → fitness フィードバック」が主であり、llive のような「**変異適用前の事前 gate**」設計とは方向が逆
  - container 構造や essential subblock のような **NN-architecture-specific invariants** は扱わない

その他関連:
- **Synthesis through Unification GP** (Welsch, program synthesis + GP) <https://kurlin.org/projects/program-synthesis/Synthesis-through-Unification-Genetic-Programming.pdf>
- **GP + model checking** (Katz, Peled 2014 系) <https://arxiv.org/abs/1402.6785>
- **Verified RL / Safety shields** (Alshiekh, Bloem ほか) CACM 2025 <https://cacm.acm.org/research/shields-for-safe-reinforcement-learning/> / <https://arxiv.org/abs/2406.06507>
  shield は **policy の行動を runtime で gate** する。**architecture の変異** ではない。
- **Neuro-Symbolic Constrained Optimization** (2025) <https://arxiv.org/abs/2511.23109>
  GNN 予測を Z3 SMT の soft constraint に流す。cloud deployment 最適化が対象で NN 進化ではない。

**B の総括**: **「NN architecture 変異列を SMT で事前 gate する」という形のレシピは見当たらない。** GP × SMT (CDGP) は記号プログラム合成、Safe RL × shield は policy runtime gating、neuro-symbolic NAS は constraint としての SMT 使い方であり、いずれも llive の **ChangeOp 列 → Z3 → architecture 変異 commit** という pipeline 構造と直接的に被らない。

---

## C. Architecture-level invariants

llive verifier は subblock count / essential type / memory pair の invariants が主だが、関連する「数値・力学系レベルの不変量」研究は厚い:

1. **Lipschitz constraints** (Trockman & Kolter, ICLR 2021)
   <https://arxiv.org/abs/2104.07167> (Cayley transform で convolutional layer を直交化、provably 1-Lipschitz CNN を構築)
   後続: Béthune et al. JMLR 2022 <https://www.jmlr.org/papers/v23/22-0026.html>、LipKernel 2024 <https://arxiv.org/abs/2410.22258>。
2. **Spectral normalization** (Miyato et al., ICLR 2018) — GAN/識別器の Lipschitz 制御、formal verifier との接続例多数。
3. **SSM / Mamba の Hurwitz 安定性**:
   - **Sparse Mamba** (Ali et al. 2024) <https://arxiv.org/abs/2409.00563> — Mamba2 の A 行列が常に安定とは限らない問題に対し controllability / observability / stability を構造に組込み。
   - **Mamba State-Space Models Are Lyapunov-Stable Learners** <https://arxiv.org/abs/2406.00209> — Mamba の recurrent dynamics の安定性を解析。
4. **Liquid Time-constant Networks (LTC)** (Hasani, Lechner, Amini, Rus, Grosu, AAAI 2021)
   <https://arxiv.org/abs/2006.04439> — Theorem 2 で hidden state が有限区間で bounded であることを証明。Neural ODE の stability theory。

**C の総括**: 「**個別 architecture の数値安定性を保証する**」work は非常に厚い (Lipschitz / spectral / Lyapunov / Hurwitz)。しかしこれらは **学習レシピや構造制約として焼き付ける**形であり、**「変異列を sat/unsat で進化ループ内で gate する」形での組込みは見つかっていない**。llive は将来この C 群の invariants を Z3 制約として組込み拡張する余地を持つ。

---

## D. AutoML-Zero とフォローアップ（small-compute 系）

- **AutoML-Zero** (Real, Liang, So, Le, ICML 2020) <https://arxiv.org/abs/2003.03384> / blog <https://research.google/blog/automl-zero-evolving-code-that-learns/>
  基本演算 op の組合せから ML アルゴリズムを進化で発見。
- フォローアップ:
  - **AutoRobotics-Zero** (Kumar et al., IROS 2023 Best Overall Paper Finalist) <https://arxiv.org/abs/2307.16890> — adaptable symbolic policy を AutoML-Zero 流で進化、ロボット制御へ。
  - **AutoNumerics-Zero** (2023) <https://arxiv.org/abs/2312.08472> — 関数近似を進化。
  - **TensorNEAT** (2025) <https://arxiv.org/abs/2504.08339> — NEAT の GPU 並列化 (500x speedup)、個人/small-compute 研究の補強。
  - **Limited Evaluation Evolutionary Optimization of Large NNs** <https://arxiv.org/abs/1806.09819> — eval 数を抑えて大規模 NN を進化。
- **個人 / 限定計算で意味ある結果を出した例**: AutoML-Zero 本体は TPU クラスタ前提。AutoRobotics-Zero は IROS で finalist 取れたが Google Research 共著。TensorNEAT 系は「個人 GPU で数百万 generations 回す」現実解。

**D の総括**: AutoML-Zero 流は **無制約進化** が骨子。llive のように **invariants + Z3 gate + HITL Approval Bus** を入れた small-compute 派生は無さそう。「数百〜数千 generations を CPU/個人 GPU で回し、Z3 gate と人間 review の二段で破綻を抑える」設計は独自に立つ可能性が高い。

---

## E. 持続的進化系 NN 研究

1. **Population-Based Training (PBT)** (Jaderberg et al., DeepMind 2017)
   <https://arxiv.org/abs/1711.09846> / blog <https://deepmind.google/blog/population-based-training-of-neural-networks/>
   ハイパラ + 重み joint 最適化。population がランタイムで mutate / exploit。**architecture 変異は対象外** (ハイパラ層)。
2. **Sakana AI: Evolutionary Model Merge** (Akiba et al., Nature Machine Intelligence 2024/2025)
   <https://www.nature.com/articles/s42256-024-00975-8> / blog <https://sakana.ai/evolutionary-model-merge/>
   事前学習済 LLM の merge レシピを進化最適化。**既存モデルの重み混合**が主で、architecture 構造の SMT gate は無い。
3. **Sakana AI: AB-MCTS / collective intelligence** <https://sakana.ai/ab-mcts/> — inference-time scaling 系、本サーベイのスコープ外。
4. **AlphaEvolve** (Google DeepMind, May 2025)
   blog <https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/> / paper <https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/AlphaEvolve.pdf> / results repo <https://github.com/google-deepmind/alphaevolve_results>
   Gemini Flash/Pro + 自動 evaluator + 進化ループで algorithm discovery (高速行列積、Erdős 問題、量子回路最適化)。
   **重要**: evaluator が「**通った/通らなかった**」の binary scoring であり、**llive のような「変異の合法性を SMT で事前判定」する形ではない**。AlphaEvolve は scorer で事後 reject、llive は verifier で事前 gate という違い。
5. **LLMatic** (Nasir et al., GECCO 2024) <https://dl.acm.org/doi/10.1145/3638529.3654017>
   LLM × Quality-Diversity × NAS。MAP-Elites 系で多様性を維持。**Z3 / SMT gate は無し**。
6. **Continual / Lifelong NAS**:
   - HERCULES <https://arxiv.org/abs/2605.04103> — 長時間運用で memory device drift 込みで NAS。
   - CL × NAS review <https://arxiv.org/abs/2206.05625>
   いずれも **plasticity / forgetting** が焦点で、formal gate は無い。

**E の総括**: 持続進化系の最前線 (PBT / Sakana Evo Merge / AlphaEvolve / LLMatic) は **evaluator-based scoring** で進化を駆動。**「変異を formal に reject する事前 gate」というアーキ層の invariant 保護は誰もやっていない** (honest 留保: 全 GECCO/EvoStar 論文を網羅したわけではない)。

---

## llive 主張の独自性チェックリスト

- [x] **Z3 verifier で破綻変異を gate する architecture evolution** = **既存に該当なし** (B 節で確認)。CDGP は記号プログラム合成、NN robustness verifier は学習後対象、AlphaEvolve は事後 evaluator。**事前 gate × architecture 変異列 × Z3** の組合せは独自と言える。
- [x] **Approval Bus で人間 HITL 経由でしか promotion されない architecture evolution** = **既存に該当なし**。HITL approval gate の概念は agentic AI 一般にあるが (Best AI Web / MachineLearningMastery 系)、**NAS / 進化 architecture への適用は確認できず**。Safe RL の shield は policy 行動の HITL であってアーキ変異の HITL ではない。
- [x] **persona-indexed specialist 集団による異種アーキ生態系** = **既存に該当なし (角度違い)**。Island Model / Quality Diversity / LLMatic は「多様性維持」が主目的で、**persona (Friston / Millidge / 磯村 / furuse 調査者など) を anchor として specialist 個体群を運用する例は見つからず**。multi-agent persona は GABM (Persona Generators) 系にあるが、**進化ゲノムへの埋込みではない**。
- [x] **factor_hook で認知状態が SSM Δ を駆動** = **既存に該当なし**。Mamba の Δ パラメータは「入力依存」(input-selective) が現行設計。**外部の cognitive state / thought factor が Δ を modulate する work は見つからず**。Sparse Mamba は構造的安定化、Lyapunov-stable Mamba は事後解析であり、認知状態駆動の設計は無い。

---

## 差別化 verdict（honest, 4 段階）

### 完全独自
- **ChangeOp 列 → Z3 事前 gate → commit** という pipeline は、現在の公開研究では確認できなかった。NN robustness 検証 (Reluplex / Marabou / α,β-CROWN / ERAN) は学習後対象、CDGP は記号プログラム合成、AlphaEvolve / LLMatic は事後 scorer 駆動。
- **factor_hook (認知状態 → SSM Δ 駆動)** は Mamba の input-selective Δ 設計を超える独自方向。
- **persona-indexed 進化 specialist 集団 (Friston / Millidge / 磯村 / furuse 等の研究者ペルソナを anchor)** は新規。

### 既存と並ぶが角度違い
- **Approval Bus HITL**: HITL approval gate 自体は agentic AI 一般概念。**「architecture 変異 promotion の HITL 化」** という焦点で組み合わせれば差別化可能だが、概念単独では新規性は中程度。
- **持続的進化** (Continual NAS / PBT / Sakana / AlphaEvolve) — llive の lldarwin_v2 が「formal gate + HITL + persona」で **質的に異なる持続進化** であることを実証データで示す必要あり。

### 既存に近い（要差別化再設計）
- **invariants の中身そのもの** (Lipschitz / spectral / Hurwitz) は厚い既存があるので、「llive verifier が独自に発明した」とは主張できない。**「既存の数値安定性 invariants を進化ループ内 SMT gate に embedding した最初の枠組み」** の角度で立てる必要あり。
- **Quality Diversity / island model** の発想は既存。llive の persona 化を「QD の anchor を人物 (研究者) に取った特殊形」として位置付けると先行研究との対話が成立する。

### 既存に negation される（撤退候補）
- 現時点で「llive のコア主張を真っ向から潰す」既存は確認できず。

---

## 投稿先候補（差別化が立つ前提で）

1. **TMLR** (Transactions on Machine Learning Research, peer review, no hard deadline)
   <https://jmlr.org/tmlr/> — 「verified evolutionary NN architecture」の境界研究として最有力。Methodology + 実証を縦に積める。
2. **GECCO** (Genetic and Evolutionary Computation Conference, ACM SIGEVO)
   毎年 7 月、abstract 1 月。LLMatic / island model 系の文脈で査読しやすい。
3. **EvoStar / EvoApplications** (毎年 4 月) — formal methods × EC のニッチ向け、layer 1 採択。
4. **AAAI** (formal methods × ML トラック) — Reluplex / Marabou 系の延長として置けるが、competition 激しい。
5. **NeurIPS / ICLR workshop**:
   - **Workshop on ML for Systems**
   - **Workshop on Safe & Trustworthy ML**
   - **Workshop on Verification of Neural Networks** (VNN-COMP 連動)
6. **CAV / FMCAD** workshop — formal methods コミュニティへの直接持込み (難易度高)。

**推奨**: **TMLR を本命**にしつつ、**GECCO の short paper / workshop** で先に visibility を取り、フィードバック反映で TMLR full submission に持っていく二段。

---

## honest 留保

- VNN-COMP 2025 の全エントリ、GECCO 2024–2025 の全 NAS 論文は網羅できていない。「llive 主張と完全に同じ work」が査読中で公開されている可能性は残る。
- Sakana AI / DeepMind / OpenAI 等の **未公開社内研究** に同種設計が存在する可能性は原理的に排除不能。
- CDGP の最新拡張 (2023–2025) と llive の差別化が十分か、CDGP 系コミュニティへの直接照合がまだ。
- factor_hook (認知状態 → SSM Δ) は神経科学/active inference 系 (Friston ほか) で類似議論があるはずで、ML 側の検索だけでは不十分。`rad-research` の `cognitive_science` / `neuroscience` を別 session で当てるべき。
- 「formal verifier を進化ループに online で組込む」概念は、runtime verification / evolution-aware RV (Illinois Experts <https://experts.illinois.edu/en/publications/techniques-for-evolution-aware-runtime-verification/>) と部分的に重なる可能性あり、より深い読込み必要。
- Lipschitz / Hurwitz invariants を llive の Z3 制約に格上げする実装は未着手。論文化時には「現状は subblock-level invariants のみ、数値安定性 invariants は次フェーズ」と honest に書く。

---

## 結論

llive の核心 (**事前 SMT gate × architecture 変異 × Approval Bus HITL × persona-indexed 進化 × factor-driven Δ**) は、公開されている主要 5 領域 (A–E) を一次出典まで遡って照合した結果、**完全独自の組合せ**として立つ。撤退の必要はない。差別化を **強める**ためには:

1. 「既存の数値安定性 invariants (C 節) を Z3 制約として組込んだ最初の枠組み」へ verifier を拡張
2. AlphaEvolve / LLMatic と直接比較する evaluation (同じ benchmark で「破綻率」「HITL approval rate」「formal gate reject 率」)
3. persona-indexed specialist の効用を、Quality-Diversity ベースラインに対する優位性として実証

を 1 個ずつ積み上げる。投稿は TMLR 本命、GECCO で先行 visibility。
