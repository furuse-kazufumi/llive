# Persona Prompt Library

> v0.F C-prompt 染色体の本体. 各偉人 = 1 md ファイル.
> 詳細仕様: [`docs/requirements_v0F_persona_prompt_resources.md`](../../../../docs/requirements_v0F_persona_prompt_resources.md)

## 構造

```
persona_prompts/
├── README.md         (this file)
├── _schema.md        (共通スキーマ仕様)
├── <field>/          (mathematician / physicist / ...)
│   └── <id>.md
└── ...
```

12 分野 × 平均 7-8 名 = ~90 名級.

## 現状 (2026-05-23)

| 分野 | skeleton 着地 | 候補総数 | 収集経路 |
|---|---|---|---|
| mathematician | 2 (岡潔 / Grothendieck) | 20 | claude_knowledge |
| physicist | 1 (Feynman) | 12 | claude_knowledge |
| computer_scientist | 1 (Knuth) | 12 | claude_knowledge |
| software_engineer | 1 (金子勇) | 10 | claude_knowledge |
| ai_ml_researcher | 0 | 10 | (Phase 2: Perplexity) |
| engineer | 0 | 8 | (Phase 2: Perplexity) |
| chemist | 0 | 4 | (Phase 2: Perplexity) |
| biologist | 0 | 4 | (Phase 2: Perplexity) |
| philosopher | 0 | 3 | (Phase 2: Perplexity) |
| cognitive_scientist | 0 | 4 | (Phase 2: Perplexity) |
| economist | 0 | 3 | (Phase 2: Perplexity) |
| **計** | **5 / 90** | **90** | mixed |

Phase 1 (本セッション): 5 名 skeleton + Loader API.
Phase 2 (後続): Perplexity で残 85 名収集.
Phase 3: A/B test でライブラリサイズと進化健全性の相関測定.

## 使用 (Loader API)

```python
from llive.genome.persona_loader import PersonaPromptLibrary

lib = PersonaPromptLibrary()
print(lib.discover())  # ['oka_kiyoshi', 'grothendieck', 'feynman', ...]

# Compose multiple personas into one prompt block
prompt = lib.compose(["oka_kiyoshi", "grothendieck"], density=0.7)
# → "あなたは岡潔とグロタンディークの思考を継承します..."
```

## ライセンス / 出典

各ファイルの frontmatter `license_note` と `source_refs` を必ず確認.
直接引用は 20 字以下に抑制. paraphrase + 出典明示が原則.
