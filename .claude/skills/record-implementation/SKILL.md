---
name: record-implementation
description: |
  llive で実装が完了した直後に、REQUIREMENTS.md の Status 反映 + memory の
  該当 project_* 更新 + MEMORY.md インデックス追加 + intentional commit を
  まとめて行う後処理 skill。feedback_implementation_status_record の 4 段階
  区分 (実装済/未配線/部分実装/未実装) で記録の整合性を保つ。
  Auto-trigger when: 実装 commit 直後、または「実装完了」「Status 更新」
  「memory 反映」「実装後の記録」を発話。
---

# record-implementation — 実装後の記録パイプライン

## 何を解く skill か

実装を進めるたびに REQUIREMENTS.md・memory・CLAUDE.md の整合が
崩れていくのを防ぐための後処理。「動くものができた」と「ドキュメントに
反映した」を別の手作業として残すと、後で参照したい時に古い情報を見て
判断を誤る。本スキルで毎回同じ後処理を機械的に行う。

## 入力前提

- 該当機能のテストが PASS している
- intentional commit (auto: ... ではない feat/fix/docs) で実装本体が
  記録済 (または直後に行う)

## ステップ

### 1. テスト合計数を確認

```bash
py -3.11 -m pytest -q --tb=line | tail -3
```
最終行の `N passed` を控える。

### 2. REQUIREMENTS.md の Status 反映

該当 FR の行を 4 段階区分 ([[feedback_implementation_status_record]]) で更新:

| 区分 | 表記例 |
|---|---|
| **実装済 + 配線済** | `**Implemented + Brief grounding 配線済** (2026-MM-DD, internal: <path>, 補足)` |
| **実装済 (未配線)** | `**Implemented** (2026-MM-DD, internal: <path>, **未配線**: <理由>)` |
| **minimal 実装済** | `**Implemented (minimal scope)** (2026-MM-DD, <制限事項>)` |
| **Pending** | `Pending (<着手判断条件>)` |

### 3. memory `project_*` を更新 or 新規作成

該当領域の memory ファイル (例: `project_llive_math_vertical_*.md`)
を確認:
- 存在する: 内容を上書き or 追記。`description:` 行も更新
- 存在しない: 新規作成
  ```yaml
  ---
  name: project-<area>-<date>
  description: <area> の進捗まとめ、N PASS / 回帰ゼロ
  metadata:
    type: project
  ---
  ```

含めるべきセクション:
- 実装ステータス table
- このセッションのハイライト
- 設計判断ノート
- 残作業
- 関連 memory ([[link]] 形式)

### 4. MEMORY.md インデックス追加

```
- [project_<area>_<date>.md](project_<area>_<date>.md) — <1 行要約> (YYYY-MM-DD)
```

既存エントリの更新の場合は `description` 部分を最新化。

### 5. 統合版記事に実装メモを追記 (任意、`feedback_articles_pause` 解除時のみ)

`docs/articles/<date>/QIITA_*.md` の該当箇所に短い「📝 実装メモ」段落を追加。
**過剰増量しない** — 1 段落、得られた具体的見識のみ。

### 6. intentional commit

```
docs(req): <FR-ID> Status を <状態> に更新

<簡潔な実装内容>
<得られた見識>
```

## チェックリスト

- [ ] REQUIREMENTS.md の Status マトリクスを 4 段階区分で書き直したか
- [ ] memory `project_*.md` の description 行も更新したか (slug は固定で OK)
- [ ] MEMORY.md にインデックス行を追加 / 既存行を更新したか
- [ ] commit メッセージに「得られた見識」セクションがあるか
- [ ] auto commit に紛れて intentional commit が無い状態になっていないか

## 注意

- **CLAUDE.md は人間管理** — ここから書き込まない。memory への更新で間接的に CLAUDE.md と整合させる
- **岡潔先生関連の言及** — `[[project_llive_oka]]` や `[[feedback_oka_kiyoshi_respect]]`
  (TBD) のような礼節文面の memory が今後追加された場合、それを参照
- `_NON_UNIT_WORDS` の追加などミクロ拡張は REQUIREMENTS には書かず memory `project_*` の「実装ノート」ブロックに集約

## 関連

- `[[feedback_implementation_status_record]]` — 4 段階区分の原典
- `[[skill: observe-cycle]]` — このスキルの前段
- `[[skill: add-grounding-channel]]` — grounding 配線後の流れ
- `[[.planning/REQUIREMENTS.md]]` — 反映先
