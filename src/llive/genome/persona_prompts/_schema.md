# Persona Prompt — 共通スキーマ仕様

## frontmatter

```yaml
---
id: <unique_slug>                # ASCII snake_case, e.g. "oka_kiyoshi"
display_name: <preferred form>   # 表示名, e.g. "岡潔 (Oka Kiyoshi)"
era: <birth-death or active>     # e.g. "1901-1978"
fields:                          # 1-3 個
  - <primary>                    # e.g. "mathematics"
  - <secondary>
nationality: <ISO 2-char>        # e.g. "JP"
lineage:
  influenced_by:                 # 影響を受けた偉人の id list (空可)
    - <id>
  influences:                    # 影響を与えた偉人の id list (空可)
    - <id>
license_note: <text>             # 引用フェアユース / public domain / paraphrase
source_refs:                     # 最低 2 件
  - <url or citation>
  - <url or citation>
tags:                            # 検索性向上のキーワード
  - <keyword>
last_updated: YYYY-MM-DD
sources_collected_via: <claude_knowledge | perplexity | manual>
---
```

## body (5 section)

### 1. 思考スタイル (Style)

1-3 段落 (200-500 字目安). この偉人を他と区別する **特徴的な思考パターン**.
LLM が prompt として再現するときの核となる「色」を記述.

### 2. 強み (Strengths)

3-5 個の bullet. LLM が取り入れると有用な認知傾向.
例: 「**問題を最も単純な物理モデルに帰着**できる」(Feynman).

### 3. 弱み (Weaknesses)

3-5 個の bullet. 盲点 / 偏向 / 既存研究との不整合.
honest disclosure: persona は万能ではなく **盲点を必ず持つ**.
例: 「**抽象化が過度になり実装可能性を犠牲にする**」(Grothendieck).

### 4. 使用 prompt (System / User Prefix)

LLM に inject する **prompt 本文** (100-300 字). システムプロンプト先頭
または user message prefix に挿入される. 命令形 + 思考スタイル指示.

```markdown
> あなたは <偉人> の思考スタイルを継承します.
> ... (具体的な行動指示 / 拒絶事項を含む) ...
```

### 5. 思考の例 (Worked Examples)

2-3 個の小例. 入力 (一般的な問題) と出力 (偉人スタイルの解 / 思考過程).
例の中で persona の **色** が読者に伝わるように.

### 6. 禁忌 (Anti-patterns)

2-4 個の bullet. **使うべきでない場面** と **組み合わせると相互打消しになる**
他 persona の id 列挙.

### 7. 出典 (Sources)

frontmatter `source_refs` と同じものを human-readable 形式で.
直接引用は **20 字以下** に抑える.

---

## Loader API が読む section

- `style_text` ← §1 (思考スタイル)
- `strengths` ← §2 (bullet list を tuple 化)
- `weaknesses` ← §3 (同上)
- `prompt_text` ← §4 (使用 prompt の blockquote 内テキスト)
- `examples` ← §5 (各 ### サブ見出しを 1 example として tuple 化)
- `anti_patterns` ← §6 (bullet list を tuple 化)
- `sources` ← §7 (bullet list を tuple 化)

## Validation

新規 persona prompt 追加時:

1. frontmatter の必須 key (id / display_name / era / fields / license_note /
   source_refs / sources_collected_via / last_updated) の存在を check
2. `id` がディレクトリ全体で unique
3. `source_refs` が 2 件以上
4. `style_text` が 100-1000 字
5. `prompt_text` の blockquote が 50-500 字

Loader 側で violation を検出したら `PersonaPromptValidationError` を raise.
