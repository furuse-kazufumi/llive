---
layout: default
title: "Antifragile 定量比較 PoC — 局所最適脱出"
parent: "Perf comparison"
nav_order: 10
---

# Antifragile Mutation — 定量比較 PoC (2026-05-24)

> [[project_idea_antifragile_mutation]] の honest disclosure「自己破壊で次の安定へ、が
> 効くかは未検証」を **定量比較** した。`py -3.11 -m llive.evolution.antifragile_bench`
> (`tests/unit/test_antifragile_bench.py`, 5 ケース)。

## 設定

- **landscape**: 騙し 2 山。局所最適 x=-2 (高さ 0.85, 広い basin) と大域最適 x=3
  (高さ 1.0, 狭い basin) を 5 単位離す。全個体を局所 basin 起点で初期化。
- **baseline**: 小 sigma (0.3) の GA。谷を越えられず局所最適に捕まる。
- **antifragile**: 停滞 (改善なし) を高 surprise として実 `AntifragileController` に供給。
  panic 中のみ sigma を `exploration_multiplier`=8 倍。clock は世代カウンタ注入、cooldown=5 世代。
- pop=30 / n_gen=60 / seeds=30。

## 結果 (simulation, seeds=30)

| 指標 | baseline (panic なし) | antifragile (panic あり) |
|---|---|---|
| **大域最適 脱出率** | **0%** | **100%** |
| 平均 best fitness | 0.850 | 1.000 |
| 平均 panic 世代数 (cost) | n/a | 47.7 / 60 |

## 効果判定

- ✅ **効果あり (この landscape では決定的)**: baseline は 1 度も脱出せず局所最適 (0.85) に
  捕まるが、antifragile は **全 seed で大域最適 (1.0) に到達**。「自己破壊 (探索爆発) で
  局所最適から脱出」が定量的に確認できた。
- ⚠️ **コストは小さくない**: panic が 60 世代中 ~47.7 世代 ON。一度捕まると surprise が
  高止まりし panic が持続する設計のため。探索増幅は評価回数 (= 計算/電力) を増やす。
- ⚠️ **honest disclosure**: これは **panic が有利になるよう設計した toy 1-D landscape**。
  「探索増幅で脱出できる」原理は実証したが、実 llive 進化 (高次元 genome / 実 fitness) での
  ROI は別途要測定。`exploration_multiplier`=1 では脱出率が落ちる (増幅が効いている裏付け)。

## 本格導入への含意

- panic トリガを「停滞検知」に紐付ければ、局所最適 (集団が揃った stack 状態) からの
  脱出機構として機能する。
- ただし panic 持続コストが高いので、**cooldown と recovery_ratio で panic 滞在を絞る**
  チューニングが本番では必須 (本 PoC は cooldown=5 世代でも 47.7 世代 ON = 再発火が多い)。
- 次: 実 fitness (llive variant 評価) + 高次元 genome での脱出率/コスト測定。

## Sources / 関連

- 実装: `src/llive/evolution/antifragile.py` (commit `f2c2d1e`) + `antifragile_bench.py`
- アイデア: [[project_idea_antifragile_mutation]] (Gemini ブレスト #3)
- 組み合わせ候補: panic × Speculative Mesh (並行投機で脱出を高速化) / panic × 予測検証
  ゲート (verifier 負荷急増を前段で抑制)
