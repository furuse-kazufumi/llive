---
name: observe-cycle
description: |
  llive Brief grounding の「実装 → 観察 → 課題発見 → 即修正」サイクルを 1 周
  ずつ進めるための workflow skill。観察スクリプト
  `scripts/observe_grounding.py` を使って実 Brief サンプルに citation channel
  を流し、出力を見て最大の問題 1 つを即座に修正、回帰テスト + commit、次の
  問題へ進む。Auto-trigger when: ユーザーが「観察」「実 Brief」「surface」
  「課題発見」「実装→観察」のキーワードを発話、または MATH grounding /
  citation channel に手を入れた直後。
---

# observe-cycle — 観察→修正サイクル

## 何を解く skill か

このスキルは「単体テストは全部 PASS しているのに、実 Brief を回したら
想定外の挙動が大量に出てくる」状況に対応するためのもの。
[[scripts/observe_grounding.py]] を使って citation channel の挙動を
**assertion ではなく観察** 視点で可視化し、最大の問題から 1 つずつ修正する。

## 入力前提

- `D:/projects/llive` が現在のリポジトリ
- 6 件以上の代表的 Brief サンプルが `scripts/observe_grounding.py::SAMPLE_BRIEFS`
  に登録済 (新サンプル追加は推奨だが必須ではない)
- 全テスト PASS 状態 (`py -3.11 -m pytest -q`)

## 1 周の手順

1. **観察スクリプト実行** — 結果を `docs/benchmarks/<date>-grounding-observation/observation.md` に出力
   ```bash
   py -3.11 scripts/observe_grounding.py --out docs/benchmarks/2026-MM-DD-grounding-observation/observation.md
   ```
2. **出力を読む** — 「集約観察」ブロックと各 Brief の citation 列を見て、**1 つ** の最大課題を選ぶ
   - 誤抽出 (例: 指数表記が分割される) — 最優先
   - UNKNOWN 大量発生 (拡張可能な辞書欠落)
   - 偽陽性 (例: TRIZ trigger の誤発火)
   - 出力フォーマット不足 (例: scale 未表示)
3. **修正**: 最小スコープで該当ファイルを編集 (regex 1 行 / 辞書 1 エントリ /
   フィルタ 1 リスト 等)。**ファイル数を 1〜2 に絞る**。
4. **回帰テスト**: 該当箇所 + 全体
   ```bash
   py -3.11 -m pytest tests/unit/test_<area>.py -q --tb=short
   py -3.11 -m pytest -q --tb=line -x
   ```
5. **回帰テスト追加**: 修正が間違いを再発させないために、failure-driven な
   テストを最低 1 件足す。"surfaced by 2026-MM-DD-grounding-observation" を
   docstring に書いて来歴を残す
6. **観察スクリプト再実行**: 同じ Brief で問題が消えたか確認
7. **commit**: intentional commit メッセージで「観察 → 発見 → 修正」の
   ナラティブを残す
8. **次の問題へ** — 上記 1 から繰り返す

## 1 セッションの目安

- 1 周あたり 10-15 分、コミット 1 件、テスト 1-3 件追加
- 1 セッションで 4-6 周が現実的 (context 圧迫を考慮)
- 「これ以上は次セッション」と区切る判断は context 量と疲労感

## 出力

- `docs/benchmarks/<date>-grounding-observation/observation.md` (最新)
- 各 commit (周ごと)
- 累計 PASS 数の推移 (commit メッセージに記録すると後追いしやすい)

## 関連

- `[[scripts/observe_grounding.py]]` — 観察スクリプト本体
- `[[src/llive/brief/grounding.py]]` — citation channel 実装
- `[[feedback_implementation_status_record]]` — 4 段階区分
- `[[feedback_benchmark_honest_disclosure]]` — 異常に良い結果は内訳を疑う

## 注意

- 1 周で複数ファイルに大幅変更すると、何が直ったか追えなくなる。**1 周 1 修正** が原則
- 単体テスト PASS と観察結果は独立軸 — 「観察で動いた」≠「テストが厚い」、両方追え
- 「即修正できないもの」(例: MATH-03 LaTeX 大規模) は observation.md にメモして次セッションへ
