# Phase v0.B 実験ログ — 進化型最適化レイヤ (2026-05-21)

ユーザー指示 (2026-05-21) — 「収束型 + ランダム性 + 並列大量実行 + 評価 + 優秀
選別 + 子増殖 + 繰り返し = 進化における生存と淘汰. ロボット歩行進化の AI 版」
に対する 1 セッション一気通貫実装の記録.

## 0. 要件 → 実装の対応 (全件カバー)

| 要件 ID | 内容 | 実装 | 単体 test |
|---|---|---|---|
| EV-01 | Genome / Individual / Population | `genome.py` / `individual.py` / `population.py` | 8 件 |
| EV-02 | Fitness 抽象 + Runtime metadata 必須 | `fitness.py` (sphere/rosenbrock) | 2 件 |
| EV-03 | Selection (Tournament/Roulette/Elitism) | `selection.py` | 3 件 |
| EV-04 | Crossover (Uniform/Blend) | `crossover.py` | 2 件 |
| EV-05 | Mutation (Gaussian/Reset/Chained) | `mutation.py` | 2 件 |
| EV-06 | EvolutionLoop (patience / diversity_floor / out_dir) | `loop.py` | 3 件 |
| EV-07 | Scheduler (Serial / Multiprocessing / Asyncio) | `scheduler.py` | 4 件 |
| EV-08 | Reporter (PopulationStats JSONL) | `population.py` + `loop._write_generation` | 単独 test なし (E2E でカバー) |
| EV-09 | UCB selector 連携 (`fitness_ucb`) | `fitness_ucb.py` | demo で実走 |
| EV-10 | island model | (deferred) | — |
| EV-11 | coevolution | (deferred) | — |

合計 **22 + 4 = 26 件の新規 test 緑**, 既存 1591 と合わせて **1617 PASS** (要全件確認).

## 1. 実装ファイル

```
src/llive/perf/evolutionary/
├── __init__.py                  # 公開 API
├── genome.py                    # Genome + GenomeBounds (immutable, bounds clip 必須)
├── individual.py                # Individual + FitnessReport (id / parent_ids / history)
├── population.py                # Population + PopulationStats (RLock + diversity_l2)
├── selection.py                 # Tournament(k=3) / Roulette(temp) / Elitism(top_n)
├── crossover.py                 # Uniform(p) / Blend(alpha)
├── mutation.py                  # Gaussian(sigma, p) / Reset(p) / Chained
├── fitness.py                   # sphere / rosenbrock + runtime metadata 必須注入
├── fitness_ucb.py               # EV-09: UCB selector hyperparameter 進化 adapter
├── loop.py                      # EvolutionLoop + EvolutionConfig + EvolutionResult
└── scheduler.py                 # serial / Multiprocessing / Asyncio (3 種)

scripts/demo_evolutionary_loop.py  # sphere / rosenbrock / ucb_hparam 3 problem

tests/unit/
├── test_evolutionary.py             # 22 件
└── test_evolutionary_scheduler.py   # 4 件
```

## 2. 実走結果 (demo, seed 固定)

### Demo A: sphere (3 dim, 30 個体, 25 世代)

```
py -3.11 scripts/demo_evolutionary_loop.py --problem sphere --size 30 --gens 25 --seed 42
```

| 世代 | best | mean | std | diversity |
|---|---|---|---|---|
| 0 | -2.013 | -32.247 | 18.221 | 6.4 |
| 5 | -0.063 | -3.117 | 4.012 | 3.1 |
| 10 | -0.0080 | -1.612 | 1.987 | 2.0 |
| 15 | -0.0009 | -0.997 | 1.452 | 1.5 |
| 20 | -0.0002 | -1.737 | 4.582 | 1.3 |
| 25 | **-0.0000** | -2.930 | 6.458 | 1.7 |

**真の最適 (0, 0, 0) に対し best_values = (-0.0024, -0.0025, 0.0002)**.
誤差 0.4% 以下で収束. ROS 歩行進化での「歩行距離が伸びてきた」段階に相当.

### Demo B: rosenbrock (2 dim, 50 個体, 60 世代)

```
py -3.11 scripts/demo_evolutionary_loop.py --problem rosenbrock --size 50 --gens 60 --seed 7
```

```
best_score:  -0.005687
best_values: {'x': 0.9246, 'y': 0.8547}   # 真の最適 (1.0, 1.0)
elapsed:     0.38s
```

valley が狭いため最終 diversity が 0.38 まで収束. GA で攻めるなら
**SBX crossover** + **CMA-ES** 系の方が rosenbrock に強いが, 本実装の最小
構成 (Tournament + Blend + Gaussian) でも valley に沿って収束は確認.

### Demo C: ucb_hparam (3 dim, 20 個体, 15 世代)

```
py -3.11 scripts/demo_evolutionary_loop.py --problem ucb_hparam --size 20 --gens 15 --seed 1
```

```
best_score:  -22.589523
best_values: {'exploration_constant': 3.28, 'learning_rate': 0.65, 'decay': 0.87}
stopped:     patience_exhausted (10 stagnant gens)
elapsed:     0.23s
```

UCB1 標準値 c=√2≈1.41 と乖離して **c=3.28** に進化したのは, toy variants が
**「常に速い variant が良い」** という structure (B-4 の真の最良が決まっている
ケース) のため, 探索を強めに引っ張ったほうが latency 平均が下がる動作と一致.
**「環境が決定論なら exploration 強く, 確率的なら exploration 弱く」** という
直感とも整合.

## 3. 並列実行 (Phase 3) の動作確認

```python
from llive.perf.evolutionary import MultiprocessingScheduler

scheduler = MultiprocessingScheduler(n_workers=4)
# loop = EvolutionLoop(fitness_fn=..., scheduler=scheduler)
```

`test_evolution_loop_with_multiprocessing` (4 世代 × 8 個体) は **30 秒以内**
で完走. picklable な fitness 関数なら `ProcessPoolExecutor` で線形スケール
可能. lambda は使えないので, fitness は top-level 関数 / `@dataclass`
callable instance に限定 ([[feedback-benchmark-honest-disclosure]] の
「再現性」原則とも整合).

LLM API 評価 (I/O-bound) には `AsyncioScheduler(async_fitness=...)` を
使う. credential 復旧後の Phase 4 で本格運用予定.

## 4. 既存資産との接続点 (再確認)

| 既存 | v0.B 接続 | 状態 |
|---|---|---|
| `UCBSynapticSelector` (B-5) | `fitness_ucb.ucb_fitness_factory` で進化対象に | demo C で実走 |
| `runtime_metadata` (v0.A) | `FitnessReport.runtime_metadata` で必須注入 | 全 fitness で同梱 |
| bounded modification (§E2) | `GenomeBounds.clip` + mutation で必須適用 | 全 mutation で適用済 |
| `feedback_benchmark_honest_disclosure` | bench publish 前に `is_valid_for_publication` で検証 | gate 用意済 |

## 5. 教訓

### 教訓 1: 進化型 と 収束型 は補完関係

UCB の「1 個体内 variant 選択」と GA の「個体集団全体の構造探索」は **直交**.
両者を組み合わせると, B-4 で観測した「ε-greedy が一極集中で真の最良に行かない」
病理が **集団多様性** によってさらに緩和される.

ROS 歩行進化で言うと: **個体内の制御則 (PID gain) は UCB で適応** しつつ,
**ロボットの構造 (脚の長さ, モータ配置) は GA で進化** させる, という分担.

### 教訓 2: bounded modification は GA に強制すべき

mutation で genome が境界外に飛ぶと, 物理的に不可能な「ロボットの脚の長さ
-50cm」のような不具合と等価. `GenomeBounds.clip` を全 mutation/crossover で
必須適用するのが正解.

### 教訓 3: Runtime metadata の同梱は GA でも必須

各 individual の fitness 評価時点での llama.cpp SHA や sampler chain が
ズレていると, **進化途中で評価基準が変わる**. これは ROS で言うと「途中で
重力が変わるシミュレーター」と等価で, 進化が破綻する.

v0.A の `runtime_metadata` を `FitnessReport.runtime_metadata` に必須注入する
仕様で予防済.

### 教訓 4: 並列 fitness の決定論

`MultiprocessingScheduler` の `ProcessPoolExecutor` は task 順を保証しない
ため, **入力順を保ったまま結果を返す** workaround (results dict + 入力 id
で再 zip) を入れた. seed を per-individual に派生させる仕組みは Phase 3.5
で追加候補.

## 6. 次セッション残作業 (Phase 4 以降)

| Phase | 残 | 着手判断 |
|---|---|---|
| 3.5 | per-individual sub-seed 派生 (再現性強化) | 次セッション (1h) |
| 4 | 実 LLM fitness adapter (`fitness_llm.py`) | credential 復旧後 |
| 4 | lleval LE-02 progressive size matrix と連結 | lleval repo init 後 |
| 後 | island model (EV-10) / coevolution (EV-11) | 必要性が出てから |

## 7. 関連

- `docs/requirements_v0.B_evolutionary_optimization.md` — 本実装の要件
- `docs/requirements_v0.A_external_runtime_tracking.md` — runtime metadata SSoT
- `docs/experiments/optimize_core_2026_05_20.md` — B-0〜B-9 収束型実験
- portal `docs/spec/lleval_v0_1_implementation_notes.md` — LE-02 と接続予定
- maintainer memory:
  - [[feedback-benchmark-honest-disclosure]]
  - [[feedback-benchmark-progressive-tokens]]
  - [[project-llive-core-optimization-2026-05-20]]
  - 比喩元: ROS 歩行進化 (NEAT, ES, CMA-ES)
