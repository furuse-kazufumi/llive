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

## 現状 (2026-05-23 — Phase 2 完了)

| 分野 | 着地数 | 内訳 | 収集経路 |
|---|---|---|---|
| mathematician | 20 | 岡潔 + Grothendieck (Phase 1) + 18 名 (Phase 2) | mixed |
| physicist | 12 | Feynman + 11 名 | mixed |
| computer_scientist | 12 | Knuth + 11 名 | mixed |
| software_engineer | 10 | 金子勇 + 9 名 | mixed |
| ai_ml_researcher | 10 | Minsky / Hinton / LeCun / Bengio / Ng / Schmidhuber / Russell / Norvig / Sutskever / Karpathy | perplexity |
| engineer | 8 | Tesla / Shannon / Wiener / Fuller / Jobs / Wozniak / 本多光太郎 / 豊田佐吉 | perplexity |
| chemist | 4 | Pauling / Curie / Franklin / Mendeleev | perplexity |
| biologist | 4 | Darwin / Crick / Watson / 山中伸弥 | perplexity |
| philosopher | 3 | Wittgenstein / Popper / Kuhn | perplexity |
| cognitive_scientist | 4 | Piaget / H. Simon / Kahneman / Chomsky | perplexity |
| economist | 3 | H. Minsky / Taleb / Schumpeter | perplexity |
| **計** | **90 / 90** ✅ | Phase 1 sample 5 + Phase 2 Perplexity 85 | mixed |

Phase 1 (完了): 5 名 skeleton + Loader API + 19 cases test.
Phase 2 (完了 2026-05-23): Perplexity sonar-pro で残 85 名収集.
Phase 3 (次): A/B test でライブラリサイズと進化健全性の相関測定.

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
