# Pre-Survey for Verified Architecture Evolution on CPU

調査日: 2026-05-28
目的: 「Transformer コアアルゴリズムに進化形態を与える」研究方向の事前 overlap / gap 整理。
規律: 一次情報 URL 必須。曖昧な引用は「要追跡」と明示。CPU 実機検証できない論点は honest 留保へ。

---

## A. 非 Transformer 系 sequence model

### A-1. Mamba / Mamba-2 (Gu & Dao 2023-2024)
- 一次出典: arXiv:[2312.00752](https://arxiv.org/abs/2312.00752) (Mamba, 2023-12), 公式実装 [state-spaces/mamba](https://github.com/state-spaces/mamba)
- 主張: 入力依存の selective SSM。Δ で「忘却 / 記憶」を token ごとに変える。Mamba-3B が同サイズ Transformer を上回り 2x サイズと拮抗 (paper Abstract)。
- CPU 可否: llama.cpp に [PR #5328](https://github.com/ggml-org/llama.cpp/pull/5328) (Mamba), [PR #9126](https://github.com/ggml-org/llama.cpp/pull/9126) (Mamba-2) で CPU 推論実装あり。Mamba-2.8B GGUF 配布 ([dranger003/mamba-2.8b-hf-GGUF](https://huggingface.co/dranger003/mamba-2.8b-hf-GGUF))。初期 PR コメントで CPU-only 動作確認、empty context では Transformer より遅いが token 増加で degrade しない。
- ライセンス: Apache-2.0 (mamba repo `LICENSE`、上記 GitHub で要再確認 — 要追跡: 自分はファイルを開いていない)。

### A-2. RWKV-7 "Goose" (Peng et al. 2025-03)
- 一次出典: arXiv:[2503.14456](https://arxiv.org/abs/2503.14456), [BlinkDL/RWKV-LM](https://github.com/BlinkDL/RWKV-LM)
- 主張: 一般化 delta rule + vector-valued gating + in-context learning rates。constant memory / constant time per token。2.9B で多言語 3B SoTA、英語は 3B SoTA tie。
- CPU 可否: 行列-ベクトル積のみ (matrix-matrix 不要)、Apache-2.0 で GGUF 配布 ([BlinkDL/rwkv-7-world](https://huggingface.co/BlinkDL/rwkv-7-world), [Mungert/rwkv7-2.9B-world-GGUF](https://huggingface.co/Mungert/rwkv7-2.9B-world-GGUF))。スマホでも動くと paper / HF カード。
- ライセンス: Apache-2.0 (paper Abstract で明記、HF card で確認)。

### A-3. RetNet (Sun et al. 2023, MSRA)
- 一次出典: arXiv:[2307.08621](https://arxiv.org/abs/2307.08621), [Microsoft Research publication page](https://www.microsoft.com/en-us/research/publication/retentive-network-a-successor-to-transformer-for-large-language-models/)
- 主張: retention 機構が「parallel / recurrent / chunkwise recurrent」3 形態を許す。O(1) inference。
- CPU 可否: 公式実装 ([Jamie-Stirling/RetNet](https://github.com/Jamie-Stirling/RetNet)) は非公式リポ。MS 公式の release は要追跡。CPU 単体推論ベンチマークは一次資料で未確認。
- ライセンス: 公式コード release が確認できておらず「要追跡」。

### A-4. Hyena Hierarchy (Poli et al. 2023, Stanford Hazy Research)
- 一次出典: arXiv:[2302.10866](https://arxiv.org/abs/2302.10866), 解説 [hazyresearch.stanford.edu/blog/2023-03-07-hyena](https://hazyresearch.stanford.edu/blog/2023-03-07-hyena), 実装 [HazyResearch/safari](https://github.com/HazyResearch/safari)
- 主張: long convolution + gating で sub-quadratic に attention 品質を再現。ICML 2023。
- CPU 可否: FFT-based long conv は CPU でも回るが GGUF / llama.cpp 系の実装は確認できず「要追跡」。
- ライセンス: safari repo は Apache-2.0 (HF/GitHub の表示、未直接確認)。

### A-5. Liquid NN / LTC / CfC (Hasani et al. 2022, MIT CSAIL)
- 一次出典: arXiv:[2106.13898](https://arxiv.org/abs/2106.13898) (CfC), Nature MI [10.1038/s42256-022-00556-7](https://www.nature.com/articles/s42256-022-00556-7), 実装 [raminmh/CfC](https://github.com/raminmh/CfC)
- 主張: 連続時間 ODE 系の closed-form 近似。LTC の ODE-solver を不要にし training/inference 1-5 桁高速化。
- CPU 可否: pure PyTorch 実装で CPU で確実に回るサイズ感 (制御/時系列タスク中心、LLM スケールではない)。
- ライセンス: raminmh/CfC は要再確認 (未直接確認、「要追跡」)。

### A-6. Modern Hopfield Networks (Ramsauer 2020 / Krotov-Hopfield 2021)
- 一次出典: arXiv:[2008.02217](https://arxiv.org/abs/2008.02217) "Hopfield Networks is All You Need"; Krotov & Hopfield 2021 [ICLR](https://research.ibm.com/publications/large-associative-memory-problem-in-neurobiology-and-machine-learning) "Large Associative Memory Problem in Neurobiology and ML"
- 主張: 連続状態 Hopfield = Transformer attention 等価。指数容量 dense associative memory。Hopfield/Hinton は 2024 Nobel Physics。
- CPU 可否: 単層 retrieval は MLP 2 層相当で CPU で容易。
- ライセンス: 関連実装は repo ごと、未直接確認。

---

## B. アーキテクチャ探索 / 進化

### B-1. AutoML-Zero (Real et al. 2020, Google Brain, ICML)
- 一次出典: arXiv:[2003.03384](https://arxiv.org/abs/2003.03384), [google-research/automl_zero](https://github.com/google-research/google-research/tree/master/automl_zero)
- 主張: 基本数学演算のみから ML アルゴリズムを進化発見。2 層 NN + backprop を「再発見」、CIFAR-10 で現代手法的構造に発展。
- CPU 可否: 公式は C++ + 多コア。CPU で動作するが学習則レベルの search は cluster 規模。
- ライセンス: Apache-2.0 (google-research 標準、未直接確認)。

### B-2. DARTS (Liu et al. 2018, CMU/DeepMind)
- 一次出典: arXiv:[1806.09055](https://arxiv.org/abs/1806.09055), [quark0/darts](https://github.com/quark0/darts)
- 主張: 離散構造を continuous relaxation し勾配で NAS。RL/進化系より数桁高速。

### B-3. ENAS (Pham et al. 2018, Google Brain, ICML)
- 一次出典: arXiv:[1802.03268](https://arxiv.org/abs/1802.03268), [melodyguan/enas](https://github.com/melodyguan/enas)
- 主張: parameter sharing で subgraph 探索を 1000x 高速化。PTB perplexity 55.8。

### B-4. AmoebaNet / Regularized Evolution (Real et al. 2018, Google Brain, AAAI)
- 一次出典: arXiv:[1802.01548](https://arxiv.org/abs/1802.01548)
- 主張: age 属性付き tournament selection。ImageNet 83.1% top-1。NAS 進化系の代表。

### B-5. AlphaEvolve (Novikov et al. 2025, DeepMind)
- 一次出典: arXiv:[2506.13131](https://arxiv.org/abs/2506.13131), [DeepMind blog](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/), [DeepMind PDF](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/AlphaEvolve.pdf), [alphaevolve_results](https://github.com/google-deepmind/alphaevolve_results)
- 主張: Gemini-powered LLM × evolutionary loop。コード変異 + evaluator feedback。Strassen 56 年ぶりに更新 (4×4 complex 48-mul)。50 問の数学問題で 75% が SoTA 復元 + 一部更新。Borg で 0.7% 計算節約。
- CPU 可否: LLM は外部 API。loop 自体は CPU で回るがコスト = LLM 利用料。
- ライセンス: 結果リポは MIT 系の可能性。コード本体は非公開 (要追跡)。

### B-6. Sakana AI Evolutionary Model Merge (Akiba et al. 2024)
- 一次出典: arXiv:[2403.13187](https://arxiv.org/abs/2403.13187), Nature MI [10.1038/s42256-024-00975-8](https://www.nature.com/articles/s42256-024-00975-8), [Sakana blog](https://sakana.ai/evolutionary-model-merge/)
- 主張: 既存 LLM の merge レシピを CMA-ES 系で探索。追加学習なし。日本語 LLM で SoTA。mergekit / Optuna Hub に取り込まれた。
- CPU 可否: merge 自体は CPU でも可能 (重み演算)。evaluation は LLM forward が必要。
- ライセンス: mergekit は LGPL-3.0 (リポ参照、未直接確認 → 要追跡)。

---

## C. 代替学習則

### C-1. Forward-Forward (Hinton 2022, NeurIPS keynote)
- 一次出典: arXiv:[2212.13345](https://arxiv.org/abs/2212.13345)
- 主張: 2 つの forward pass (positive / negative) + 各層 local goodness で backprop 置換。低消費電力 analog HW を想定。
- CPU 可否: MNIST / CIFAR スケールで CPU 完結。Hinton 本人の reference 実装は小規模。
- ライセンス: 公式 reference 実装の所在は要追跡 (paper には PyTorch コード snippet)。

### C-2. Equilibrium Propagation (Scellier & Bengio 2017)
- 一次出典: arXiv:[1602.05179](https://arxiv.org/abs/1602.05179), [Frontiers Comp Neurosci 2017](https://www.frontiersin.org/journals/computational-neuroscience/articles/10.3389/fncom.2017.00024/full)
- 主張: energy-based model で 2 相 (free / nudged) の局所差分から weight 更新。STDP に近い局所性。BPTT 近似であることが理論的に示されている。
- 拡張: arXiv:[2508.15989](https://arxiv.org/html/2508.15989v1) (Scalable EP via intermediate error signals, deep ConvCRNN, 2025) — 深層化方向の継続研究。
- CPU 可否: 小〜中規模 ConvNet で実装例あり。

### C-3. Predictive Coding (Millidge, Tschantz, Buckley, 2020-2023)
- 一次出典: arXiv:[2006.04182](https://arxiv.org/pdf/2006.04182) "Predictive Coding Approximates Backprop along Arbitrary Computation Graphs", arXiv:[2202.09467](https://arxiv.org/pdf/2202.09467) "Predictive Coding: Towards a Future of Deep Learning beyond Backpropagation?" (IJCAI 2022), arXiv:[2304.02658](https://arxiv.org/pdf/2304.02658) (Neural Computation 2023 critical eval)
- 主張: hierarchical generative model + local error。Friston 系自由エネルギー原理と接続。任意計算グラフで backprop 近似可。
- CPU 可否: PCN は局所更新で並列化容易、CPU で MLP/ConvNet スケール実装あり。

### C-4. Hebbian / STDP local rules (2023)
- 一次出典: arXiv:[2307.04054](https://arxiv.org/abs/2307.04054) "Deep Unsupervised Learning Using STDP", arXiv:[2306.15220](https://arxiv.org/abs/2306.15220) "S-TLLR: STDP-inspired Temporal Local Learning Rule"
- 主張: SNN の純粋 STDP は深層スケールが難しいが、rate-based + pseudo-label の組合せや 3-factor local rule で深層化可。time step 数に依存しない memory/time 複雑度。
- CPU 可否: SNN シミュレータ (Brian2 / Norse / SpikingJelly) で CPU 動作。LLM スケールはまだ研究段階。

---

## D. 検証付き NN 探索 (existing work と gap)

### D-1. SMT/SAT による NN 検証 (frame)
- Marabou (Katz et al. 2019, Stanford): SMT-based DNN verifier。reachability/robustness query を Simplex+SMT で解く。[Marabou repo](https://github.com/NeuralNetworkVerification/Marabou), [paper PDF](https://theory.stanford.edu/~barrett/pubs/KHI+19.pdf)
- α,β-CROWN (Wang/Zhang et al.): VNN-COMP 2021-2025 連覇。GenBaB (Shi et al. 2024) で Transformer/LSTM 等非 ReLU を含む branch-and-bound 検証可。BICCOS (Zhou et al., NeurIPS 2024) で cutting plane 自動生成。[alpha-beta-CROWN repo](https://github.com/Verified-Intelligence/alpha-beta-CROWN)
- Binarized NN SMT verification: arXiv:[2011.02948](https://arxiv.org/pdf/2011.02948) (Marabou 拡張)。

### D-2. 検証 × NAS の交差
- DSRNA (Hosseini et al. 2020): arXiv:[2012.06122](https://arxiv.org/pdf/2012.06122) — certified robustness lower bound + Jacobian norm を differentiable metric にして robust 構造を NAS。
- "Towards Accurate and Robust Architectures via NAS" (Huang et al. 2024): arXiv:[2405.05502](https://arxiv.org/pdf/2405.05502) — 多目的 search で自然/敵対損失同時最適化。
- VeriFlow (2024): arXiv:[2406.14265](https://arxiv.org/abs/2406.14265) — flow-based density model で検証 search を関心分布に限定。
- **Gap**: 「進化探索した構造を 1 件ずつ SMT/CROWN で検証 → 通った gene のみ次世代」の **proxy fitness 統合** は明示的にはまだ見つからず (要追跡)。DSRNA は differentiable bound、α,β-CROWN は post-hoc 検証で、両者を NAS の **selection pressure** に組み込んだ先行例は今回 確認できなかった。

---

## E. CPU 実機での非 Transformer 訓練の現実性

### E-1. 推論
- RWKV-7: GGUF + llama.cpp 系で 0.19B / 0.4B / 1.5B / 2.9B が CPU 単体可。Q4_K で 8GB RAM 級 PC でも 2.9B 動作報告。
- Mamba/Mamba-2: llama.cpp 取り込み済 (PR #5328, #9126)。Mamba-2.8B / Codestral-7B 量子化版あり。
- RetNet / Hyena: 公式 CPU 配布は確認できず (要追跡)。

### E-2. 訓練
- RWKV-7 paper は「training に GPU 必須」とは明言していないが、scratch 学習は GPU 前提。BlinkDL は単 GPU でも段階的に学習できる工夫を公開。
- Mamba scratch training は GPU H100/A100 級が前提 (paper)。
- PyTorch on Windows CPU の体感: Intel Xeon 系で **inference** quantization (A16W8 / DA8W8) は PyTorch 2.8 で native 最適化 ([PyTorch blog](https://pytorch.org/blog/high-performance-quantized-llm-inference-on-intel-cpus-with-native-pytorch/))。training 側の Windows CPU ベンチは一次資料で確認できず「要追跡」。
- 実務感: **100M 級 RWKV/Mamba を CPU で scratch 学習 = 可能だが days オーダー**。**1B 級は不現実**。fine-tune (LoRA/QLoRA) や **構造遺伝子の小規模 proxy task** であれば CPU で hours オーダー。

### E-3. 推奨スタック (CPU 出発)
1. RWKV-7 0.19B / 0.4B 公式重みを load → llive の persona-indexed loop で in-context 適応
2. PyTorch + bitsandbytes/torchao 量子化 + Intel oneDNN (Windows でも有効)
3. NAS の **proxy task** は char-level (PTB / Tiny Stories / enwik8 早期 chunk) で 1 世代 数分
4. 検証は Marabou or α,β-CROWN の small subgraph 単位 (full model でなく cell / block 検証)

---

## 差別化マトリクス (llive 独自軸 vs 先行研究)

| llive の主張 | 該当 先行研究 | overlap / gap |
|---|---|---|
| **Z3 verifier を fitness gate に組込み**「検証通過 = 生存条件」 | DSRNA (差分 bound), α,β-CROWN (post-hoc), Marabou (SMT) | overlap: 検証技術は既存。**gap: 検証を進化の selection pressure として明示的に積んだ例は今回未発見**。要追跡。 |
| **Approval Bus** で人間が世代ごとに承認 (HITL evolution) | AlphaEvolve (LLM × evaluator loop) | overlap: evaluator-in-the-loop は同型。gap: AlphaEvolve は automatic evaluator、llive は **人間の approval signal を fitness の 1 dim** にする点が独自。FullSense 哲学 #5 (Honest disclosure) + 規約 (Approval Bus 迂回禁止) と整合。 |
| **persona-indexed specialist 集団** (furuse 調査者 / Friston / Millidge / 磯村 等) を遺伝子に焼き付け | Sakana evolutionary merge (model merge), AutoML-Zero (algorithm scratch), AmoebaNet (architecture) | overlap: 集団進化 + 多様性は同型。gap: **persona = prompt + memory shard + 評価軸** の三位一体で遺伝子化、かつ既に [[project_persona_genome_integration]] で 1000 世代の turnkey driver 着地済の点が独自。 |
| **CPU で踏み込める範囲** (個人 PC + RWKV-7/Mamba 重み) | RWKV-7, Mamba (CPU 推論可)、AlphaEvolve (cloud LLM 前提) | overlap: 個別の CPU 推論は確立。gap: 「**CPU で進化ループを完結**」「on-prem only ([[feedback_llive_measurement_purity]])」を貫いた competitive coevolution は未発見。 |
| **学習則自体を進化対象に** (FF / EP / PCN / Hebb を gene として混在進化) | AutoML-Zero (algorithm 進化), Forward-Forward, Equilibrium Propagation, Predictive Coding | overlap: 各学習則は単独で活発。gap: **複数学習則を 1 個体内に混在させ進化的に淘汰** する明示的先行は今回未発見 (要追跡)。 |
| **コア計算 (attention / 状態保持) を非可換に進化** | Mamba (selective SSM), RWKV-7 (generalized delta rule + vector gating), RetNet (retention 3 形態), Hopfield-attention 等価 | overlap: 個別の「Transformer 代替コア」は揃っている。gap: **これら自身を進化遺伝子の探索空間としてカタログ化** し、世代ごとに operator を swap する設計は未発見。 |

---

## honest 留保

### 一次情報で裏取り未了 (要追跡)
- Mamba / safari / mergekit 等のライセンスは「Apache-2.0 と思われる」レベルで `LICENSE` ファイル直接確認はしていない。
- RetNet の公式 release コード所在と CPU 推論可否。
- Forward-Forward の Hinton 公式 reference 実装の所在。
- AlphaEvolve のオープンコード公開状況 (results リポはあるが本体非公開と推定、未直接確認)。
- 「検証 × NAS を selection pressure として積んだ先行研究」を見つけきれていない (用語空間が "robust NAS" / "certified NAS" / "verified-architecture-search" 等で散らばっており網羅性に不安)。

### CPU で実機検証できない論点
- 100M-1B 級 scratch 学習の Windows CPU 実時間 (Intel oneDNN + PyTorch 2.8 で実測比較する一次資料が今回見つからず、推定 days-weeks)。
- α,β-CROWN を **per-generation** に回したときの 1 世代あたりコスト (paper benchmarks は単発検証の wall-clock のみ)。
- RWKV-7 / Mamba の **構造を変えた gene** が CPU 推論 stack に乗るか (llama.cpp は固定 op セット前提)。

### まだ十分網羅できていない領域
- GECCO/EvoStar 2023-2025 の NAS 進化系 論文 (個別 paper まで掘れず)。
- Liquid NN を **LLM 領域** に押し上げた先行 (Hasani の最近の Liquid Foundation Model 系は LFM-1/3/40B として 2024 出ているが本サーベイ未照合)。
- 中国系研究 (Qwen / 智源 / 上海AI Lab) の SSM/RWKV 派生。

---

## CPU 実験パスの提案

1. **RWKV-7 0.4B 重みを base に in-context 進化ループ** (Apache-2.0、GGUF 配布)
   → llive の persona genome を prompt + state 初期値で表現、CPU で 1000 世代を hours。
2. **Mamba-130M を gene template にした Δ パラメータ進化**
   → selective SSM の Δ 写像を persona ごとに差し替え、proxy task は enwik8 char-level perplexity。
3. **学習則 gene を FF / EP / PCN / backprop の 4 値カテゴリで混在進化**
   → 小規模 MLP (1-10M) を CPU で hours スケール、proxy task は MNIST/Fashion/CIFAR-10。
4. **α,β-CROWN small-cell 検証を fitness gate に**
   → cell 単位 (例: attention head 1 個 / SSM block 1 段) で Lipschitz/robustness 検証通過を生存条件にする。Marabou 軽量モデルで先に PoC。
5. **Sakana 風 model merge を CPU で**
   → RWKV-7 0.19B + Mamba-130M + 量子化重み merge の遺伝子化。CMA-ES。1 epoch evaluation は CPU で 分オーダー。

---

## 参考: llive 既存資料との接続
- [[project_persona_genome_integration]] : persona を遺伝子に焼き付け済、本調査の B/E と直接接続。
- [[project_llive_v0E_coevolution]] / [[project_llive_v0C_variant_evolution]] : 派生集団進化基盤、本調査の B-5/B-6 と overlap 評価が必要。
- [[project_llive_meta_cognition_evolution]] : meta_loop UCB1 と本調査 D の検証 gate 連動余地。
- `docs/non-transformer/COMPARISON.md` / `rwkv-cpu-quickstart.md` : 既存比較表/手順書と本サーベイのライセンス情報を突き合わせ要更新。

---

## Sources (集約)

### A. 非 Transformer sequence model
- [Mamba arXiv:2312.00752](https://arxiv.org/abs/2312.00752)
- [state-spaces/mamba (GitHub)](https://github.com/state-spaces/mamba)
- [llama.cpp PR #5328 Mamba](https://github.com/ggml-org/llama.cpp/pull/5328)
- [llama.cpp PR #9126 Mamba-2](https://github.com/ggml-org/llama.cpp/pull/9126)
- [RWKV-7 arXiv:2503.14456](https://arxiv.org/abs/2503.14456)
- [BlinkDL/RWKV-LM (GitHub)](https://github.com/BlinkDL/RWKV-LM)
- [BlinkDL/rwkv-7-world (HF)](https://huggingface.co/BlinkDL/rwkv-7-world)
- [Mungert/rwkv7-2.9B-world-GGUF (HF)](https://huggingface.co/Mungert/rwkv7-2.9B-world-GGUF)
- [RetNet arXiv:2307.08621](https://arxiv.org/abs/2307.08621)
- [MSR RetNet publication](https://www.microsoft.com/en-us/research/publication/retentive-network-a-successor-to-transformer-for-large-language-models/)
- [Hyena arXiv:2302.10866](https://arxiv.org/abs/2302.10866)
- [Hazy Research Hyena blog](https://hazyresearch.stanford.edu/blog/2023-03-07-hyena)
- [HazyResearch/safari (GitHub)](https://github.com/HazyResearch/safari)
- [CfC arXiv:2106.13898](https://arxiv.org/abs/2106.13898)
- [CfC Nature MI](https://www.nature.com/articles/s42256-022-00556-7)
- [raminmh/CfC (GitHub)](https://github.com/raminmh/CfC)
- [Hopfield is All You Need arXiv:2008.02217](https://arxiv.org/abs/2008.02217)
- [Krotov-Hopfield 2021 (IBM)](https://research.ibm.com/publications/large-associative-memory-problem-in-neurobiology-and-machine-learning)

### B. NAS / 進化
- [AutoML-Zero arXiv:2003.03384](https://arxiv.org/abs/2003.03384)
- [google-research/automl_zero](https://github.com/google-research/google-research/tree/master/automl_zero)
- [DARTS arXiv:1806.09055](https://arxiv.org/abs/1806.09055)
- [ENAS arXiv:1802.03268](https://arxiv.org/abs/1802.03268)
- [AmoebaNet arXiv:1802.01548](https://arxiv.org/abs/1802.01548)
- [AlphaEvolve arXiv:2506.13131](https://arxiv.org/abs/2506.13131)
- [DeepMind AlphaEvolve blog](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)
- [google-deepmind/alphaevolve_results](https://github.com/google-deepmind/alphaevolve_results)
- [Sakana evolutionary merge arXiv:2403.13187](https://arxiv.org/abs/2403.13187)
- [Sakana Nature MI](https://www.nature.com/articles/s42256-024-00975-8)

### C. 代替学習則
- [Forward-Forward arXiv:2212.13345](https://arxiv.org/abs/2212.13345)
- [Equilibrium Propagation arXiv:1602.05179](https://arxiv.org/abs/1602.05179)
- [EP Frontiers 2017](https://www.frontiersin.org/journals/computational-neuroscience/articles/10.3389/fncom.2017.00024/full)
- [PCN approx backprop arXiv:2006.04182](https://arxiv.org/pdf/2006.04182)
- [PCN beyond backprop arXiv:2202.09467](https://arxiv.org/pdf/2202.09467)
- [PCN neuromorphic eval arXiv:2304.02658](https://arxiv.org/pdf/2304.02658)
- [Deep-STDP arXiv:2307.04054](https://arxiv.org/abs/2307.04054)
- [S-TLLR arXiv:2306.15220](https://arxiv.org/abs/2306.15220)

### D. 検証 × NN/NAS
- [Marabou paper PDF](https://theory.stanford.edu/~barrett/pubs/KHI+19.pdf)
- [Marabou GitHub](https://github.com/NeuralNetworkVerification/Marabou)
- [alpha-beta-CROWN GitHub](https://github.com/Verified-Intelligence/alpha-beta-CROWN)
- [alpha-beta-CROWN vnncomp2024](https://github.com/Verified-Intelligence/alpha-beta-CROWN_vnncomp2024)
- [Binarized NN SMT arXiv:2011.02948](https://arxiv.org/pdf/2011.02948)
- [DSRNA arXiv:2012.06122](https://arxiv.org/pdf/2012.06122)
- [Robust NAS arXiv:2405.05502](https://arxiv.org/pdf/2405.05502)
- [VeriFlow arXiv:2406.14265](https://arxiv.org/abs/2406.14265)

### E. CPU 実機
- [PyTorch quantized LLM CPU blog](https://pytorch.org/blog/high-performance-quantized-llm-inference-on-intel-cpus-with-native-pytorch/)
- [dranger003/mamba-2.8b-hf-GGUF](https://huggingface.co/dranger003/mamba-2.8b-hf-GGUF)

---

(以上、計 約 3,000 字 + 表 + 参考文献)
