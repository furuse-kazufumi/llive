# AI 開発で役に立つアルゴリズム体系化

> **起草**: 2026-05-23 (llive optimize/core-2026-05-20 branch)
> **目的**: ユーザー指示「AI 開発で役に立ちそうなアルゴリズム一覧表を作成 +
> Perplexity も使って体系化 + 新たな気付き」.
> **文脈**: [[project_llive_thought_factor_per_layer]] / [[project_llive_rwkv_backend]] /
> [[project_llive_v0E_coevolution]] 着地後の整理.
> **手法**: WebSearch (6 query 2026-05-23) + llive 実装現状の交差で体系化.

## 体系化軸 (9 カテゴリ)

| # | カテゴリ | 何を解決するか |
|---|---|---|
| 1 | **学習** (training) | base model 作成 |
| 2 | **後学習・整列** (post-training / alignment) | 人間/AI feedback で品質向上 |
| 3 | **推論最適化** (inference) | latency / cost 削減 |
| 4 | **推論 / reasoning** (test-time scaling) | 出力品質を inference 時に向上 |
| 5 | **アーキテクチャ** (model architecture) | スケーリング法則 + 長 context |
| 6 | **進化計算 / 探索** (evolutionary / search) | hyperparameter / 表現の最適化 |
| 7 | **記憶 / 検索** (memory / retrieval) | 知識の永続化 + 想起 |
| 8 | **評価 / 観測** (eval / observability) | 性能の計測 + drift 検出 |
| 9 | **安全性 / 整列** (safety) | 暴走防止 + 監督 |

---

## 1. 学習 (training)

| アルゴリズム | 用途 | llive 関係 |
|---|---|---|
| **SFT** (Supervised Fine-Tuning) | base instruction tuning | 未着 (前提) |
| **Pre-training (NTP)** | 大規模 corpus | 外部 backend に委任 |
| **Constitutional AI** (Anthropic) | self-supervised safety | 検討余地 |
| **Distillation** (Hinton) | teacher → student 小型化 | 検討余地 |
| **Self-Play** (AlphaGo 系) | 自己改善 | [[project_llive_v0E_coevolution]] と類似 |
| **Curriculum Learning** | 易→難 段階学習 | progressive matrix と親和 |

## 2. 後学習・整列 (post-training / alignment)

最も動きが激しい領域 (2024-2026)。on-policy vs off-policy + reward 形式で分類:

| アルゴリズム | 必要なもの | 特徴 | 採用判断 |
|---|---|---|---|
| **PPO** | critic + reward model | 安定だがメモリ 2x. 標準だが重い | RLHF 王道だが重 |
| **DPO** (Rafailov 2023) | 比較 pair | reward model 不要. シンプル | low-cost 代替 |
| **GRPO** (DeepSeek) | group sampling | critic 不要 + 数学 reasoning 強 | DeepSeek-R1 系 |
| **ORPO** (Hong 2024) | preference + SFT 同時 | SFT + 整列を 1 stage で | 効率良し |
| **KTO** (Ethayarajh 2024) | thumbs ↑/↓ binary | paired 不要. 実運用向き | production 向け |
| **SimPO** (Meng 2024) | preference のみ | ref model 不要. avg log prob | 軽量、AlpacaEval +6.4 |
| **DAPO** (2025) | adaptive dynamic | GRPO 改良 | 最新 |
| **RLVR** (Verifier Rewarded) | verifier | 検証可タスク用 (math/code) | OpenAI o1 系 |
| **RLAIF** | AI feedback | 人手不要 (AI ↔ AI) | scaling oversight |
| **AlphaPO** | alpha-divergence | distribution shift 抑制 | 最新 |

**llive 連動**: NSGA2 (既実装) と組合せれば「safety vs quality vs latency」多目的 Pareto で扱える.

## 3. 推論最適化 (inference)

「データ移動量を減らす」+「メモリ load あたり仕事量を増やす」の 2 方向 (Morph 2026):

| アルゴリズム | カテゴリ | 効果 | llive/llmesh 関係 |
|---|---|---|---|
| **KV cache** | memory | 必須 | 全 backend 前提 |
| **PagedAttention** (vLLM, Kwon 2023) | memory | 断片化なし、lossless | llmesh 検討候補 |
| **FlashAttention / FA-2 / FA-3** | compute | HBM 削減 O(N) | local 推論で有効 |
| **Continuous batching** | throughput | 連続バッチ詰め | server 用途 |
| **Speculative decoding** (Leviathan 2023) | latency | draft + target 検証 | medusa, EAGLE |
| **PagedAttention + streaming KV** | hybrid | 長 context 維持 | 長文 inference |
| **Quantization** (FP8, INT4, GPTQ, AWQ, GGUF) | size+speed | 4-8x mem 削減 | llmesh で KV quant 既導入 |
| **MQA / GQA** | architecture | head reduction | base model 設計時 |
| **Multi-token prediction** | latency | 1 step で N token | DeepSeek-V3 |
| **vLLM / TGI / TRT-LLM** | engine | production serving | 3 大 engine |

**Combo の威力**: FP8 + FlashAttn-3 + continuous batching + speculative で **5-8x cost-eff** vs naive FP16 ([Morph 2026](https://www.morphllm.com/llm-inference)).

## 4. 推論 / reasoning (test-time scaling)

OpenAI o1 (2024) 以降爆発した領域。L1 (固定 budget) vs L2 (適応的 scale) で分類 ([arXiv:2504.09037](https://arxiv.org/pdf/2504.09037)):

| アルゴリズム | 構造 | cost | llive 連動 |
|---|---|---|---|
| **Chain-of-Thought (CoT)** (Wei 2022) | 線形 chain | 1x | PromptChromosome `language_style` で誘導 |
| **Self-Consistency** (Wang 2022) | N sample → vote | N x | A/B run と親和 |
| **Tree-of-Thought (ToT)** (Yao 2023) | 木探索 | 10-50x | 高コスト、選択肢探索 |
| **Graph-of-Thought (GoT)** | グラフ | 5-30x | knowledge structure + reasoning |
| **Matrix-of-Thought** (2025) | chain × tree 行列 | 中 | 最新 |
| **Chain-in-Tree** (2025) | tree 内 chain | 中 | 最新 |
| **Forest-of-Thought** (2025) | test-time compute scale | 高 | scaling 路線 |
| **ReAct** (Yao 2022) | thought → act → obs loop | tool 依存 | Brief API + MCP 親和 |
| **Reflexion** (Shinn 2023) | verbal self-correction | iterative | [[project_llm_wiki_pattern]] LLW と合流可 |
| **Best-of-N + verifier** | reranking | N x | RLVR 系の inference 版 |
| **Process Reward Model** | step-level reward | 訓練必要 | o1 系 |
| **L1 controllability** | 固定 budget | constant | 計画的予算配分 |
| **L2 adaptiveness** | 入力依存 | variable | confidence-driven |

**重要発見**: llive `RecursionDepthGene` ([[project_llive_v0F_genome_two_layer]]) はまさに **L2 adaptive scaling** の遺伝表現として位置づけ可能.

## 5. アーキテクチャ (model architecture)

2026 時点で Transformer 王座継続だが SSM/RWKV 系が長 context で chip away ([Local AI Master 2026](https://localaimaster.com/blog/mamba-state-space-models-guide)):

| アルゴリズム | 計算量 | 強み | 弱み | llive backend 状態 |
|---|---|---|---|---|
| **Transformer** | O(N²) attention | 短-中 context 最強 | 128K+ で爆発 | ✅ Anthropic/OpenAI/Ollama 既稼働 |
| **Mamba / Mamba-2** (Gu/Dao 2024) | O(N) selective SSM | 長 context 安価 | training tricky | 未着 (CUDA + Linux 前提) |
| **RWKV-7 "Goose"** (Peng 2025) | O(N) recurrent | CPU 動作 + 7B で Llama 3.1 8B 競合 | tooling 限定 | ✅ **本日 skeleton 着地** |
| **Jamba** (AI21 2024) | Transformer:Mamba = 1:7 + MoE | 256K context + 効率 | 52B → on-prem 困難 | ✗ (cloud only) |
| **MoE** (Mixtral, DeepSeek-MoE) | sparse expert routing | 高品質 + 低 active params | routing 不安定 | 検討余地 |
| **MoE-Mamba** (Pióro 2024) | SSM + MoE | Mamba を 2.2x 速 training | research 段階 | 検討余地 |
| **Falcon Mamba** | pure SSM | 7B in production | RWKV と競合 | 検討余地 |
| **Hyena / Striped Hyena** | conv-based long convolution | long range | tooling 弱 | 検討余地 |
| **Diffusion LLM** (Mercury 2025) | text diffusion | 並列生成 | 別系統 | VLM 文脈で別計画 |

**Practical guide ([CallSphere 2026](https://callsphere.ai/blog/transformer-alternatives-mamba-rwkv-state-space-models-2026))**:
- **長 context + 効率**: Mamba / RWKV
- **短-中 context + 最強品質**: Transformer
- **mobile / embedded**: RWKV (state-only)
- **genomics / time-series**: SSM 系
- **百万-token agent**: Mamba 系

## 6. 進化計算 / 探索 (evolutionary / search)

llive のメイン路線。実装在庫が豊富:

| アルゴリズム | 種別 | llive 実装 |
|---|---|---|
| **GA** (Genetic Algorithm) | base | ✅ `EvolutionLoop` |
| **CMA-ES** (Hansen 2003) | covariance adaptive | 検討余地 (継続 numeric に強) |
| **Differential Evolution** (Storn 1997) | vector difference | 検討余地 |
| **NSGA-II** (Deb 2002) | 多目的 Pareto | ✅ `nsga2.py` |
| **Island Model** (Cohoon 1987) | 分散進化 + migration | ✅ `island_model.py` + dashboard 着地 (本日) |
| **Novelty Search** (Lehman 2008) | quality 無視 → 多様性 | ✅ `novelty_lane.py` |
| **MAP-Elites** (Mouret 2015) | grid 埋め QD | ✅ `quality_diversity.py` |
| **PGA-MAP-Elites** (Nilsson 2021) | policy gradient + ME | 検討余地 (deep NE 向け) |
| **ME-NSS** | novelty + surprise hybrid | 検討余地 |
| **NEAT** (Stanley 2002) | topology evolution | 検討余地 |
| **Tournament/Roulette/Lexicase** | selection | ✅ `selection.py` |
| **Self-adaptive σ** | mutation rate も遺伝 | ✅ `self_adaptive.py` |
| **Speciation** (NEAT 由来) | 種分化 | ✅ `speciation.py` |
| **Genome3D 4 階建て** | impl + prompt + meta + factors | ✅ **本日着地** (本 PR) |
| **CoDeepNEAT** | NN topology + hyperparam 共進化 | 検討余地 |
| **EvoFlow** | LLM driven evolution | 検討余地 (最新 2025) |
| **Promptbreeder** (Fernando 2023) | prompt 自己改良 | PromptChromosome の設計 root |

## 7. 記憶 / 検索 (memory / retrieval)

| アルゴリズム | 構造 | llive 4 層メモリ連動 |
|---|---|---|
| **Naive RAG** | dense/sparse retrieval | RAD ベース |
| **HyDE** | LLM が hypothetical doc 生成 → embed | working layer で生成 |
| **Reranker** (BGE/Cohere) | second-stage filter | precision 向上 |
| **GraphRAG** (Microsoft 2024) | knowledge graph retrieval | long_term layer 親和 |
| **Agentic Graph RAG** | retrieve-evaluate-refine loop | Reflexion 系と合流 |
| **Self-RAG** (Asai 2023) | retrieval を model 自身が判定 | confidence-driven |
| **Knowledge Graph + 多段 reasoning** | structured | episodic layer 連動 |
| **Long-context (1M+)** | SSM 有利 | RWKV/Mamba 着地で開放 |
| **Episodic memory + consolidation (sleep)** | 神経科学風 | ✅ `consolidation` 既存 |
| **Vector DB** (Faiss, Pinecone, Milvus) | dense index | llmesh で対応 |
| **Hybrid (BM25 + dense)** | sparse + dense 結合 | 標準 |
| **MemGPT** (Packer 2024) | LLM 自身が memory 管理 | 4 層メモリの管理者を LLM 化 |

## 8. 評価 / 観測 (eval / observability)

| アルゴリズム | 用途 | llive/lleval 連動 |
|---|---|---|
| **A/B test** | baseline 比較 | ✅ lleval スコープ |
| **Progressive size matrix** (xs/s/m/l/xl) | scaling curve | ✅ lleval LE-02 |
| **Honest disclosure 5+1 軸** | latency/quality/stability/safety/honesty + meta | ✅ lleval LE-01 |
| **LLM-as-judge** | 自動評価 | ✅ Brief API |
| **Judge rotation + position swap** | self-preference bias 検出 (Panickssery 2024) | ✅ lleval LE-03 |
| **Span tracing** (OpenInference) | Phoenix / Arize | 検討余地 (skill ある) |
| **Pareto front 可視化** (NSGA2) | 多目的 dashboard | ✅ 本日 evolution_dashboard |
| **MAP-Elites grid 可視化** | QD 進捗 | 検討余地 |
| **Reference dataset + holdout** | 標準ベンチ | 検討余地 |
| **Helm / Big-Bench-Hard / MMLU** | 標準 suite | 外部 |
| **Confidence calibration** (ECE) | 自己評価精度 | 検討余地 |
| **Drift monitoring** | 基盤更新検出 | honest disclosure 6 番目軸候補 |

## 9. 安全性 / 整列 (safety)

| アルゴリズム | 特徴 | llive 連動 |
|---|---|---|
| **Constitutional AI** (Anthropic) | self-supervised safety | 検討余地 |
| **Debate** (Irving 2018) | adversarial alignment | scaling oversight |
| **AI Watchdog / Approval Bus** | gatekeeping | ✅ llive 既内蔵 |
| **Scaling oversight** | 監督者 LLM | RLAIF と合流 |
| **Red-teaming** | adversarial 入力 | 検討余地 |
| **Refusal training** | NSFW/危険拒否 | 標準 |
| **Watermarking** (Kirchenbauer 2023) | 出力署名 | 検討余地 |

---

## 新たな気付き (honest disclosure 観点)

WebSearch 6 件 + llive 実装在庫の交差から見えた発見:

1. **llive の進化計算は GA family が中心で CMA-ES / DE が無い**.
   sphere/rosenbrock のような **continuous numeric** な探索では CMA-ES が GA を
   大きく上回ることが既知. ThoughtFactorPerLayerChromosome は 40-dim continuous
   matrix なので CMA-ES と相性が良い. **検討価値: 高**.

2. **後学習 (DPO/GRPO/ORPO/KTO/SimPO) が完全未着手**.
   llive は「LLM の外側で進化」を扱うが「LLM 自体を後学習」する path は無い.
   GRPO の group sampling は llive variant 評価と shape が似ている (N variant ×
   1 reference) — **既存進化基盤を後学習にも転用できる可能性**.

3. **推論最適化 (FlashAttn-3 / PagedAttention / Speculative) は完全に llmesh の管轄**
   だが、未着手. on-prem ローカル推論で 5-8x のコスト効率が手に入る軸を放置している.
   [[project_llmesh_critical_review]] と合流して優先度を上げるべき.

4. **推論 reasoning (CoT/ToT/Reflexion/GoT/Matrix-of-Thought)** が PromptChromosome
   経由でしか組み込まれていない. **`RecursionDepthGene`** は L2 adaptive scaling の
   遺伝表現として位置づけ直すと意味が明確になる ([[project_llive_v0F_genome_two_layer]]
   の見直し価値).

5. **GraphRAG / Agentic Graph RAG が未着手**. llive 4 層メモリの **long_term layer**
   は knowledge graph + multi-hop reasoning と最も親和性が高い構造 (因子 × 層
   ゲノム化で「graph-aware factor strength」が表現可能).

6. **マルチモーダル系 (画像/音声) backend 未着** ([[project_llive_vlm_future]]).
   Diffusion LLM (Mercury) や VLM (LLaVA, Qwen-VL 等) が「眼鏡 v2」(マルチモーダル
   評価) の前提. これは「未着手の Backend」群に加える価値.

7. **「眼鏡」は本 doc 自体が眼鏡 v0**.
   一覧化 + 体系化することで「**llive がカバーしている領域 vs 未着の領域**」が
   一望できるようになった. これを毎月 update することで cumulative な状況把握が可能
   (NEXT_SESSION 月次 task として価値).

## llive 既存 vs 未来 まとめ表

| カテゴリ | 既実装 | 検討候補 |
|---|---|---|
| 進化 | GA / Island / QD / NSGA2 / Self-adaptive / Speciation / Genome3D | **CMA-ES** / DE / NEAT / PGA-MAP-Elites / EvoFlow |
| Architecture | Transformer ✅ / RWKV skeleton ✅ | **Mamba** / Jamba / MoE-Mamba / Falcon Mamba / Hyena |
| 学習 | (未) | SFT / Distillation |
| 後学習 | (未) | **DPO** / **GRPO** / ORPO / KTO / SimPO / DAPO / RLVR / RLAIF |
| 推論最適化 | (llmesh 側で KV quant) | **FlashAttn-3** / **PagedAttention** / Speculative / vLLM 統合 |
| 推論 reasoning | RecursionDepthGene (L2 adaptive) | ToT / Reflexion / ReAct / GoT / Self-Consistency |
| 記憶 | 4 層メモリ / consolidation / RAD | **GraphRAG** / Agentic Graph RAG / MemGPT / Self-RAG |
| 評価 | lleval LE-01..07 / honest disclosure | Phoenix span / MAP-Elites grid 可視化 / Drift monitoring |
| 安全性 | Approval Bus / fail-closed | Constitutional / Debate / Watermarking |

## 優先度ランキング (推奨着手順、honest disclosure)

1. **CMA-ES を進化計算 module に追加** — continuous 探索で GA より高速、Genome3D.c_factors 用. 1 日.
2. **GraphRAG skeleton** — 4 層メモリ × knowledge graph で本質的多様性増. 2 日.
3. **Mamba backend** (`MambaPyBackend`) — RWKV に続く SSM 系第二弾. WSL2 要. 2 日.
4. **DPO / GRPO mock 評価** — variant 評価基盤を後学習 path に転用. 2-3 日.
5. **FlashAttention-3 / PagedAttention 検討** — llmesh 側で 5-8x 効率. 1 週間.
6. **Constitutional AI / Debate** — llive Approval Bus の理論裏付け. 1 週間+.

## Sources (WebSearch 2026-05-23)

### 後学習・整列
- [Post-Training in 2026: GRPO, DAPO, RLVR & Beyond](https://llm-stats.com/blog/research/post-training-techniques-2026)
- [A Guide to RL Post-Training for LLMs: PPO, DPO, GRPO, and Beyond](https://huggingface.co/blog/karina-zadorozhny/guide-to-llm-post-training-algorithms)
- [DPO vs PPO for LLMs: Key Differences](https://www.clarifai.com/blog/dpo-vs-ppo)
- [Comparative Analysis of PPO, GRPO, DAPO (arXiv:2512.07611)](https://arxiv.org/html/2512.07611v1)
- [Aman's AI Journal: Policy/Preference Optimization Primer](https://aman.ai/primers/ai/preference-optimization/)

### アーキテクチャ
- [Mamba & State-Space Models Guide (2026)](https://localaimaster.com/blog/mamba-state-space-models-guide)
- [Beyond Transformers: Mamba, RWKV, SSM (2026)](https://callsphere.ai/blog/transformer-alternatives-mamba-rwkv-state-space-models-2026)
- [Jamba's Hybrid Transformer-Mamba Design (Medium)](https://gregrobison.medium.com/architectural-evolution-in-large-language-models-a-deep-dive-into-jambas-hybrid-transformer-mamba-c3efa8ca8cae)
- [The Transformer Rebellion (Medium)](https://tao-hpu.medium.com/the-transformer-rebellion-four-architectures-challenging-llm-dominance-cfd5fbc23cb3)
- [Attention was never enough: Hybrid LLMs (AI21)](https://www.ai21.com/blog/rise-of-hybrid-llms/)
- [MoE-Mamba (arXiv:2401.04081)](https://arxiv.org/pdf/2401.04081)

### 推論最適化
- [LLM Inference: Prefill, Decode, KV Cache (Morph 2026)](https://www.morphllm.com/llm-inference)
- [LLM Inference Optimization Techniques (Clarifai)](https://www.clarifai.com/blog/llm-inference-optimization/)
- [LLM Inference Optimization: KV Cache, Batching, Paged/Flash (Towards AI)](https://pub.towardsai.net/llm-inference-optimization-730b2d718a44)
- [KV Cache Optimization Strategies (arXiv:2603.20397)](https://arxiv.org/html/2603.20397v1)

### 推論 reasoning
- [A Survey of LLM Reasoning (arXiv:2504.09037)](https://arxiv.org/pdf/2504.09037)
- [How LLM Reasoning Powers Agentic AI (Medium)](https://medium.com/@anicomanesh/how-llm-reasoning-powers-the-agentic-ai-revolution-cbefd10ebf3f)
- [Chain or Tree? Matrix of Thought (arXiv:2509.03918)](https://arxiv.org/pdf/2509.03918)
- [Chain-in-Tree (arXiv:2509.25835)](https://arxiv.org/pdf/2509.25835)
- [Forest-of-Thought (arXiv:2412.09078)](https://arxiv.org/pdf/2412.09078)
- [From RAG to Multi-Agent Systems (Preprints 2025)](https://www.preprints.org/manuscript/202502.0406/v1)
- [Reflexion Agents with LangGraph (DEV)](https://dev.to/im-shafiqurehman/from-simple-llms-to-reliable-ai-systems-building-reflexion-based-agents-with-langgraph-1a5n)
- [Graph Counselor: Multi-Agent Graph Exploration (arXiv:2506.03939)](https://arxiv.org/pdf/2506.03939)

### 進化計算 / QD
- [Scaling MAP-Elites to Deep Neuroevolution (arXiv:2003.01825)](https://arxiv.org/pdf/2003.01825)
- [Quality Diversity: Novelty Search to MAP-Elites (Mouret)](https://rl-vs.github.io/rlvs2021/class-material/evolutionary/light-virtual_school_qd.pdf)
- [PGA-MAP-Elites for Neuroevolution (ACM)](https://dl.acm.org/doi/10.1145/3577203)
- [Blending Notions of Diversity for MAP-Elites](https://www.antoniosliapis.com/papers/blending_notions_of_diversity_for_map_elites.pdf)

### 全体トレンド
- [Top LLMs and AI Trends for 2026 (Clarifai)](https://www.clarifai.com/blog/llms-and-ai-trends)
- [LLM News (May 2026)](https://llm-stats.com/ai-news)
- [Toward Large Reasoning Models (ScienceDirect 2025)](https://www.sciencedirect.com/science/article/pii/S2666389925002181)
