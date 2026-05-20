# llive 要件定義 v0.B — 進化型最適化レイヤ (Evolutionary Optimization)

**Drafted:** 2026-05-21
**Status:** **要件追加** (Phase 1 skeleton と同セッションで着手)
**Type:** Performance / optimization layer addendum
**Trigger:** ユーザー指摘 (2026-05-21) —

> 「収束型のアルゴリズム適用と, その評価指標が揃ったなら, 収束型アルゴリズムに
> ある程度のランダム性を持たせて, 可能な限り並列で同時に大量に走らせて, 特定の
> 入力を繰り返した後, 評価を行い優秀なものを選別という作業を繰り返してほしい」
>
> 「進化における生存と淘汰の繰り返しのようなことをやりたい」
>
> 「ROS 上で大量に仮想ロボットにランダムなアルゴリズムで歩行させて, 一番動きが
> 安定している数体を残して, それらの子を増やしてからまた同じことを繰り返す
> ような方法 — それの AI 版」

---

## 1. 動機 — 収束型 (UCB) vs 進化型 (GA)

### 既存 (本セッション B-0〜B-9 で確立)

- `SynapticSelector` (ε-greedy + Hebbian weight)
- `UCBSynapticSelector` (UCB1 で公平 exploration)
- `StrategyVariant` (impl + weight + bounds)
- 各 variant の latency_ms / quality 観測
- bounded modification (§E2) で weight min/max clip

**現状の限界**: UCB は **1 個体の内側で variant を選ぶ** ところまで. variant
自体の **hyperparameter** (例: ε, lr, decay, threshold) は人手で決め打ち.
ロボット歩行で例えると「**1 体のロボットが歩き方を学ぶ**」段階.

### v0.B が解く問題

**集団全体で進化** させる. variant 自体の hyperparameter / 構造を遺伝子と
見立てて, 「**N 体のロボットを並列に歩かせて, 上位を残し, 交配 + 突然変異
で次世代を作る**」を回す.

| 軸 | UCB (収束型) | GA (進化型) |
|---|---|---|
| 個体数 | 1 | **N (10〜10000)** |
| 探索対象 | variant id (有限離散) | hyperparameter vector / variant 構造 (連続 or 構造的) |
| 適応スピード | 1 セッション内 | 世代 (複数セッション) |
| 局所最適脱出 | exploration round 依存 (B-4 で観測した bias リスク) | crossover + mutation で構造的に脱出 |
| 並列性 | weight 共有のため一系統 | **embarrassingly parallel** (個体 fitness 評価が独立) |
| 評価コスト | 低 (1 個体) | 高 (N 個体 × 同入力) |

両層は **直交** で組み合わせ可能:

- **進化型** が hyperparameter を grid 探索しつつ
- **収束型** が各個体の内側で variant 選択を最適化

これにより, B-4 で観測した「ε-greedy が一極集中で真の最良に行かない」病理が,
**集団多様性** によってさらに緩和される.

---

## 2. 用語 (ROS 歩行進化との対応)

| ロボット歩行進化 | llive v0.B |
|---|---|
| 仮想ロボット 1 体 | `Individual` (1 個体) |
| 関節パラメータ (脚 角度 / 周期 / 重心) | `Genome` (実数ベクトル + bounds) |
| 仮想ロボット 100 体 | `Population` |
| 歩行距離 / 転倒回数 / 消費エネルギー | `Fitness` (latency / quality / cost の合成) |
| 上位 N 体を残す | `Selection` (tournament / elitism) |
| 親 2 体から子を作る | `Crossover` (uniform / blend / SBX) |
| 突然変異で新パターン | `Mutation` (gaussian / reset / boundary) |
| 1 世代 | `Generation` |
| 進化を回す全体 | `EvolutionLoop` |
| 100 体を並列に走らせる | `Scheduler` (multiprocessing.Pool / asyncio) |
| 進化記録 | `Reporter` (世代 × {best / mean / std / diversity}) |

---

## 3. 要件 (EV-FX 系列)

### EV-01 (must) — Genome / Individual / Population

- `Genome` = 実数ベクトル + per-dim bounds. JSON 化可能.
- `Individual` = `Genome` + history (世代ごとの fitness 履歴) + uuid.
- `Population` = `list[Individual]` + 世代番号 + RNG seed + best/mean/std summary.
- 全 dataclass は `@dataclass(frozen=True)` または `to_dict / from_dict` で
  serialize/deserialize 可能.
- thread-safe (RLock) — 並列評価で aggregate するため.

### EV-02 (must) — Fitness 関数の抽象

- `Fitness = Callable[[Genome, RuntimeMetadata], FitnessReport]` 型.
- `FitnessReport` = `{score: float, breakdown: dict[str, float], runtime_metadata: ...}`.
- 既存の `runtime_metadata.RuntimeMetadata` (v0.A) を **すべての fitness 評価
  に同梱必須** — 公開ベンチ整合性を維持 ([[feedback-benchmark-honest-disclosure]]).

### EV-03 (must) — Selection

- v0.B で実装する 3 種 (default = tournament k=3):
  - `TournamentSelection(k=3)` — k 体 random pick → best 1 体を親に
  - `ElitismSelection(top_n)` — 上位 N 体を直接次世代へコピー
  - `RouletteSelection(temperature)` — fitness 比例ルーレット

### EV-04 (must) — Crossover

- v0.B で実装する 2 種 (default = uniform):
  - `UniformCrossover(p=0.5)` — 各 dim 独立に親 A/B からサンプル
  - `BlendCrossover(alpha=0.5)` — 親値の線形補間 + α 拡張
- 将来候補: `SBX` (Simulated Binary Crossover) — 連続パラメータで GA 標準

### EV-05 (must) — Mutation

- v0.B で実装する 2 種:
  - `GaussianMutation(sigma=0.1, p=0.05)` — N(0, σ) を p の確率で加算
  - `ResetMutation(p=0.01)` — 1% の確率で完全 reset (bounds 内 uniform)
- すべての mutation は bounds で clip (`bounded modification §E2` 整合).

### EV-06 (must) — EvolutionLoop

- 1 世代 = evaluate → select → breed (crossover + mutation) → 次世代生成.
- 終了条件: max_generations / best_fitness 停滞 (patience 世代) / 多様性閾値.
- per-generation の checkpoint (JSONL) — 落ちても復元可能.
- random seed を **世代単位** で記録 (再現性).

### EV-07 (should) — Scheduler (並列実行)

- v0.B Phase 3 で並列化:
  - `SerialScheduler` (default, Phase 1-2 で使う) — pytest 安定
  - `MultiprocessingScheduler(n_workers=cpu_count)` — CPU-bound fitness で
    線形スケール期待
  - `AsyncioScheduler` — I/O-bound (LLM API) fitness 用. credential 復旧後.
- scheduler 切替は env / config で. fitness 関数は **picklable** が前提
  (multiprocessing 制約).

### EV-08 (should) — Reporter

- 世代ごとに以下を記録:
  - best/mean/std fitness
  - genome diversity (pairwise L2 mean) — 多様性枯渇を検出
  - elapsed time / wall clock
  - random seed
- 出力先: `out/evolution_<run_id>/generations.jsonl`, `summary.md`,
  `convergence.png` (matplotlib optional extra).

### EV-09 (could) — 既存 SynapticSelector 連携

- `Individual.genome` が UCB selector の hyperparameter (ε, lr, c) を含む場合,
  fitness 評価内で **UCB selector を spawn して実 variants を回す**.
- これにより 「**個体 = UCB selector の hyperparameter 一式**」が進化対象に.

### EV-10 (could) — 階層 GA / island model

- 集団を islands に分けて, 一定世代ごとに migration. 局所最適脱出に強い.
- v0.B Phase 4 以降の候補.

### EV-11 (could) — Coevolution

- 2 集団を相互に評価 (例: prompt generator vs judge). 防衛的進化.
- v1.x 候補.

---

## 4. 非要件 (Out of scope, v0.B)

- **neural architecture search (NAS)** — Genome を「ネットワーク構造」にする話は別 vertical
- **強化学習との fusion (PPO etc)** — 別 vertical (v0.C 候補)
- **分散実行 (Ray, Dask)** — multiprocessing で十分回らなければ検討
- **GUI** — Reporter の出力を grep で読めれば良い

---

## 5. 段階 (Phase 1 → 4)

| Phase | 内容 | 同セッション着手? |
|---|---|---|
| 1 | Genome / Individual / Population dataclass + 単体テスト | **本セッション** |
| 2 | Selection / Crossover / Mutation + EvolutionLoop (serial) + toy fitness test | **本セッション** |
| 3 | MultiprocessingScheduler + AsyncioScheduler + 再現性検証 | 次セッション |
| 4 | 既存 SynapticSelector 連携 (EV-09) + 実 LLM fitness (credential 復旧後) | credential 復旧後 |

---

## 6. 既存資産との接続点

| v0.B コンポーネント | 既存資産 | 接続方法 |
|---|---|---|
| `Fitness` | `SynapticSelector` の `latency_ms / quality` | individual 評価時に内部で UCB を spawn |
| `Reporter` | `runtime_metadata` (v0.A) | 6 metadata を全 generation に持たせる |
| `Population` | bounded modification (§E2) | clip を mutation/crossover で踏襲 |
| `Scheduler` | `governance` (Approval Bus) | 危険操作の自動評価は govern 経由 |
| 全体 | `feedback_benchmark_honest_disclosure` | 異常値 fitness は内訳分解必須 |

---

## 7. 設計判断

### D-1. 進化型 ON は環境変数 + config 経由のみ

production 実コードに進化型ループが暗黙混入することを避ける.
`LLIVE_EV_ENABLED=1` を必要とする. 既存 hot path は **B-9 注入のまま** 進化型
ではない.

### D-2. Determinism は seed 制御で確保

各 generation の RNG seed を `Generation` に保存. 再現実行で同 trajectory
を再現できる. 並列実行時は per-individual に sub-seed を派生.

### D-3. 進化型結果の bench publish には Honest Disclosure 必須

「進化で X 倍速くなった」を公開する前に必ず 5+1 因子分解
(v0.A の 6 metadata + lleval LE-03 の 5 因子) を bench に同梱.

### D-4. dependencies は **stdlib + numpy + dataclasses 縛り**

`deap` / `pymoo` 等の OSS は既存だが, **add しない**. 教育性 + 自前理解 +
依存ゼロ. 性能不足が確認されたら検討.

---

## 8. リスク

| リスク | 影響 | 緩和 |
|---|---|---|
| 並列 fitness 評価で memory leak | 長時間 run で OOM | per-generation で worker pool 再起動 |
| seed 不揃いで結果再現不能 | bench 怪しい | per-generation seed JSONL に必ず記録 |
| 多様性枯渇 (premature convergence) | 局所最適 | diversity 監視 + reset mutation 強化 |
| fitness が non-deterministic (LLM API) | 同 genome で異なる score | N 回平均 + 信頼区間も記録 |
| LLM 評価コスト発散 | credential 消費 | mock fitness の比率を default 高めに |

---

## 9. 関連

- [[feedback-benchmark-honest-disclosure]]
- [[feedback-benchmark-progressive-tokens]]
- [[feedback-llive-measurement-purity]]
- [[project-llive-core-optimization-2026-05-20]] (B-0〜B-9 の収束型)
- llive `docs/requirements_v0.A_external_runtime_tracking.md`
- llive `src/llive/perf/synaptic_selector.py` (`UCBSynapticSelector`)
- portal `docs/spec/lleval_v0_1_implementation_notes.md` (LE-02 progressive size matrix と相性)
- 比喩元: ROS 仮想ロボット歩行進化 (e.g. NEAT, ES, CMA-ES の論文系)
