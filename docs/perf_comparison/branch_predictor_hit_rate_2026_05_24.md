# Branch predictor hit_rate — 単体測定 (SPEC-MESH-01)

> 2026-05-24。Speculative Mesh Execution の本格導入要件
> (`llmesh/docs/requirements_speculative_mesh.md`) §5 着手順 1 =
> 「予測器単体の hit_rate を measure してから transport 配線へ」を実施。
> 実装: `llive/src/llive/evolution/branch_predictor.py` + `branch_predictor_bench.py`。
> 規約: 要件 → PoC → フィジビリティ ([[feedback_poc_feasibility_first]])。

## なぜ先に測るか

Speculative Mesh の ROI は **予測精度 (hit_rate) が支配** する。idle peer に
「次に来そうな分岐 (ChangeOp / Brief)」を投機実行させるが、外せば peer の compute は
無駄 = 電力浪費で、latency は buy できない。だから transport (SPEC-MESH-02/03) を
配線する前に、まず予測器単体の hit_rate floor/ceiling を測る (要件の主リスク #1)。

## 測定設定

- 予測器 2 種 (どちらも stdlib のみ):
  - **frequency** (baseline) — 文脈を見ず、累積頻度の top-K を返す。
  - **markov-1** — 直前に観測した action の遷移分布から top-K。未知文脈は global 頻度→
    既定語彙へ degrade (fail-safe)。
- 評価: online next-step prediction。各ステップで予測を**観測前**に読み、実際の次 action が
  top-K に入れば hit。cold-start step も含めて計上 (honest: origin は 1 step 目から投機する)。
- 合成系列 4 種 × k∈{1,2}、n=2000、seed=0。
- 再現: `py -3.11 -m llive.evolution.branch_predictor_bench`

## 結果

| scenario | k | frequency | markov-1 | uplift | note |
|---|---|---|---|---|---|
| iid (no structure) | 1 | 0.249 | 0.237 | -0.012 | no structure (sanity: baseline holds) |
| iid (no structure) | 2 | 0.497 | 0.496 | -0.001 | no structure (sanity: baseline holds) |
| skewed frequency (.70) | 1 | 0.697 | 0.695 | -0.002 | no structure (sanity: baseline holds) |
| skewed frequency (.70) | 2 | 0.803 | 0.796 | -0.007 | no structure (sanity: baseline holds) |
| markov-1 noisy (.85) | 1 | 0.229 | 0.872 | +0.643 | context captures structure |
| markov-1 noisy (.85) | 2 | 0.451 | 0.910 | +0.460 | context captures structure |
| cyclic (period 4) | 1 | 0.250 | 0.999 | +0.749 | context captures structure |
| cyclic (period 4) | 2 | 0.499 | 0.999 | +0.499 | context captures structure |

## 解釈

- **構造が無いと markov は baseline を超えない** (iid / skewed の uplift ≈ 0)。これは
  sanity check: 文脈モデルが構造の無い系列で「勝った」ら、それはノイズか実装バグの徴候。
  ここでは正しく baseline 同等に張り付いた。
- **skewed (.70)** は文脈ではなく頻度の偏り。frequency が dominant 確率 0.70 をそのまま
  hit_rate にする (0.697) = baseline で十分。markov はここに価値を足さない (honest)。
- **第一次構造がある系列で markov が支配的に勝つ**: noisy (.85) で 0.229→0.872 (k=1)、
  cyclic で 0.250→0.999。要件の成功基準「hit_rate ≥ 0.5」は、実 ChangeOp 系列に
  order-1 構造があれば容易に満たせる見込み。

## honest disclosure (数値を引用する前に必読)

- これは **合成系列** での測定。実運用 hit_rate は、稼働中の llive が実際に出す
  ChangeOp / Brief 系列に依存し、その系列はまだログ化されていない。本測定は
  **「予測器が構造を捉えられるか」という capability の検証**であって、本番 hit_rate ではない。
- **hit_rate は speedup ではない**。end-to-end の ROI は `llmesh/speculative/bench.py` の
  レイテンシモデルが決め、実 transport 上で再測定が要る (SPEC-MESH-07)。hit_rate はその
  ROI の **入力**にすぎない。
- markov-1 は order-1 しか見ない。実 ChangeOp 系列が高次依存や container 文脈で動くなら
  order-1 では取りこぼす。粒度 (action だけ vs target_container 込み) と次数は実ログを得て
  から上げる。
- baseline (frequency) を全数値に併記したのは [[feedback_benchmark_honest_disclosure]] に
  従うため。iid 行が「baseline が崩れていない」ことの証拠。

## 実測経路 (2026-05-24 実装済 — 合成値を実測で上書きする仕組み)

§次ステップ 1 の「実 ChangeOp 系列のログ化」を実装した。これで合成値を実測で上書きする
**仕組みは完成**し、残るは実運用ログの蓄積だけになった (mechanism ready, data pending)。

- **ログ化**: `llive/src/llive/evolution/change_op_log.py` — `ChangeOpSequenceLog`
  (append-only JSONL)。`apply_diff` が materialize した ChangeOp 列を action label
  (`op_action_label`: instance → 4 種ラベル) に落として 1 diff = 1 burst で永続化。
  `applied` で static gate 通過可否を記録 (emitted / promotable の 2 系列を測れる)。
- **配線**: `triz/self_reflection.py` の `SelfReflectionSession(change_op_log=...)`。
  `_verify` で `apply_diff` 成功時にその burst を記録 (失敗 diff は記録しない)。
  既定 None = オフ (運用時に渡せば自動蓄積)。bench / 将来の多世代ループにも同じ log を
  通せば、進化が実際に走る場所すべてで実系列が貯まる。
- **実測**: `llive/src/llive/evolution/branch_predictor_real.py` — ログを読み
  frequency vs markov-1 の hit_rate を測る。`py -3.11 -m llive.evolution.branch_predictor_real <log.jsonl>`。

**honest disclosure (実測ガード)**: scored steps < `MIN_PREDICTIONS` (=30) のとき
`insufficient_data` を立て、**数値を一切出さず**「実測データ不足」と表示する。少数ステップの
hit_rate はノイズであり、それを本番値として引用するのは [[feedback_benchmark_honest_disclosure]]
が戒める「変に高速 = 良い結果」の罠そのもの。ゆえに合成上限は実ログが十分貯まるまで降ろさない。
burst 間の継ぎ目は within-diff の因果ステップではないが、origin が実際に連続して emit する
operational transition なので連結を採用 (この注記つき)。

## 次ステップ

1. ~~実 ChangeOp 系列のログ化~~ **完了 (上記「実測経路」)**。残作業 = 稼働進化ループを
   `ChangeOpSequenceLog` 付きで回し、実ログを `MIN_PREDICTIONS` 以上まで蓄積 → 実測で
   合成値を上書き。
   **依然の前提 (2026-05-24)**: ChangeOp を *系列的* に大量に出す多世代進化ループは
   現状まだ常時稼働していない (`evolution/bench.py` の `BenchHarness` は単発 A/B、
   self-reflection は 1 cycle で短い burst)。仕組みは入ったので、ログを貯める運用が回れば
   実測値が得られる。
2. 実 hit_rate が成功基準 (≥ 0.5) を満たすなら SPEC-MESH-02/03 (transport + executor) へ。
   満たさないなら次数/粒度を上げる or 投機対象を「重い分岐」に絞る (SPEC-MESH-06)。
3. SPEC-MESH-04 fast-fallback は最初から組み込む (後付け不可・最高優先)。

## Sources / 関連

- 予測器: `llive/src/llive/evolution/branch_predictor.py` (+ tests, bench)
- 実系列ログ: `llive/src/llive/evolution/change_op_log.py` (+ `tests/unit/test_change_op_log.py`)
- 実測: `llive/src/llive/evolution/branch_predictor_real.py` (+ `tests/unit/test_branch_predictor_real.py`)
- 配線: `llive/src/llive/triz/self_reflection.py` (`SelfReflectionSession(change_op_log=...)`)
- 要件: `llmesh/docs/requirements_speculative_mesh.md` (SPEC-MESH-01 / §5)
- manifest 契約: `llmesh/llmesh/speculative/manifest.py` (`SpeculativeManifest.branch` = opaque dict)
- 上流: memory `project_idea_speculative_mesh_execution` / `project_fullsense_expression_realtime_marathon`
