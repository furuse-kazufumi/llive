# 個人/小規模 compute での Architecture / Algorithm Evolution 事例

**作成**: 2026-05-28 (Agent C 事前調査)
**目的**: llive の「Verified Neural Architecture Evolution on CPU」研究で、個人 compute (laptop CPU / 32GB RAM / no GPU) で意味ある成果を出した先行例を honest に洗い出し、現実的 baseline と差別化軸を見積もる。

---

## A. AlphaEvolve / DeepMind 系 — 個人で扱える部分

**AlphaEvolve (Google DeepMind, 2025)**
- arxiv 2506.13131 (2025-06-16) / blog: <https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/>
- 結果 repo: <https://github.com/google-deepmind/alphaevolve_results> (結果データのみ、フレームワーク本体は **非公開**)
- 主成果: 4×4 complex matrix multiplication を 48 scalar mults で実現 (Strassen 1969 以来 56 年ぶり改善)。Google データセンタ/チップ設計の自動最適化。
- **個人で扱える部分**: 結果データ + 評価ベンチマーク定義のみ。Gemini-Pro orchestrator + 大量 inference budget が前提で **個人 compute では本体再現は無理**。

**FunSearch (DeepMind, 2023)**
- Nature 2023 (s41586-023-06924-6) / repo: <https://github.com/google-deepmind/funsearch>
- 公式 repo は **single-threaded 実装** + cap set / bin packing / corner-free sets の探索コード。LLM / sandbox / 分散基盤は非含。
- 第三者再現: <https://github.com/lumi-a/funsearch> (改良版 single-machine 実装)
- **個人で扱える部分**: コード本体 + 評価関数は手元で動く。LLM 呼び出しを API 経由 (Anthropic/OpenAI) にすれば laptop 1 台で小規模問題は回せる。

**OpenEvolve / CodeEvolve / ShinkaEvolve (open-source AlphaEvolve 系)**
- OpenEvolve: <https://github.com/algorithmicsuperintelligence/openevolve> (最も active な fork) / <https://github.com/jamesahou/openevolve> / <https://github.com/ryanrudes/openevolve>
- CodeEvolve: arxiv 2510.14150 — **open-weight models が closed source baseline と同等性能を fraction of compute cost で達成**を主張。
- ShinkaEvolve (Sakana AI, 2025-09): arxiv 2509.19349 / <https://github.com/SakanaAI/ShinkaEvolve> / <https://sakana.ai/shinka-evolve/>
  - 円パッキング問題で **150 samples** で SOTA 発見 (AlphaEvolve 系は通常数千 samples)。
  - 革新: (1) fitness/novelty 認識 parent sampling、(2) embedding-LLM novelty rejection、(3) UCB1 ベース LLM ensemble bandit。
  - **個人で扱える可能性最大** — Apache-2.0、sample efficiency が桁違いに高い。

---

## B. Sakana AI 系 — 公開実装の現状

**Evolutionary Model Merge (Sakana AI, 2024-03)**
- arxiv 2403.13187 / Nature Machine Intelligence 採録
- repo: <https://github.com/SakanaAI/evolutionary-model-merge> (Apache-2.0)
- アプローチ: 既存 open-weight モデル (Mistral 等) を進化的に merge → SOTA 日本語 LLM 構築。mergekit / Optuna に統合済。
- **個人で扱える部分**: evaluation コードは動くが、merge 候補生成は GPU/メモリ依存大。CPU 単機では 1.5B 級以下なら可能。

**CycleQD (Sakana AI, 2024)**
- LLM agent 集団進化 + model merging + QD (Quality-Diversity)。lifelong learning の最初の一歩を主張。
- 公開: blog のみ confirmed (<https://sakana.ai/blog/>)。本体コード公開は調査時点で未確認。

**The AI Scientist v1/v2 (Sakana AI, 2024-2025)**
- 完全自動研究エージェント。v2 paper が AI conference workshop の peer review に通過 (Nature d41586-026-00899-w 報告)。
- repo は公開。1 論文生成あたり API 経由 LLM コール多数で、**個人実行はコスト面で制約あり** (1 試行 $15-30)。

**Darwin Gödel Machine (DGM, Sakana AI / UBC / Vector Institute, 2025-05)**
- arxiv 2505.22954 / repo: <https://github.com/jennyzzt/dgm>
- 自分のコードを書き換えて改善する agent。SWE-bench 20.0% → 50.0%, Polyglot 14.2% → 30.7%。
- **個人で扱える部分**: コードは Apache 系で公開。ただし foundation model API (Claude/GPT) のヘビーコールが前提。CPU で動かすこと自体は可能だが lineage 展開には API 費用がかかる。

---

## C. 個人 compute での NAS 成果

**NAS-Bench-201 / NATS-Bench (D-X-Y, 2020-2024)**
- repo: <https://github.com/D-X-Y/NAS-Bench-201>
- **15,625 個の architecture を CIFAR-10/100 + ImageNet16-120 で完全 pre-trained**。`api.get_more_info(arch_index, dataset)` で訓練不要に accuracy 取得可能。
- **個人 compute で完全に動く** — 検索アルゴリズム研究はこれが事実上 de facto。llive の verified evolution 系の探索アルゴリズム検証にも 1 次採用候補。

**Zero-Cost NAS Proxies (2021-2024)**
- arxiv 2101.08134 (Abdelfattah, Mellor et al., ICLR 2021): minibatch 1 つで architecture を採点。3 桁高速化。
- 2024 後続: LPZero (Dong et al.), GreenMachine (Cortês et al., arxiv 2411.15290) — エネルギー効率志向の zero-cost proxy 自動設計。
- **個人で活用可能** — 1 architecture あたり数秒で proxy 評価。CPU で 100-1000 architecture を 1 日で探索できる。
- 注意: proxy と実 accuracy の Spearman correlation は 0.6-0.85 程度で **完璧ではない**。

**Weight Agnostic Neural Networks (WANN, Gaier & Ha, NeurIPS 2019)**
- repo: <https://weightagnostic.github.io/> / arxiv 1906.04358
- NEAT ベース、scalar weight 1 つで全 edge 共通。topology のみを進化。
- **CPU 親和性が非常に高い** (sparse + skip connection、GPU が活きない)。Raspberry Pi 移植実証あり (ACM DOI 10.1145/3486001.3486226)。
- **llive にとって参考価値大** — CPU で構造のみ進化する古典的成功例。

---

## D. AutoML-Zero フォローアップ詳細

**原論文**: Real, Liang, So, Le, ICML 2020 (arxiv 2003.03384)
- repo: <https://github.com/google-research/google-research/tree/master/automl_zero>
- 基本数学演算のみから ML アルゴリズム全体を発見 — 線形回帰、2 層 NN + backprop、weight averaging を**ゼロから再発見**。
- compute: 元論文は **数千 CPU core × 数日**。
- **個人 compute の限界**: 探索空間制約版なら laptop 1 台 + 数時間 - 数日で小さな結果は出る (例: 線形分類器の再発見)。完全な NN + SGD 再発見は厳しい。

**後続研究の方向性**:
- 構造制約付き探索空間で大幅効率化 — 例えば Forward/Backward 経路の prim を予め用意し損失関数や optimizer のみを進化。
- 限定 domain (時系列予測、特定 RL task) でのドメイン特化 AutoML-Zero 風研究。
- **直接的 follow-up paper の数は意外と少ない** (5 年で 100+ citation あるが構造再構成系は少なく、application 応用が大半)。これは llive にとって **未開拓領域** を意味し得る。

---

## E. GECCO / EvoStar 最新 best papers

**EvoStar 2025 (Trieste, 2025-04-23〜25)** — <https://www.evostar.org/2025/eml/>
- EuroGP + EvoApps 合同 Evolutionary Machine Learning track 設置。
- topics: neuroevolution / feature selection / evolutionary adversarial / AutoML / transfer learning / evolving learning functions。
- **best paper の specific 候補**: 公式 announce ページから個別特定できず — 個別論文は proceedings (Springer LNCS) を直接確認する必要あり。

**GECCO 2024**
- "Evolution and Efficiency in Neural Architecture Search" (arxiv 2403.17012) — expert design と automated optimization の架け橋。
- "G-EvoNAS: Evolutionary NAS Based on Network Growth" (arxiv 2403.02667) — 段階的 growth で計算効率向上。
- **個人参加者の活躍**: GECCO は伝統的に大学院生 + 中小研究室の発表が多く、laptop ベース実験論文も毎年複数本。

**HUMIES Award (GECCO)**
- 「人間競争レベルの結果を出した evolution」を表彰。llive の差別化軸として有用。

---

## F. Forward-Forward / Equilibrium-Prop の小規模実証

**Forward-Forward (Hinton, NeurIPS 2022 talk)**
- arxiv 2212.13345
- PyTorch 実装複数:
  - <https://github.com/mpezeshki/pytorch_forward_forward> (公式 talk 準拠)
  - <https://github.com/LukasMahieu/forward-forward-algorithm> (conv 拡張)
  - <https://github.com/visvig/forward-forward-algorithm> (CIFAR-10 notebook)
- **CIFAR 結果 (arxiv 2312.14924, "Training CNNs with FF")**: MNIST で 1.2% error, CIFAR-10 で約 21% error (BP の方が高精度)。
- **個人 compute 親和性**: layer-local 勾配で **メモリ消費が線形ではなく定数**。CPU で深い構造も訓練可能。

**Equilibrium Propagation (Scellier & Bengio, 2017→2024)**
- arxiv 2006.03824 (Laborieux et al.): CIFAR-10 で 11.7% test error (BPTT に肉薄)。
- arxiv 2508.14081 (2025): 寝起き様 lifelong learning + PyTorch 実装。
- **個人 compute**: convergent dynamics → 1 sample / 1 inference cycle あたり数十 step 必要で **CPU では時間かかる** が、メモリ効率は良い。MNIST 規模なら laptop 数時間で実証可能。

**llive にとっての意味**: FF / EP は「勾配計算を local 化」する仕組みで、CPU + 進化探索と相性が良い。learning rule 自体を進化対象にする際の **prim パレット** として有用。

---

## G. CPU で動く small LLM の最新地平

**llama.cpp ecosystem (2025)**
- <https://github.com/ggml-org/llama.cpp> — 100+ architectures をサポート (Mamba, RWKV 含む)。AVX/AVX2/AVX512 最適化、1000+ contributors。
- **BitMamba-2 (1.58-bit + Mamba2)**: Intel i3-12100F で **50 tokens/sec** を達成 (custom AVX2 kernel)。Discussion #19233。
- RWKV.cpp: <https://github.com/RWKV/rwkv.cpp> — INT4/5/8 + FP16, RWKV-6/7 対応。

**TinyLlama-1.1B** — <https://github.com/jzhang38/TinyLlama>
- 1.1B params × 3T tokens, 16×A100-40G × 90 日, **約 $140k**。
- **個人 compute での train from scratch は事実上 GPU farm 必須**。CPU では 5-10 年スケール、現実的でない。
- 個人で出来るのは **inference + fine-tune** のみ (laptop CPU で 2-5 tokens/sec)。

**TinyStories (Eldan & Li, Microsoft, 2023)**
- arxiv 2305.07759 — 10M parameter (!) transformer が首尾一貫した英語短編を生成。
- **single GPU 1 日未満**で train 完了 — つまり **CPU でも数日〜1 週間で可能**。
- llive の verified evolution 検証用 toy model として **第一候補**。

**nanoGPT / nanochat (Karpathy)**
- <https://github.com/karpathy/nanoGPT>: `--device=cpu --compile=False` で CPU 動作可。小型 (4 layer, 4 head, 128 embed) なら laptop OK。
- nanochat (2025-10): $100 / 4h × 8×H100 で ChatGPT クローン — GPU 前提だが「budget LLM training」の基準点。
- nanoGPT 自体が **recursive self-improvement benchmark** として使われ始めている (Karpathy ツイート言及)。

**Regional Tiny Stories (arxiv 2504.07989, 2025)**
- 多言語 small LM 学習比較。**CPU+laptop で各言語 100M 級モデル train** が現実的。

---

## 現実的 baseline ─ 個人 compute で目指せる範囲 (honest)

**ハード**: laptop CPU (現代 8-16 core) / 32GB RAM / no GPU
**到達可能 ライン (honest 評価)**:

| 課題 | 個人 CPU 可否 | 備考 |
|---|---|---|
| TinyStories 10M model train from scratch | **可** | 数日 - 1 週間 |
| TinyStories 100M model train | △ | 1-2 週間、メモリギリ |
| TinyStories 級 from scratch を **進化的探索の評価対象**にする | **可** (1 architecture / 数日) | 100 architecture = 半年〜1 年。NAS-Bench で proxy 化が必須 |
| TinyLlama 1.1B from scratch | **不可** | GPU farm $100k+ |
| 既存 1B+ model fine-tune | **可** (LoRA) | inference 2-5 tok/sec |
| BitMamba 1.58b inference | **可** | 50 tok/sec |
| Forward-Forward / EP on MNIST | **可** | 数時間 |
| Forward-Forward on CIFAR-10 | **可** | 1-2 日 |
| NAS-Bench-201 ベース探索 (15,625 arch) | **可** | API 経由 instant、探索アルゴリズム研究 ◎ |
| Zero-cost proxy で 1000 architecture 探索 | **可** | 1 日以内 |
| AutoML-Zero 級 ゼロからの ML 発見 | **限定的に可** | 制約付き探索空間 + toy task |
| ShinkaEvolve 風 LLM-driven 進化 (API 経由) | **可** | API 費用 $50-500 / experiment |

**探索規模目安**:
- NAS-Bench level: 1 万 architecture (proxy 評価): **可**
- 100 architecture (実 train, TinyStories 級): **数日 - 数週間**
- 1000 generation × 10 individual の遺伝アルゴリズム: モデル評価が proxy 化されれば **可**

---

## llive にとっての含意 — 「個人で勝てる」差別化軸

先行研究と重複しない、CPU+laptop で意味ある結果が出せる軸:

1. **Z3 verifier で探索空間 prune** — 大手未着手。SMT で「学習則が局所収束する制約」「architecture が dimension 整合性を持つ制約」を表現し、無効解を進化前に排除する。AlphaEvolve 系は **empirical fitness のみ**で形式検証なし。
2. **persona-indexed specialist 集団** — `project_persona_genome_integration` で着地済の方向性。Friston/Millidge/磯村等 persona を進化ゲノムに組込み済。1000 世代 5-7s で完走実証あり。
3. **factor_hook で認知状態 → SSM Δ 動的化** — 10 思考因子をメモリ層 2D matrix chromosome に着地済 (`project_llive_thought_factor_per_layer`)。SSM (Mamba/RWKV) の Δ パラメータを動的化する研究は未開拓。
4. **CPU 親和的 prim パレット** — FF / EP / WANN の learning rule を進化探索の prim として組み込む。GPU farm 大手は backprop + AdamW 一択。
5. **sample efficient evolution** — ShinkaEvolve の novelty rejection + UCB1 LLM ensemble を踏襲しつつ、verifier prune と組み合わせて 100 sample 以下で SOTA を狙う。

---

## honest 留保

**未確認領域**:
- EvoStar 2025 best paper の specific 受賞論文 — 公式アナウンスから個別特定できず。Springer LNCS proceedings 直接参照が必要。
- CycleQD のコード公開状況 — blog のみ確認、本体 repo は調査時点で未確認。
- "個人 compute で大手と並ぶ" 主張のあるリポジトリ群 — star 数ベースの間接情報のみで、実測再現は未実施。

**"個人で出来た" 主張の真贋検証ステータス**:
- ShinkaEvolve の 150 sample で SOTA は **論文+ blog +コード公開**で trace 可能。真贋:高。ただし API LLM call が前提なので「ピュア CPU only」ではない。
- TinyStories 10M train 1 日未満: **論文 + 多数の独立再現**あり。真贋:極高。
- WANN の Raspberry Pi 移植: ACM 論文化されているが、性能比較の honest 評価は要確認。
- Forward-Forward CIFAR 21% error: BP 比劣勢を **明確に開示**しており honest disclosure 観点で良好。

**llive 研究上の警告**:
- 「進化で algorithm を発見」系の主張は **Sakana AI / DeepMind が桁違いの compute budget で先行**しており、honest disclosure の `feedback_benchmark_honest_disclosure` 規律のもと「我々は 100 sample で達成」等の主張時は **API call 数 / wall-clock / 評価 task の comparable 性** を必ず開示すること。
- AlphaEvolve 系 (LLM-driven program evolution) はゲノム/個体評価の **両方が API 経由 LLM call** で、純粋 CPU only ではない。llive で「CPU only」を主張するなら **prim ベース AutoML-Zero 系**に軸足を置く方が無理がない。

---

## 主要一次情報 URL リスト

- AlphaEvolve: <https://arxiv.org/abs/2506.13131> / <https://github.com/google-deepmind/alphaevolve_results>
- FunSearch: <https://www.nature.com/articles/s41586-023-06924-6> / <https://github.com/google-deepmind/funsearch>
- ShinkaEvolve: <https://arxiv.org/abs/2509.19349> / <https://github.com/SakanaAI/ShinkaEvolve>
- Sakana Evolutionary Model Merge: <https://github.com/SakanaAI/evolutionary-model-merge>
- Darwin Gödel Machine: <https://arxiv.org/abs/2505.22954> / <https://github.com/jennyzzt/dgm>
- AutoML-Zero: <https://arxiv.org/abs/2003.03384> / <https://github.com/google-research/google-research/tree/master/automl_zero>
- NAS-Bench-201: <https://github.com/D-X-Y/NAS-Bench-201>
- Zero-Cost NAS: <https://arxiv.org/abs/2101.08134>
- WANN: <https://weightagnostic.github.io/> / <https://arxiv.org/abs/1906.04358>
- Forward-Forward (Hinton): <https://arxiv.org/abs/2212.13345>
- FF for CNN: <https://arxiv.org/abs/2312.14924>
- Equilibrium Prop scaling: <https://arxiv.org/abs/2006.03824>
- TinyStories: <https://arxiv.org/abs/2305.07759>
- TinyLlama: <https://github.com/jzhang38/TinyLlama>
- llama.cpp: <https://github.com/ggml-org/llama.cpp>
- rwkv.cpp: <https://github.com/RWKV/rwkv.cpp>
- nanoGPT/nanochat: <https://github.com/karpathy/nanoGPT> / <https://github.com/karpathy/nanochat>
- OpenEvolve (open AlphaEvolve): <https://github.com/algorithmicsuperintelligence/openevolve>
- CodeEvolve: <https://arxiv.org/abs/2510.14150>
- EvoStar 2025: <https://www.evostar.org/2025/eml/>
