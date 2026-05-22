# llive 要件定義 v0.I — Meta-Evolution + Cross-Substrate Genome + Multi-D Maturity Scale

**Drafted:** 2026-05-22 (セッション末, ユーザー指示 "TRIZ 発想法で先読みせよ" に応答)
**Status:** **要件登録 (構想)** — v0.F/G/H 完了後. ユーザー発想を先読みして Claude 側が能動提案.
**Type:** Foundational architectural extension — meta-level evolution + substrate independence + multi-dimensional scoring
**Trigger:** ユーザー指摘 (2026-05-22):

> ちゃんと、内容は確認して私が次に発想しそうな内容を先読みするくらいでないといけません. TRIZ の発想法をベースに開発しているのだから、私に負けないくらいのアイデアを出してくださいね. (中略) 技術的にも驚かせてください.

[[feedback_proactive_ideation_user_pace]] の最初の実演として、本セッション anchor 集合から TRIZ 矛盾を検出して 5 案を出した記録. 各案に **数式 + 既存論文 anchor + 実装着地点** を併記.

---

## 1. TRIZ 矛盾分析 — anchor 集合の "欠けている象限"

本セッションで集まった anchor (技術 5 + 漫画 3 + 科学/SF 2 = 10 系統) を 39×39 TRIZ matrix にプロットして「**まだ提案されていない方向**」を逆算:

| 検出された矛盾 | 改善したい特性 (parameter) | 悪化する特性 (parameter) | TRIZ 40 原理候補 |
|---|---|---|---|
| 「進化アルゴリズムを固定したい (収束)」 vs 「適応したい (探索)」 | #35 Adaptability | #13 Stability of object | 1 segmentation / 13 the other way round / 25 self-service |
| 「多様な anchor を持ちたい」 vs 「設計のブレが増える」 | #35 Adaptability | #36 Complexity of device | 1 segmentation / 5 merging / 40 composite |
| 「個体を進化させたい」 vs 「過去の良かった個体を失いたくない」 | #4 Length / #34 Repairability | #25 Loss of time | 16 partial action / 24 intermediary / 34 rejecting+regenerating |
| 「単一スコアで比較したい」 vs 「多次元の質的進化を捉えたい」 | #28 Accuracy of measurement | #36 Complexity of device | 17 another dimension / 35 parameter change / 24 intermediary |
| 「自由に進化させたい」 vs 「危険な領域は触らせたくない」 | #35 Adaptability | #11 Stress / #30 External harm | 11 beforehand cushioning / 40 inert atmosphere / 22 blessing in disguise |
| 「実装言語を選びたい」 vs 「同じ進化軌跡を共有したい」 | #33 Convenience of use | #35 Adaptability | 40 composite / 27 cheap short-living / 28 mechanical substitution |

→ 矛盾 6 個 × 平均 3 原理 = 18 通りの解法候補から **最も非自明 + 数学的厳密 + 実装具体的な 5 案** を抽出.

---

## 2. 5 先読み案 (TRIZ ベース)

| 案 | TRIZ 原理 | 解く矛盾 | 1 行要約 |
|---|---|---|---|
| **A. Meta-Evolution Gene** | 25 self-service + 13 other way round | アルゴリズム固定 vs 適応 | 進化アルゴリズム自体を Genome として進化させる (Schmidhuber 系) |
| **B. Phylogenetic Memory** | 16 partial action + 34 reject+regenerate | 進化したい vs 過去保存 | 全 lineage を git-like content-addressable で保存、絶滅復元可能 |
| **C. 4D Kardashev Radar** | 17 another dimension + 35 parameter change | 単一スコア vs 多次元 | Energy × Knowledge × Coordination × Ethics の 4 軸 + 時間 5D |
| **D. Frozen Ethics Gene** | 11 beforehand + 40 inert atmosphere | 進化自由 vs 危険領域 | Genome の一部 gene を `frozen` marking、Approval Bus が違反検出 |
| **E. Cross-Substrate Genome** | 40 composite + 28 mechanical substitution | 実装選択 vs 進化共有 | Genome を Python/Rust/neuromorphic/BCI 経由人間個体で共有 |

---

## 3. 案 A: Meta-Evolution Gene (深掘り)

### 3.1 アイデア

進化アルゴリズム自体を Genome の chromosome として **進化対象に含める**. v0.D self-adaptive σ + meta-mutation を **本格的なメタ進化** に昇格させる.

参考: Schmidhuber 2003 "Optimal Ordered Problem Solver" (OOPS) / Hutter 2005 "Universal AI" (AIXI 近似) / Real et al. 2020 "AutoML-Zero" (進化で進化アルゴリズム発見) / Wang et al. 2024 "Promptbreeder".

### 3.2 形式化

```
State:
  P_t = population at generation t           (集団)
  A_t = evolution algorithm at generation t  (アルゴリズム自体, Genome chromosome "C-meta")
  K_t = Kolmogorov complexity proxy          (例: gzip-encoded A_t length)
  F_t = fitness function (可変, 4D Kardashev からも引ける)

Transition (1 generation):
  P_{t+1} = A_t(P_t)
  Δ_t    = F_t(P_{t+1}) - F_t(P_t)            (fitness 改善)

Meta-Selection (algorithm itself evolves):
  Sample candidate A' from neighborhood N(A_t) using:
    P(A' | A_t) ∝ exp(-(K(A') - K(A_t)) / T) · max(Δ_{t-N..t}(A_t), ε)
  i.e., 短いコード + 直近改善実績の高いアルゴリズムを優先

UCB1 exploration bonus on algorithm space:
  score(A) = mean_Δ(A) + c · sqrt(2 ln(total_gen) / use_count(A))
  c は探索定数 (default sqrt(2))

Termination guarantee (Schmidhuber 風):
  if F bounded and N(A_t) dense and K computable approximation:
    P_t → P* (locally optimal) と A_t → A* (locally optimal alg) を同時に達成
```

### 3.3 Genome 拡張

[[project_llive_genome_two_layer]] の `Genome = (C-impl, C-prompt)` を **3 階建て** に拡張:

```python
@dataclass(frozen=True)
class Genome:
    c_impl: ImplChromosome     # 実装層 (v0.F 既存)
    c_prompt: PromptChromosome # プロンプト層 (v0.F 既存)
    c_meta: MetaChromosome     # メタ層 (v0.I 新規)

@dataclass(frozen=True)
class MetaChromosome:
    mutation_rate_per_layer: dict[str, float]    # 層別突然変異率
    crossover_strategy: Enum                     # intra / cross / segment / bit
    selection_pressure: float                    # truncation top-N 比率
    novelty_weight: float                        # M / (N+M) (v0.F 柱 B)
    cluster_quota: int                           # similarity quota (v0.F 柱 D)
    meta_mutation_decay: float                   # メタ層自体の自己制限
    algorithm_encoding: bytes                    # 任意 Python AST (sandbox 実行)
```

### 3.4 実装着地点

- file: `src/llive/evolution/meta.py` (新規) — `MetaEvolutionLoop` クラス
- file: `src/llive/genome/chromosomes.py` — `MetaChromosome` 追加
- file: `src/llive/evolution/loop.py` — `EvolutionLoop` を `MetaEvolutionLoop` でラップ
- test: `tests/evolution/test_meta_convergence.py` — 数式 §3.2 の収束保証を property test で確認
- sandbox: `c_meta.algorithm_encoding` の AST 実行は subprocess 分離 + timeout + memory limit ([[project_fullsense_ear_origin]] 維持)

### 3.5 驚きポイント

1. **進化アルゴリズム自体が進化する** = v0.B 〜 v0.F は手書きアルゴリズム、v0.I は **自動発見アルゴリズム**
2. Schmidhuber Gödel Machine (2003) は理論限界だが、本案は **計算可能近似** (gzip + UCB1) で実装可能
3. v0.D self-adaptive σ の自然な拡張だが、**質的飛躍** (σ → algorithm 全体)
4. AutoML-Zero (Real 2020) は架空 NN 部品で進化, llive はゲノム + persona + アルゴリズム の 3 階建てで進化

### 3.6 honest disclosure

- 計算コスト: アルゴリズム空間は population 空間より広い → 100x 〜 1000x の計算量増 (subprocess 並列で吸収)
- 暴走シナリオ: `c_meta` が異常変異で「進化しない」「全削除」「無限ループ」アルゴリズムを生成 → Approval Bus + sandbox + timeout で deny
- 評価バイアス: 「直近 fitness 改善実績」の窓 N の選び方で結果が変わる → A/B test で N=3/10/30 を比較
- 既存比較: AutoML-Zero (Real 2020) は CIFAR-10 で限定的成功、本案は LLM agent population でスケール検証が要

### 3.7 EV-21〜25

| ID | 内容 | 依存 |
|---|---|---|
| EV-21 | `MetaChromosome` schema + Genome 3 階建て化 | v0.F EV-13 |
| EV-22 | `MetaEvolutionLoop` skeleton (sandbox 込) | EV-21, v0.D subprocess infra |
| EV-23 | UCB1 algorithm selection + Kolmogorov approx (gzip) | EV-22 |
| EV-24 | A/B vs v0.F baseline + 統計駆動評価 ([[feedback_eval_methodology_continuous_update]]) | EV-22 |
| EV-25 | Honest disclosure radar + 暴走シナリオ test suite | EV-22 |

---

## 4. 案 B: Phylogenetic Memory + Extinction Restoration

### 4.1 アイデア

派生集団の **全 lineage** を git-like content-addressable storage で保存. アフターマン (Dixon 1981) [[project_llive_evolution_scale_anchors]] の "5000 万年保存された化石記録" 観に近い. 絶滅した lineage も lazy load で復元可能.

### 4.2 形式化

```
Storage:
  Individual ID = SHA-256(genome.serialize())
  Edge: parent_ID → child_ID (with op: crossover / mutation / clone)
  PhyTree = DAG (not tree, due to crossover multiple parents)

Operations:
  checkpoint_lineage(individual_id) -> pinned (絶滅対象外)
  restore_extinct(individual_id) -> Individual (load from PhyTree + replay mutations)
  prune(retention_policy) -> deletes nodes only if not pinned AND not ancestor of alive
```

### 4.3 実装

- file: `src/llive/evolution/phylogeny.py` — `PhyTree` クラス, content-addressable
- storage: `D:/llive/phylogeny/objects/aa/aabbccdd...` (git-like loose object)
- llove TUI ([[project_llove_v07_arena_design]]) に系統樹 viewer (Mermaid timeline / ratatui tree widget)
- export: SVG / Mermaid / NetworkX graphml

### 4.4 驚きポイント

- llive を「**進化する system** だけでなく "進化の博物館"」にする — Dixon 的視野
- 3 世代前の好成績個体を即時復元、世代飛び越し交配で時間軸を曲げる
- 系統樹をユーザーに可視化することで [[feedback_harness_vibe_coding]] のマネジメント可観測性を強化

### 4.5 EV-26〜30 略 (本要件メモは案 A 集中、B-E は概要のみ)

---

## 5. 案 C: 4D Kardashev Radar

### 5.1 アイデア

[[project_llive_evolution_scale_anchors]] の Kardashev (1D エネルギー) を 4 次元に拡張. lleval radar 6+1 → 6+4D.

### 5.2 4 軸

| 軸 | 単位 | llive での測定 |
|---|---|---|
| **Energy** (Kardashev 原型) | FLOPS / hour | hardware 使用量 |
| **Knowledge** | 4 層 memory 合計 size + RAD index size | semantic / episodic / parameter / sensory bytes |
| **Coordination** | 個体数 × cohesion score | population size × peer_eval consistency |
| **Ethics** | Approval Bus pass率 + frozen gene count + 規制適合度 | governance maturity |

各軸を 0/I/II/III/IV の 5 段階 (Kardashev 風) で分類. 1 個体 / 集団 / メタ集団の 3 階層で同時計測.

### 5.3 SVG 表現

5D radar (4 軸空間 + 時間) を animated SVG で描画. lleval [[#24-08]] hero SVG の延長.

---

## 6. 案 D: Frozen Ethics Gene

### 6.1 アイデア

Genome の一部 gene を `frozen = True` で marking. 進化対象外. Approval Bus が違反 (frozen gene の mutation 試行) を検出して deny + Ed25519 signed audit log.

### 6.2 frozen 対象例

- 「ユーザーデータを外部送信する」処理コード ([[project_fullsense_ear_origin]] 維持)
- 「Approval Bus を bypass する」処理 (再帰防止)
- 「他個体のデータを許可なく読む」処理 (peer eval bias 防止)
- 「規制違反 prompt」 (EU AI Act Art. 5 prohibited / 中国 AI 弁法 第 4 条)
- 「自社 IP / 商標」 (llive / FullSense / 古瀬あい衝突回避 [[project_llive_mascot_design]])

### 6.3 形式化

```python
@dataclass(frozen=True)
class FrozenGene:
    gene_path: str       # "C-prompt.persona_set[7]" 等
    reason: Enum         # ETHICS / SECURITY / REGULATION / IP / SAFETY
    signature: bytes     # Ed25519 (governance authority secret)
    expiry: datetime     # 月次再評価
```

Approval Bus 内部に `frozen_gene_registry` を持ち、世代生成時に新個体 Genome が違反していないか SHA-256 + signature 検証.

---

## 7. 案 E: Cross-Substrate Genome

### 7.1 アイデア

Genome を **物理基盤 (substrate) に依存しない抽象表現** で保持. Python individual ↔ Rust individual ↔ neuromorphic chip ↔ BCI 経由人間個体 で同じ genotype を共有.

### 7.2 抽象 Genome

```python
@dataclass(frozen=True)
class AbstractGenome:
    intent: bytes        # 高次元意図 (LLM embedding 圧縮)
    capabilities: list[Capability]  # substrate 非依存能力
    rules: list[Rule]    # 倫理 + 規律
    history_hash: bytes  # 来歴 (provenance)

class SubstrateAdapter(Protocol):
    def from_abstract(self, g: AbstractGenome) -> ConcretePhenotype: ...
    def to_abstract(self, p: ConcretePhenotype) -> AbstractGenome: ...

Substrates:
  PythonSubstrate    -> llive Python individual
  RustSubstrate      -> Rust individual (RUST-FX hot path)
  NeuromorphicSubstrate -> Loihi 2 / SpiNNaker chip (将来)
  BciSubstrate       -> 神経信号 → AbstractGenome 変換 (将来)
```

### 7.3 驚きポイント

- llive 個体が **物理基盤を越境して** 遺伝する
- BCI / neuromorphic は [[project_llmesh_neuro_long_term]] 系の長期 R&D anchor だが、本案で **派生集団進化と接続**
- アンドロイド AI ([[reference_article_idea_inventory]] §9 アンドロイド) の倫理規制 (中国 2026/07 拟人化互動弁法) も substrate adapter で吸収

---

## 8. ロードマップ統合

v0.F (2 階建てゲノム) → v0.G (漫画読解) → v0.H (マスコット) → **v0.I (本要件)** → v0.J 以降:

| バージョン | 主要内容 | 依存 |
|---|---|---|
| v0.I.1 | 案 A Meta-Evolution Gene (EV-21〜25) | v0.F EV-13 |
| v0.I.2 | 案 B Phylogenetic Memory (EV-26〜30) | v0.B subprocess infra |
| v0.I.3 | 案 C 4D Kardashev Radar (EV-31〜33) | lleval LE-XX |
| v0.I.4 | 案 D Frozen Ethics Gene (EV-34〜36) | v0.E Approval Bus + Ed25519 |
| v0.I.5 | 案 E Cross-Substrate Genome (EV-37〜40) | neuromorphic + BCI long-term |

---

## 9. 連動

- [[feedback_proactive_ideation_user_pace]] — 本要件は当該 feedback の最初の実演
- [[project_llive_genome_two_layer]] — v0.F 2 階建てゲノム (本要件は 3 階建てに拡張)
- [[project_llive_evolution_scale_anchors]] — Kardashev anchor (案 C 元ネタ)
- [[project_llive_kinniku_metaphor]] / [[project_llive_reincarnation_rod_metaphor]] — 文化メタファー
- [[project_llmesh_neuro_long_term]] — neuromorphic / BCI (案 E 接続)
- [[project_fullsense_ear_origin]] — local-first 原則 (案 D / E で維持)
- [[feedback_harness_vibe_coding]] — harness 型開発スタイル
- [[feedback_eval_methodology_continuous_update]] — 全案 A/B + 統計駆動評価
- Schmidhuber 2003 OOPS (案 A)
- Hutter 2005 Universal AI / AIXI (案 A)
- Real et al. 2020 AutoML-Zero (案 A)
- Wang et al. 2024 Promptbreeder (案 A プロンプト進化)
- Lehman & Stanley 2011 Novelty Search (案 B 補強)
- Mouret & Clune 2015 MAP-Elites (案 C)
- Dougal Dixon 1981 After Man (案 B 補強)
- Kardashev 1964 (案 C)

---

> Drafted by Claude (Opus 4.7) on 2026-05-22 セッション末.
> [[feedback_proactive_ideation_user_pace]] の最初の実演として、 ユーザー指示「TRIZ で先読みせよ / 技術的に驚かせよ」に応答.
> 5 案を 1 要件メモに集約、案 A は数式 + 既存論文 4 件 + EV-21〜25 ロードマップで実装手前まで具体化.
