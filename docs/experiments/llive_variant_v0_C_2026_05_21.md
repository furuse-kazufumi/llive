# v0.C 実験 log — llive 派生集団進化 (2026-05-21)

ユーザー指示 (2026-05-21):

> 「完全に同時でなくても, 多くのランダムな llive 派生を作って比較の上で
> 取捨選択していく形を取りたい」
> 「進化形態として多様性を持ちながらゲノム交配のような要素があれば組み込めると」
> 「ある程度進化には個体数が必要なので, それを今の環境で行おうとすると少し
> 時間がかかる」
> 「準備が大事」

→ **「1 llive = 1 個体」と見て集団化** + **染色体単位の交配 (SegmentCrossover)**
+ **大規模集団 + 長時間運用に必要な checkpoint / resume / 時間予算** を 1
セッションで全件着地.

## 0. 要件 → 実装の対応

| 要件 ID | 内容 | 実装 |
|---|---|---|
| LV-01 | LlivVariantGenome (19 dim) + bounds + labels | `llive_variant.py` |
| LV-02 | LlivVariantBuilder (Genome → Config) | 同上 |
| LV-03 | mock variant fitness (8 軸合成) | `mock_variant_fitness_factory` |
| LV-04 | SegmentedScheduler (1 segment ずつ serial) | 同上 |
| LV-05 | 派生間隔離 (data_dir 紐付け skeleton) | LlivVariantConfig.data_dir |
| LV-06 | Reporter 拡張 (variant_id 同梱) | breakdown / notes |
| LV-07 | runtime_metadata 6 SHA 同梱 | mock_variant_fitness 内 |
| (大規模) | checkpoint / resume / 時間予算 | `EvolutionConfig` + `_resume_from_snapshot` |
| (ゲノム交配) | SegmentCrossover (5 chromosome) | `crossover.py` 拡張 |

合計 **+19 件の新規 test 緑** (`test_evolutionary_llive_variant.py` 13 +
`test_evolutionary_checkpoint.py` 6).

## 1. Genome レイアウト (19 dim, 5 chromosome)

```
[0..10)   思考因子 weight (10 dim)
            構造化 / 再構成 / 閉ループ / 自己拡張 / 不確実性 /
            探索 / 整合 / 来歴 / 多視点 / 現実接続

[10..13)  memory tier (3 dim)
            semantic_threshold / episodic_threshold / structural_decay

[13..14)  backend (1 dim)
            backend_id ∈ {mock, openai, anthropic, mamba, rwkv}

[14..17)  sampler (3 dim)
            temperature / top_p / kv_quant_id

[17..19)  proactive (2 dim)
            gift_value_threshold / cooldown_minutes
```

これを **5 segment** に分けて `SegmentCrossover` に渡す:

```python
LIVE_VARIANT_SEGMENTS = (
    (0, 10),   # 思考因子 chromosome
    (10, 13),  # memory chromosome
    (13, 14),  # backend chromosome
    (14, 17),  # sampler chromosome
    (17, 19),  # proactive chromosome
)
```

「**生物的な gene segment swap**」を実装した形. 親 A / B から segment 単位で
独立に選ぶため, dim 単位の uniform crossover より **粗い粒度** で多様性を
維持できる.

## 2. 実走結果 — llive_variant demo (30 個体 × 12 世代)

```
py -3.11 scripts/demo_evolutionary_loop.py --problem llive_variant --size 30 --gens 12 --seed 42
```

世代推移 (best / mean / std / diversity):

| 世代 | best | mean | std | diversity |
|---|---|---|---|---|
| 0 | 0.5358 | 0.6420 | 0.0440 | 14.40 |
| 3 | 0.7080 | 0.6878 | 0.0205 | 12.84 |
| 6 | 0.7278 | 0.7058 | 0.0161 | 8.81 |
| 9 | 0.7421 | 0.7252 | 0.0126 | 7.69 |
| 12 | **0.7514** | 0.7327 | 0.0142 | 8.28 |

12 世代で best **0.5358 → 0.7514** に向上 (+40%), 多様性は 8.28 を維持
(diversity_floor 1e-6 に対し 8 桁余裕あり, 枯渇していない).

**best individual (Genome 値, 抜粋)**:

```
factor_provenance:   1.000  (来歴は最大)
factor_consistency:  0.914
factor_uncertainty:  0.886
factor_exploration:  0.752
semantic_threshold:  0.509  (中庸)
backend_id:          2.15  → "anthropic"
temperature:         0.77
gift_value_threshold: 0.609
cooldown_minutes:    29.8  (≈ default 30 分)
```

→ mock fitness の **factor_coverage** (中庸+均整) と **memory_efficiency**
(threshold が極端でない) で point を稼ぐ構成に収束. 実 backend で評価すると
backend_id がどう動くか変わる可能性大.

## 3. 大規模集団 + 長時間運用への準備

ユーザー指摘「個体数が必要で時間がかかる」「準備が大事」を踏まえて以下を
**1 セッション内に**確立:

### 3.1 checkpoint (世代ごと snapshot)

```python
config = EvolutionConfig(
    max_generations=30,
    checkpoint_every=1,           # 全世代で snapshot
    out_dir=Path("out/llive_variant_run1"),
)
```

→ `out/llive_variant_run1/snapshot_gen_NNNN.json` が毎世代書かれる.
`generations.jsonl` に 1 世代 1 行で stats も append.

### 3.2 resume (前回 snapshot から再開)

```python
config = EvolutionConfig(
    max_generations=60,
    out_dir=Path("out/llive_variant_run2"),
    resume_from=Path("out/llive_variant_run1"),  # dir 指定 → 最新 snapshot
)
```

→ `_resume_from_snapshot` が最新 `snapshot_gen_*.json` を自動選択して
`population` を上書き. **セッション中断 → 再開で世代を引き継げる**.

これにより「**1 個体 5 分 × 50 体 × 30 世代 = 75000 分 ≈ 52 日**」のような
長時間運用でも, **セッション切れごとに resume** で世代を進められる.

### 3.3 時間予算 (wallclock budget)

```python
config = EvolutionConfig(
    max_generations=1000,         # 大きく
    max_wallclock_seconds=3600.0, # 1 時間で safely 停止
)
```

→ `stopped_reason="wallclock_budget_exhausted (3600.1s / 3600.0s)"`.

「1 時間だけ進化を回す」みたいな運用が可能. セッション内で安全な停止
ポイントを保証する.

### 3.4 SegmentedScheduler

```python
loop = EvolutionLoop(
    fitness_fn=mock_variant_fitness_factory(),
    scheduler=SegmentedScheduler(segment_size=10, grace_sec=2.0),
)
```

→ 集団 50 体を 5 segment (10 体ずつ) で serial 評価, segment 間で 2 秒
sleep. 並列スループットは下がるが, **派生間干渉を物理的に避けられる**.

`feedback_quiet_hours` (22-8 JST で能動発話抑制) との相性が良い: grace_sec
を伸ばすと深夜帯に CPU を free にできる.

## 4. 教訓 (v0.C から 3 つ)

### 教訓 1: 染色体単位の交配は多様性に寄与する

`SegmentCrossover(segments=LIVE_VARIANT_SEGMENTS, p=0.5)` で 12 世代後の
diversity が **8.28** を維持. `UniformCrossover(p=0.5)` だと dim 単位で
均化が進み diversity がより早く落ちる (B-2/B-6 で観察済).

「**生物の染色体ペア交叉**」と同じ粗さで混ぜることが, GA の多様性維持に
直接効く. これは AutoML 系の文献でも知られた性質を実装で再現できた.

### 教訓 2: checkpoint + resume があると「長時間 GA は普通の運用」

実 llive 派生評価が 1 体 5 分かかっても, **セッションを跨いで世代を進める**
だけで進化は止まらない. これは「並列でないと現実的でない」という GA の
常識を覆す: **serial でも checkpoint + resume があれば 50 日でも 1 年でも
回せる**.

ユーザーの「完全に同時でなくても」+ 「準備が大事」がこの教訓に直結する.

### 教訓 3: 19 dim でも収束は十分速い

「19 dim genome は探索空間が広すぎる」という懸念があったが, 30 個体 × 12
世代 (= **360 評価**) で +40% の改善が得られた. これは TournamentSelection(k=3)
+ SegmentCrossover(p=0.5) + GaussianMutation(σ=0.1, p=0.2) + Elitism(top=2)
の組合せが効いている.

実 llive 評価に切り替えても, **30 個体 × 30 世代 = 900 評価** で十分実用的な
構成探索ができる見込み. 1 評価 5 分なら 75 時間 (= 約 3 日) で 30 世代分.

## 5. 次セッション残作業

| Phase | 残 | 着手判断 |
|---|---|---|
| 2 | 実 LlivKernel spawn (subprocess 経由) + ephemeral data_dir | 環境準備後 |
| 2 | 実 backend (llama-server / Anthropic) で 1 体評価の E2E smoke | credential 復旧後 |
| 3 | lleval 統合 (LV-09) — 19 dim genome を lleval Config に変換 | lleval repo init 後 |
| 3 | 系統樹可視化 (LV-10) — `out/<run>/lineage.mmd` | Phase 2 完了後 |

## 6. 関連

- `docs/requirements_v0.C_llive_variant_evolution.md` — 本実装の要件
- `docs/requirements_v0.B_evolutionary_optimization.md` — v0.B 本体
- `docs/experiments/evolutionary_v0_B_2026_05_21.md` — v0.B 実験 log
- `src/llive/perf/evolutionary/llive_variant.py` — 実装本体
- `src/llive/perf/evolutionary/crossover.py` — SegmentCrossover
- `src/llive/perf/evolutionary/loop.py` — checkpoint / resume / budget
- maintainer memory:
  - [[user-cognitive-mesh-model]] (10 思考因子の起源)
  - [[feedback-quiet-hours]] (SegmentedScheduler の grace_sec と相性)
  - [[feedback-marathon-lessons]] (mock baseline 重要性, ここでも適用)
