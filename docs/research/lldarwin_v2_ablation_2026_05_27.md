# lldarwin v2 Ablation Report

日付: 2026-05-27  設定: pop=24, gens=40, seeds=[0, 1, 2, 3, 4]

> **HONEST DISCLOSURE**: 本実験は proxy fitness のみ使用 (LLM 不使用)。
> 「mechanism feasibility」= 選択アルゴリズムが proxy 指標で機能するか の検証。
> 実 LLM 評価との相関は保証されない。結論は全て proxy 限界付きで解釈すること。

## 1. 平均指標表 (5 seed 平均)

| 構成 | best_final | best_incr(tail30%) | div_l2_mean | div_l2_final | pop_size | sat_gen | me_filled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 1.0000 | 0.0035 | 10.5042 | 10.5899 | 24 | 4 | 35 |
| no_novelty | 0.9961 | 0.0064 | 7.7197 | 9.5262 | 24 | 7 | 31 |
| no_adaptive | 0.9997 | 0.0001 | 16.0023 | 11.9567 | 24 | 3 | 45 |
| no_factor_sub | 0.9999 | 0.0039 | 12.4835 | 12.3285 | 24 | 2 | 36 |
| no_reservoir | 1.0000 | 0.0103 | 5.4743 | 3.4459 | 24 | 7 | 32 |
| no_map_elites | 1.0000 | 0.0035 | 10.5042 | 10.5899 | 24 | 4 | 0 |
| tournament | 0.9965 | 0.0125 | 8.7223 | 3.5862 | 24 | 4 | 0 |

## 2. 寄与率表 (baseline − 構成, 3 指標)

正 = その要素が baseline に寄与している (外すと指標が下がる)
負 = 外すと改善または無関係

| 構成 | best_final | best_incr(tail30%) | div_l2_mean | 合計寄与 |
| --- | --- | --- | --- | --- |
| no_novelty | +0.0039 | -0.0029 | +2.7845 | +2.7855 |
| no_adaptive | +0.0002 | +0.0035 | -5.4982 | -5.4945 |
| no_factor_sub | +0.0000 | -0.0003 | -1.9794 | -1.9797 |
| no_reservoir | -0.0000 | -0.0067 | +5.0299 | +5.0231 |
| no_map_elites | +0.0000 | +0.0000 | +0.0000 | +0.0000 |
| tournament | +0.0035 | -0.0089 | +1.7819 | +1.7764 |

## 3. 各要素の寄与判定

- **novelty (z-score 標準化)** (`no_novelty`): **必須** — 外すと飽和/多様性が有意に低下
- **adaptive_difficulty (条件カリキュラム)** (`no_adaptive`): **削減候補 (有害方向)** — 外した方が指標が改善 (proxy 限定)
- **factor_subspace_qd (意味次元 QD ブレンド)** (`no_factor_sub`): **削減候補 (有害方向)** — 外した方が指標が改善 (proxy 限定)
- **lineage_reservoir (系統中立貯蔵庫)** (`no_reservoir`): **必須** — 外すと飽和/多様性が有意に低下
- **map_elites_archive (QD アーカイブ)** (`no_map_elites`): **削減候補** — 寄与微小 (proxy スケールでは必要性薄)

### Tournament 対照群

- baseline best_final=1.0000 vs tournament=0.9965
- diversity_l2_mean: baseline=10.5042 vs tournament=8.7223

## 4. 破綻しない最小コア候補

削減候補 (寄与率 < 0.005、外しても破綻リスク低): no_adaptive, no_factor_sub, no_map_elites
最小コア (残すべき要素): no_novelty, no_reservoir

> **破綻境界**: 複数要素を同時に外す組み合わせ実験 (combo ablation) は
> 本実験スコープ外。最小コア候補は 1 要素 off の推定のみ。
> 実際の破綻境界は combo ablation (次ステップ) で確認すること。

## 5. frozen 候補にできる要素

frozen = 「寄与率が一定以上あり、proxy スケールで挙動が安定している = チューニング不要で凍結できる」要素。

frozen 候補: no_novelty, no_reservoir

## 6. Proxy 限界 (Honest Disclosure)

本実験の fitness は `make_pressure_fitness()` による決定論的 proxy。思考因子の均衡スコアを返すだけであり、実 LLM タスク評価ではない。
具体的な限界:
1. **Goodhart リスク**: proxy はゲノム空間を直接測るため、novelty や多様性を「ゲノム座標の分散」として評価する。実 LLM の出力多様性・能力とは異なる可能性が高い。
2. **飽和が早い**: proxy の値域は狭く (balance * (1 - std))、実 LLM より早期に best=1.0 近傍に到達しやすい。饱和世代 (saturation_gen) の絶対値は実 LLM ランとは直接比較できない。
3. **lineage_reservoir の寄与**: proxy では全個体が同一の決定論的 fitness を返すため、系統固定圧が弱い。実 LLM では fitness の個体差が大きいためreservoir の寄与が更に大きくなる可能性がある。
4. **map_elites の役割**: proxy では archive の多様性指標が選択圧に再帰しないためarchive の寄与率が低く出やすい。実 LLM ランでの archive ベースのmulti-criteria selection では寄与が逆転する可能性。
5. **seed 変動**: 5 seed 平均だが、proxy の確定論的性質から seed 間分散が実 LLM より小さい。実 LLM ランでは分散が増え、各判定の信頼区間が広がる。

**結論の使い方**: 「proxy で寄与率が高い要素は実 LLM でも必須候補」だが、
「proxy で削減候補」= 実 LLM でも不要 とは**言えない**。
proxy 結果は実 LLM 実験の仮説生成と設計ガイドとして使う。

## 7. Seed 別詳細 (raw)

<details>
<summary>展開して表示</summary>

### baseline

```
{"best_score_final": 1.0, "best_score_increment": 0.00042710098964404697, "diversity_l2_mean": 15.909040755972471, "diversity_l2_final": 10.804643138588313, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 38, "saturation_gen": 5, "config_name": "baseline", "seed": 0, "elapsed_s": 1.193}
{"best_score_final": 1.0, "best_score_increment": 0.003790306958189049, "diversity_l2_mean": 7.895619590168291, "diversity_l2_final": 10.990329496215834, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 35, "saturation_gen": 11, "config_name": "baseline", "seed": 1, "elapsed_s": 1.229}
{"best_score_final": 0.9997683908751853, "best_score_increment": 0.0012239018236958055, "diversity_l2_mean": 8.613892779709717, "diversity_l2_final": 14.47918917293831, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 33, "saturation_gen": 2, "config_name": "baseline", "seed": 2, "elapsed_s": 1.4}
{"best_score_final": 1.0, "best_score_increment": 2.813881640029159e-05, "diversity_l2_mean": 10.680566925540889, "diversity_l2_final": 6.523697478166955, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 43, "saturation_gen": 3, "config_name": "baseline", "seed": 3, "elapsed_s": 1.175}
{"best_score_final": 1.0, "best_score_increment": 0.012255756428164788, "diversity_l2_mean": 9.42168308096755, "diversity_l2_final": 10.151452192721, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 29, "saturation_gen": 1, "config_name": "baseline", "seed": 4, "elapsed_s": 1.175}
```

### no_novelty

```
{"best_score_final": 1.0, "best_score_increment": 0.0, "diversity_l2_mean": 21.852063921148353, "diversity_l2_final": 20.30049899776287, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 33, "saturation_gen": 5, "config_name": "no_novelty", "seed": 0, "elapsed_s": 0.729}
{"best_score_final": 0.9857578909702917, "best_score_increment": 0.016549324241421637, "diversity_l2_mean": 2.8688086775256987, "diversity_l2_final": 7.6662369768946155, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 27, "saturation_gen": 1, "config_name": "no_novelty", "seed": 1, "elapsed_s": 0.694}
{"best_score_final": 1.0, "best_score_increment": 0.0, "diversity_l2_mean": 5.790081411310453, "diversity_l2_final": 8.260256685290337, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 28, "saturation_gen": 27, "config_name": "no_novelty", "seed": 2, "elapsed_s": 0.673}
{"best_score_final": 1.0, "best_score_increment": 0.0, "diversity_l2_mean": 6.160514447009811, "diversity_l2_final": 8.494588261725484, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 42, "saturation_gen": 2, "config_name": "no_novelty", "seed": 3, "elapsed_s": 0.708}
{"best_score_final": 0.9945219655797742, "best_score_increment": 0.015607155588759358, "diversity_l2_mean": 1.9268815317273555, "diversity_l2_final": 2.9095515954284283, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 26, "saturation_gen": 1, "config_name": "no_novelty", "seed": 4, "elapsed_s": 0.661}
```

### no_adaptive

```
{"best_score_final": 0.9992226493843077, "best_score_increment": 0.00035024962604823795, "diversity_l2_mean": 18.768318814800583, "diversity_l2_final": 11.417148335421018, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 48, "saturation_gen": 5, "config_name": "no_adaptive", "seed": 0, "elapsed_s": 0.942}
{"best_score_final": 1.0, "best_score_increment": 0.0, "diversity_l2_mean": 17.533514512098538, "diversity_l2_final": 18.177384315913947, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 56, "saturation_gen": 5, "config_name": "no_adaptive", "seed": 1, "elapsed_s": 0.939}
{"best_score_final": 1.0, "best_score_increment": 0.0, "diversity_l2_mean": 16.477962630961592, "diversity_l2_final": 12.729722939308495, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 42, "saturation_gen": 1, "config_name": "no_adaptive", "seed": 2, "elapsed_s": 0.942}
{"best_score_final": 1.0, "best_score_increment": 0.0, "diversity_l2_mean": 12.477542601442808, "diversity_l2_final": 10.714311277327607, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 40, "saturation_gen": 3, "config_name": "no_adaptive", "seed": 3, "elapsed_s": 0.957}
{"best_score_final": 0.9994894240688426, "best_score_increment": 0.0, "diversity_l2_mean": 14.754357672688155, "diversity_l2_final": 6.74490372118303, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 42, "saturation_gen": 2, "config_name": "no_adaptive", "seed": 4, "elapsed_s": 1.014}
```

### no_factor_sub

```
{"best_score_final": 0.9996369534400655, "best_score_increment": 0.00035024962604823795, "diversity_l2_mean": 14.980672338058492, "diversity_l2_final": 15.827345704010364, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 38, "saturation_gen": 5, "config_name": "no_factor_sub", "seed": 0, "elapsed_s": 1.035}
{"best_score_final": 1.0, "best_score_increment": 0.0045498453558778795, "diversity_l2_mean": 13.402846583237213, "diversity_l2_final": 11.495388207371956, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 37, "saturation_gen": 2, "config_name": "no_factor_sub", "seed": 1, "elapsed_s": 0.953}
{"best_score_final": 1.0, "best_score_increment": 0.0030944682062928885, "diversity_l2_mean": 12.210354637235143, "diversity_l2_final": 15.362665790032718, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 40, "saturation_gen": 2, "config_name": "no_factor_sub", "seed": 2, "elapsed_s": 0.943}
{"best_score_final": 1.0, "best_score_increment": 0.0, "diversity_l2_mean": 11.762331725225287, "diversity_l2_final": 9.743100003324061, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 38, "saturation_gen": 3, "config_name": "no_factor_sub", "seed": 3, "elapsed_s": 0.922}
{"best_score_final": 1.0, "best_score_increment": 0.011463673595695334, "diversity_l2_mean": 10.061369383549033, "diversity_l2_final": 9.213813303373696, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 28, "saturation_gen": 1, "config_name": "no_factor_sub", "seed": 4, "elapsed_s": 0.907}
```

### no_reservoir

```
{"best_score_final": 1.0, "best_score_increment": 0.029128412867368447, "diversity_l2_mean": 10.712712242012056, "diversity_l2_final": 1.7989061784024396, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 44, "saturation_gen": 2, "config_name": "no_reservoir", "seed": 0, "elapsed_s": 1.398}
{"best_score_final": 1.0, "best_score_increment": 0.020885390221394018, "diversity_l2_mean": 3.2886790043336687, "diversity_l2_final": 4.493010246405994, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 31, "saturation_gen": 15, "config_name": "no_reservoir", "seed": 1, "elapsed_s": 1.166}
{"best_score_final": 1.0, "best_score_increment": 0.0012845724539209957, "diversity_l2_mean": 3.9912288556088535, "diversity_l2_final": 3.8334047601709473, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 26, "saturation_gen": 14, "config_name": "no_reservoir", "seed": 2, "elapsed_s": 1.191}
{"best_score_final": 1.0, "best_score_increment": 0.0, "diversity_l2_mean": 5.8700042961966545, "diversity_l2_final": 4.498710411212614, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 35, "saturation_gen": 3, "config_name": "no_reservoir", "seed": 3, "elapsed_s": 1.418}
{"best_score_final": 1.0, "best_score_increment": 0.0, "diversity_l2_mean": 3.508843679784038, "diversity_l2_final": 2.6056770971028733, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 27, "saturation_gen": 1, "config_name": "no_reservoir", "seed": 4, "elapsed_s": 1.16}
```

### no_map_elites

```
{"best_score_final": 1.0, "best_score_increment": 0.00042710098964404697, "diversity_l2_mean": 15.909040755972471, "diversity_l2_final": 10.804643138588313, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 0, "saturation_gen": 5, "config_name": "no_map_elites", "seed": 0, "elapsed_s": 1.172}
{"best_score_final": 1.0, "best_score_increment": 0.003790306958189049, "diversity_l2_mean": 7.895619590168291, "diversity_l2_final": 10.990329496215834, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 0, "saturation_gen": 11, "config_name": "no_map_elites", "seed": 1, "elapsed_s": 1.49}
{"best_score_final": 0.9997683908751853, "best_score_increment": 0.0012239018236958055, "diversity_l2_mean": 8.613892779709717, "diversity_l2_final": 14.47918917293831, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 0, "saturation_gen": 2, "config_name": "no_map_elites", "seed": 2, "elapsed_s": 1.264}
{"best_score_final": 1.0, "best_score_increment": 2.813881640029159e-05, "diversity_l2_mean": 10.680566925540889, "diversity_l2_final": 6.523697478166955, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 0, "saturation_gen": 3, "config_name": "no_map_elites", "seed": 3, "elapsed_s": 1.135}
{"best_score_final": 1.0, "best_score_increment": 0.012255756428164788, "diversity_l2_mean": 9.42168308096755, "diversity_l2_final": 10.151452192721, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 0, "saturation_gen": 1, "config_name": "no_map_elites", "seed": 4, "elapsed_s": 1.259}
```

### tournament

```
{"best_score_final": 1.0, "best_score_increment": 0.0, "diversity_l2_mean": 7.482997176223712, "diversity_l2_final": 2.377685572758299, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 0, "saturation_gen": 3, "config_name": "tournament", "seed": 0, "elapsed_s": 0.179}
{"best_score_final": 0.982422868230759, "best_score_increment": 0.03990467849039858, "diversity_l2_mean": 7.6061410340677735, "diversity_l2_final": 0.3533311029670953, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 0, "saturation_gen": 2, "config_name": "tournament", "seed": 1, "elapsed_s": 0.224}
{"best_score_final": 1.0, "best_score_increment": 0.012531452095094986, "diversity_l2_mean": 7.877301300697762, "diversity_l2_final": 1.2796670534918537, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 0, "saturation_gen": 5, "config_name": "tournament", "seed": 2, "elapsed_s": 0.23}
{"best_score_final": 1.0, "best_score_increment": 0.007218071559198513, "diversity_l2_mean": 13.42335697916233, "diversity_l2_final": 7.915108874523356, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 0, "saturation_gen": 10, "config_name": "tournament", "seed": 3, "elapsed_s": 0.183}
{"best_score_final": 1.0, "best_score_increment": 0.0027664704392480477, "diversity_l2_mean": 7.221622152415116, "diversity_l2_final": 6.005381863766781, "final_pop_size": 24, "stopped_reason": "max_generations", "actual_generations": 40, "map_elites_n_filled": 0, "saturation_gen": 4, "config_name": "tournament", "seed": 4, "elapsed_s": 0.17}
```

</details>
