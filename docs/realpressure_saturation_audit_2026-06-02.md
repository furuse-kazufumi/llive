# real-pressure 進化ラン 飽和監査 (honest disclosure, 2026-06-02)

対象: `out/persona_evo_main_realpressure_s1/` (fitness=real-pressure, pop=24, gen=15, seed=1,
llive_commit `50f8590`, selection=lldarwin-v2, **novelty=False / lineage_reservoir=False**)。
本 doc は [[feedback_benchmark_honest_disclosure]]「異常に良い結果は内訳を疑う」に従う事実監査。

## 用語(かみくだき)
- **飽和(ceiling)**: スコアが満点に張り付いて、それ以上良くなりようがない状態。テストが簡単すぎると起きる。
- **多様性崩壊**: 集団が 1 種類の祖先ばかりになること。進化が「探索」をやめて 1 点に固まる。
- 要するに: **「テストが簡単すぎて1世代で満点 → あとは1系統に偏っただけ」**＝進化が効いた証拠にならない。

## 観測 (metrics.jsonl / founder_lineage.jsonl, 実データ)

| gen | best | mean | median | diversity_l2 | 支配 founder |
|---|---|---|---|---|---|
| 0 | 0.90 | 0.729 | 0.70 | 2.436 | (random)16 + 各1 |
| 1 | **1.00** | 0.800 | 0.80 | 1.442 | von-neumann 8 / millidge 6 / oka 5 |
| 2 | **1.00** | 0.804 | 0.80 | 1.193 | **millidge 18/24** |

- **best が gen1 で 1.0(満点)到達→以降頭打ち**。スコアは 0.7/0.8/0.9/1.0 の **0.1 刻み(粗い)**。
- **diversity_l2 が 2 世代で半減**(2.44→1.19)。
- **millidge が gen2 で 18/24(75%)** を占有 = 単一系統の急速 takeover。

## 根本原因 (コードで確定, 推測でない)

`src/llive/perf/evolutionary/real_pressures.py:393` `fitness()`:
`score = mean(全 task の score_fn 値)`、`cfg.axes × cfg.tasks_per_axis` の**小バッテリー**。
コードの notes 自身が **"Small batteries = noisy estimate ... NOT a general-capability claim"** と明記。

1. **天井効果**: fitness 上限 1.0 を gen1 で達成 = headroom なし。founder が既に 0.7-0.9 で、1 世代で満点に届く = **タスクが簡単すぎ / バッテリーが粗すぎる**。gen>1 の best は平坦な天井で、改善でなく頭打ち。
2. **多様性維持なし**: novelty=False + lineage_reservoir=False → 淘汰圧が単一勝者へ収束 → millidge takeover + diversity 崩壊 (= genetic drift)。
3. → **本ランは「進化が成功した」signal を出していない**。天井+drift であり、selection が load-bearing かを測れていない。

## llcore ③ arc との接続 (同型)

これは llcore ③ arc の **「天井効果 = 非診断」** と完全に同じ構造:
- Step C `flip_flop` = 全 method R²≈0.95 飽和で非診断。
- ③ arc の核: **滑らか/天井の landscape では selection(と多様性)は load-bearing になりようがない**(勾配が無い)。
- 本 real-pressure ランは llive 側で同じ罠を踏んでいる。[[feedback_llive_measurement_purity]] の純度は守れている(on-prem)が、**fitness 設計が飽和**している。

## 推奨 (CPU・on-prem で対応可)

1. **fitness に headroom を作る**: `tasks_per_axis` を増やす(粗さ解消)+ より難しいタスク + 連続スコア化 → **gen1 で満点に届かない**地形にする。founder の 0.7-0.9 から伸びしろが残る設計。
2. **多様性維持を ON**: `novelty=True` および/または `lineage_reservoir=True`。PERSONA-FX track(ペルソナ多様性の非自明性検証)は takeover が起きると成立しないので必須。
3. **honest 再評価**: 本ランの「best 曲線」を改善として報告しない(gen1 で飽和)。再設計後に fresh-seed で再走。
4. 走行中プロセス(gen2/15)は on-prem $0 なので完走させても害は無いが、**結果は非診断**。次走を上記再設計で。kill 判断はユーザー(不可逆操作のため勝手に停止しない)。

## 留保
- n=15 gen / pop24 / 小バッテリーで母数小。だが「天井で gen1 満点 + diversity 崩壊 + 単一 takeover」は seed 非依存に出る構造的兆候(³ arc と一致)。
- score_fn の各軸 rubric の中身までは本監査で精査していない(次段で軸別 breakdown を確認すると、どの軸が飽和源かが分かる)。

関連: [[feedback_benchmark_honest_disclosure]] / [[feedback_llive_measurement_purity]] / [[feedback_no_echo_baseline]] / llcore ③ arc (StepC/E-A/StepD ceiling lesson)
