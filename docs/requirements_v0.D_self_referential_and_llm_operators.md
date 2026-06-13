# llive 要件定義 v0.D — Self-Referential Mutation + LLM Operators

**Drafted:** 2026-05-21
**Status:** **要件追加 (新規)** — v0.C の上に重ねる. 公開研究との差別化軸を
明示する目的で追加.
**Type:** Evolutionary architecture — self-adaptive + LLM-as-operator
**Trigger:** 先行研究 survey
([`docs/research/llm_evolutionary_prior_art.md`](https://github.com/furuse-kazufumi/fullsense/blob/main/docs/research/llm_evolutionary_prior_art.md))
で **Promptbreeder / LMX / R2SAEA / EUREKA / MASPO** など 2023〜2026 の 9
件と比較した結果, llive v0.B/v0.C に組み込めば差別化軸を増やせる手法群を
要件として登録する.

---

## 0. 背景 — 先行研究 9 件との overlap

| 軸 | 状況 | 出典 |
|---|---|---|
| **集団 GA × LLM hyperparameter / prompt** | 先行 2 年以上 | EvoPrompt (2023-09) / Promptbreeder (2023-09) / FunSearch (Nature 2024) |
| **on-prem 集団 GA × 19 dim 数値 genome** | **類例見当たらず** | llive v0.C 独自 |
| **Self-referential mutation** (mutation 自体を進化) | Promptbreeder が先行. llive **未実装** | [arXiv:2309.16797](https://arxiv.org/abs/2309.16797) |
| **LLM-as-crossover-operator** (genome 自体が LLM の入力出力) | LMX が先行. llive **未実装** | [arXiv:2302.12170](https://arxiv.org/abs/2302.12170) |
| **LLM-as-surrogate** (expensive evaluation の置換) | R2SAEA が先行. llive **未実装** | [arXiv:2605.02933](https://arxiv.org/abs/2605.02933) |
| **Fitness function を LLM が code 生成** | EUREKA が先行. llive **未実装** | [arXiv:2310.12931](https://arxiv.org/abs/2310.12931) |
| **Multi-agent role-specific genome** | MASPO が直近. llive **未実装** | [arXiv:2605.06623](https://arxiv.org/abs/2605.06623) |

honest disclosure:「LLM × evolution の枠組み」自体は **先行多数**. llive
は **on-prem 限定 + 19 dim 数値 genome + subprocess transport** の 3 軸が
独自. v0.D で **self-referential + LLM-operator + LLM-surrogate** の 3 軸を
取り込み, 「on-prem で動く self-evolving LLM frame」として位置づけを強化する.

---

## 1. SR-FX (Self-Referential Mutation) — 優先度 HIGH

### SR-01: Mutation σ を genome dim に含める (self-adaptive ES)

**動機**: Promptbreeder は mutation prompt 自体を進化させる. これを **数値
genome 版** に置き換えると, 各次元の mutation σ も世代と共に最適化される
**self-adaptive evolution strategy (ES)** になる.

**実装**:

- 既存 19 dim genome を **38 dim** に拡張 (各次元の σ を末尾に同伴).
- `SelfAdaptiveGaussianMutation` (新規) — σ_i は genome[i+19] を読む.
- σ 自体の mutation は **log-normal** 推奨 (Schwefel 1981).
- `mutation.py` の `GaussianMutation` と並走 (既存 default は維持).

**テスト**:

- 38 dim genome で 30 世代回し, σ の世代推移を観察.
- 探索初期 (gen 0-5) は σ が高め, 収束期 (gen 20+) は σ が低めに**自動調整**
  されることを確認.
- baseline (固定 σ=0.1) と best score 比較.

**参照**: [Promptbreeder arXiv:2309.16797](https://arxiv.org/abs/2309.16797),
Hansen & Ostermeier (2001) CMA-ES.

### SR-02: Mutation 戦略選択を genome に含める (meta-mutation)

**動機**: mutation 種類 (Gaussian / Reset / Chained) を選ぶ meta-dim を
genome に含めることで, 「どんな mutation で進化するか」自体を進化させる.

**実装**:

- genome 末尾に `mutation_strategy_id` (0=Gauss / 1=Reset / 2=Blend) を追加.
- `MetaMutation` (新規) wrapper — 各 individual の strategy_id を読んで対応
  mutation を適用.

**テスト**:

- 3 戦略並走で世代後に **dominant strategy が収束する** ことを確認.
- 多様性枯渇しないか stat 取る.

---

## 2. LX-FX (LLM-as-Operator) — 優先度 MID (credential 後実装)

### LX-01: LMX 風 crossover (自然言語化 genome)

**動機**: LMX (Meyerson 2023) は few-shot prompting で **テキスト genome の
crossover** を LLM に任せる. llive で **思考因子 weight を自然言語化** すれば
LMX が直接効く.

**実装**:

- `LlivVariantConfig` に `narrative` フィールド追加 (factor 表現の自然言語版).
  - 例: `"This llive emphasizes 構造化 (0.7) over 探索 (0.3), uses anthropic
    backend with conservative temperature 0.4."`
- `LMXCrossover` (新規) — 親 2 体の narrative を LLM に few-shot prompt として
  渡し, 子の narrative を生成 → parser で genome 再構成.
- LLM backend は llive 標準 `LlmBackend` interface 経由 (`LLIVE_OPENAI_MODEL`
  env で切替可能).

**テスト**:

- 親 narrative 2 件で 1 回 LMX → 子 narrative が parser で genome 化できる.
- Mock LLM backend で deterministic な crossover 結果が出る (test 用).
- 数値 `SegmentCrossover` と並走時, **diversity と best score の trade-off**
  を比較.

**ガード**:

- credential が無い環境では `LMXCrossover` は **無効化** され `SegmentCrossover`
  に fallback ([[feedback-llive-measurement-purity]] 準拠).

### LX-02: LLM-as-fitness-function (EUREKA 風)

**動機**: EUREKA は RL の reward function を LLM が code 生成する. llive で
`mock_variant_fitness_factory` を **LLM が code として書く fitness 関数**に
置換すれば, タスク特化型の fitness が自動生成できる.

**実装**:

- `LLMFitnessGenerator` (新規) — タスク記述 (自然言語) + 既存 fitness
  signature を LLM に渡し, Python code を生成 → exec して fitness 関数化.
- 生成 code は **SHA-256 で identity 固定** + **Approval Bus 経由でユーザー
  承認**してから採用 ([[project-approval-bus]] 準拠, governance 重要).
- 1 世代に 1 回 fitness 関数を再生成 (EUREKA の reward reflection に相当).

**安全要件**:

- 生成 code は `restricted_exec` sandbox 内で実行.
- 通常 fitness 軸 (latency / quality / stability / safety / honesty) は
  fallback として常駐.
- LLM 生成 fitness が baseline より N% 改善しない場合は採用しない (Approval).

**参照**: [EUREKA arXiv:2310.12931](https://arxiv.org/abs/2310.12931).

---

## 3. SU-FX (LLM-as-Surrogate) — 優先度 MID (credential 後実装)

### SU-01: LLM surrogate model で expensive evaluation を置換

**動機**: 実 LlivKernel 評価が 1 体 5 分 × 30 体 × 30 世代 = 75 時間.
R2SAEA (2026-04) は LLM (Qwen2.5 + GRPO) を **pairwise relation surrogate**
として使い prompt complexity を O(n²) → O(n) に削減.

**実装**:

- `LLMRelationSurrogate` (新規) — 親 pairing で 2 個体 → "A > B" / "B > A" /
  "tie" の LLM 判定.
- 過去世代の真値 fitness を **anchor** として in-context に与える.
- evolution loop で 1 世代の真値評価を N=5 体に抑え, 残り 25 体は surrogate
  で順位推定.

**テスト**:

- mock LLM surrogate (実 LLM 不要の deterministic version) で end-to-end 動作.
- 真値 30 体評価 (baseline) と LLM-surrogate 5 体評価で best score を比較.

**参照**: [R2SAEA arXiv:2605.02933](https://arxiv.org/abs/2605.02933).

---

## 4. MR-FX (Multi-Role Genome) — 優先度 LOW

### MR-01: 役割固有 genome (MASPO 風)

**動機**: MASPO (2026-05) は LLM-based multi-agent system で **役割固有の
prompt** を joint 最適化. llive 集団を **役割集団** として扱う拡張.

**実装** (将来):

- 集団を 3-5 roles に分割 (例: Explorer / Exploiter / Verifier / Critic /
  Refiner).
- 各 role に専用 genome dim subset を割り当て (例: Explorer は探索因子重視,
  Verifier は整合因子重視).
- 役割間の crossover は段別 (role-specific) + 段越え (cross-role) のミックス.

**位置づけ**:

- これは llive の **multi-llive collaboration** 構想と連動する大規模変更.
- v0.D Phase 1 では **要件登録のみ** で着手しない.

**参照**: [MASPO arXiv:2605.06623](https://arxiv.org/abs/2605.06623).

---

## 5. PLAN (Phase ごと)

| Phase | 含まれる項目 | 前提 |
|---|---|---|
| **D.1** | SR-01 (self-adaptive σ) | credential 不要, 着手可能 |
| **D.2** | SR-02 (meta-mutation strategy) | D.1 後 |
| **D.3** | LX-01 (LMX crossover, narrative 化) | credential 復旧 |
| **D.4** | LX-02 (LLM-as-fitness, EUREKA) | credential + Approval Bus 統合 |
| **D.5** | SU-01 (LLM-surrogate) | credential + 真値 anchor データセット |
| **D.6** | MR-01 (multi-role genome) | v0.E 候補に格上げ可 |

D.1〜D.2 は **今セッション以降の通常開発で消化可能** (mock baseline で全
test 通せる). D.3〜D.5 は **credential 復旧待ち**. D.6 は構想.

---

## 6. 差別化の言語化

**llive v0.D 以降の主張**:

> 「LLM × evolutionary algorithm の枠組みは 2023 以降に複数の DeepMind /
> Microsoft / NVIDIA 研究で先行している. llive は (1) **on-prem 限定で**
> 集団進化を実装し, (2) **19 dim 数値 genome + subprocess transport** で
> production-ready な実装パターンを提供し, (3) **honest disclosure 5+1 因子
> 分解** で結果の透明性を担保する. v0.D で **self-referential mutation
> (Promptbreeder)** と **LLM-operator (LMX)** を取り込み, 「on-prem で動く
> self-evolving LLM frame」として位置づける.」

これは [[feedback-benchmark-honest-disclosure]] の精神に沿う立場宣言.
「枠組みの発明」を主張せず, **「on-prem 実装パターン」を差別化軸**にする.

---

## 7. References

### 直接根拠

- [`docs/research/llm_evolutionary_prior_art.md`](https://github.com/furuse-kazufumi/fullsense/blob/main/docs/research/llm_evolutionary_prior_art.md) (fullsense portal) — Survey 本体
- Meyerson, E. et al. (2023). [LMX: Language Model Crossover](https://arxiv.org/abs/2302.12170).
- Fernando, C. et al. (2023). [Promptbreeder](https://arxiv.org/abs/2309.16797).
- Ma, Y. et al. (2023). [EUREKA](https://arxiv.org/abs/2310.12931).
- Lu, Y. et al. (2026). [R2SAEA](https://arxiv.org/abs/2605.02933).
- Wang, Z. et al. (2026). [MASPO](https://arxiv.org/abs/2605.06623).
- Survey: [arXiv:2509.08269](https://arxiv.org/html/2509.08269v1) (2026-09)

### llive 内部 cross-reference

- `docs/requirements_v0.B_evolutionary_optimization.md` — v0.B 本体
- `docs/requirements_v0.C_llive_variant_evolution.md` — v0.C (1 llive = 1 個体)
- `src/llive/perf/evolutionary/llive_variant.py` — 19 dim genome 実装
- `src/llive/perf/evolutionary/subprocess_scheduler.py` — v0.C Phase 2 着地 (2026-05-21)
- `src/llive/perf/evolutionary/mutation.py` — SR-01 / SR-02 拡張先

### 関連 maintainer memory

- [[feedback-llive-measurement-purity]] — on-prem 限定の測定純度
- [[feedback-benchmark-honest-disclosure]] — 異常に良い結果は内訳を疑う
- [[feedback-rad-rag-confusion]] — RAD コーパス vs RAG vs RAD₂
- [[project-llive-v0B-evolutionary]] — v0.B 本体
