# llive v0.F — 偉人思想 Persona Prompt リソース仕様 (Addendum)

> 親要件: [`requirements_v0.F_genome_two_layer_and_novelty.md`](requirements_v0.F_genome_two_layer_and_novelty.md)
> 策定日: 2026-05-23 (silent 自律セッション)
> ユーザー指示: 「Prompt ベースで偉人の思考を取り込むというゲノムについて、偉人の情報源を提供しないと成立しない。研究者寄りの偉人 (数学者 / 技術者 / プログラマー / 各業界研究者) を Prompt 化。個体数の数倍リソース。Perplexity 使用可。」

---

## 1. なぜこの addendum か (Why)

`requirements_v0.F_genome_two_layer_and_novelty.md` §A-2 で `persona_set` を以下のように
bitmask enum で定義していた:

```
{ 岡潔, Polya, TRIZ, Six Hats, Bayesian, Feynman, 金子勇 }
```

これは **「どの persona を ON にするか」の選択肢** に過ぎず、**各 persona が
実際にどんな思考を駆動するかの prompt 本体が存在しない**。Genome に書いた
`persona_set=0b0010110` を実行時に prompt に翻訳する経路が欠落していた。

本 addendum で以下を確定する:

1. **Persona Prompt Library**: 1 persona = 1 markdown file の reference library
2. **共通スキーマ**: frontmatter (id / fields / era / lineage / license) + body
   (思考スタイル / 強み / 弱み / 例 / 禁忌 / 出典)
3. **Loader API**: `PersonaPromptLibrary` クラスで Genome bitmask → composed prompt
4. **個体数の数倍リソース**: 初期スコープ ~20、最終 ~90 (集団 size 30 × 3 倍)
5. **多様性確保**: 数学 / 物理 / 計算機 / ソフトウェア / AI / 工学 / 化学 / 生物 /
   哲学 / 認知 / 経済 / アート — **12 分野以上** を最低 2-3 名ずつ
6. **収集手順**: 私 (Claude) の知識 + Perplexity ([`PERPLEXITY_API_KEY`](D:/api-keys.json)) で出典収集

---

## 2. Persona Prompt Library 構造

### 2.1 配置

```
src/llive/genome/persona_prompts/
├── README.md
├── _schema.md                          # 共通スキーマ仕様
├── mathematician/
│   ├── oka_kiyoshi.md
│   ├── grothendieck.md
│   ├── galois.md
│   ├── ramanujan.md
│   ├── godel.md
│   ├── turing.md
│   ├── von_neumann.md
│   └── ...
├── physicist/
│   ├── feynman.md
│   ├── einstein.md
│   ├── bohr.md
│   ├── heisenberg.md
│   └── ...
├── computer_scientist/
│   ├── knuth.md
│   ├── dijkstra.md
│   ├── mccarthy.md
│   ├── alan_kay.md
│   ├── hoare.md
│   └── ...
├── software_engineer/
│   ├── stallman.md
│   ├── carmack.md
│   ├── linus_torvalds.md
│   ├── kaneko_isamu.md
│   ├── rob_pike.md
│   └── ...
├── ai_ml_researcher/
│   ├── minsky.md
│   ├── hinton.md
│   ├── lecun.md
│   ├── bengio.md
│   ├── karpathy.md
│   └── ...
├── engineer/
│   ├── tesla_nikola.md
│   ├── shannon.md
│   ├── wiener.md
│   ├── fuller.md
│   └── ...
├── chemist/
│   ├── pauling.md
│   ├── curie.md
│   └── ...
├── biologist/
│   ├── darwin.md
│   ├── crick.md
│   ├── watson.md
│   ├── yamanaka_shinya.md
│   └── ...
├── philosopher/
│   ├── wittgenstein.md
│   ├── popper.md
│   └── ...
├── cognitive_scientist/
│   ├── piaget.md
│   ├── simon_herbert.md
│   ├── kahneman.md
│   └── ...
├── economist/
│   └── ...
└── artist_designer/
    └── ...
```

### 2.2 共通スキーマ (`_schema.md` で定義)

```markdown
---
id: <unique_slug>                # e.g. "oka_kiyoshi"
display_name: <preferred form>   # e.g. "岡潔 (Oka Kiyoshi)"
era: <birth-death or active>     # e.g. "1901-1978"
fields: [<primary>, <secondary>] # e.g. ["mathematics", "philosophy"]
nationality: <ISO>               # e.g. "JP"
lineage:                         # 思想の流れ (誰の影響を受け、誰に影響を与えたか)
  influenced_by: [<id1>, <id2>]
  influences: [<id3>, <id4>]
license_note: <text>             # 引用フェアユース / public domain 等
source_refs:                     # 出典 URL or 書名
  - <url or citation>
  - <url or citation>
tags: [<keyword>, ...]           # 検索性向上
last_updated: YYYY-MM-DD
sources_collected_via: <claude_knowledge | perplexity | manual>
---

# <Display Name>

## 思考スタイル (Style)

(1-3 段落で、この偉人の特徴的な思考パターンを記述)

## 強み (Strengths)

- (LLM が取り入れると有用な認知傾向 3-5 個)

## 弱み (Weaknesses)

- (盲点 / 偏向 / 既存研究との不整合 3-5 個)

## 使用 prompt (System / User Prefix)

> あなたは ○○ の思考スタイルを継承します。
> ...
> (実際に LLM に injection する prompt 本文 100-300 字程度)

## 思考の例 (Worked Examples)

### 例 1: <problem>
<偉人スタイルで解く思考過程>

### 例 2: <problem>
<同上>

## 禁忌 (Anti-patterns)

- <この persona を使うべきでない場面>
- <組み合わせると相互打消しになる persona>

## 出典 (Sources)

1. <citation>
2. <citation>
```

---

## 3. Loader API 仕様

### 3.1 `PersonaPromptLibrary` クラス

```python
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class PersonaPrompt:
    id: str
    display_name: str
    era: str
    fields: tuple[str, ...]
    nationality: str
    style_text: str        # "## 思考スタイル" section
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    prompt_text: str       # "## 使用 prompt" section
    examples: tuple[str, ...]
    anti_patterns: tuple[str, ...]
    sources: tuple[str, ...]
    license_note: str
    lineage_influenced_by: tuple[str, ...]
    lineage_influences: tuple[str, ...]
    tags: tuple[str, ...]


class PersonaPromptLibrary:
    """File-system backed library of persona prompts."""

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).parent / "persona_prompts"
        self._cache: dict[str, PersonaPrompt] = {}

    def discover(self) -> list[str]:
        """List all available persona ids."""

    def get(self, persona_id: str) -> PersonaPrompt:
        """Load and cache a single persona."""

    def compose(self, persona_ids: list[str], density: float = 1.0) -> str:
        """Combine multiple personas into one composed prompt block.
        density: 0.0-1.0 → どれくらい詳しく取り入れるか (短縮 / フル)."""

    def by_field(self, field: str) -> list[PersonaPrompt]:
        """Filter by primary field (mathematician / physicist / ...)."""

    def random_sample(self, n: int, *, rng=None,
                      fields: list[str] | None = None) -> list[PersonaPrompt]:
        """Sample n personas, optionally biased by field."""
```

### 3.2 Genome bitmask → composed prompt 経路

```python
# v0.F Genome の C-prompt 染色体
class CPromptChromosome:
    persona_set: int          # bitmask over self.library.discover()
    prompt_template_id: str   # "base" | "chain_of_thought" | ...
    historical_quote_density: float  # [0, 1]

    def to_prompt_block(self, library: PersonaPromptLibrary) -> str:
        all_ids = library.discover()
        active = [all_ids[i] for i in range(len(all_ids))
                  if self.persona_set & (1 << i)]
        body = library.compose(active, density=self.historical_quote_density)
        return TEMPLATES[self.prompt_template_id].format(persona_block=body)
```

### 3.3 1 inference 単位での使用

```python
genome = individual.genome
prompt = genome.c_prompt.to_prompt_block(persona_library)
response = llm_backend.generate(prompt + "\n\n" + user_input)
```

---

## 4. 個体数 vs 偉人ライブラリ サイズの設計

| 集団サイズ | 必要 persona 数 (個体数 × 倍率) | 倍率根拠 |
|---|---|---|
| 30 | **90** (×3) | 各個体が ~5 persona を持つ + Hamming distance 確保 + 並列 mutation 余裕 |
| 50 | 150 | 同上 |
| 100 | 250-300 | crowding 緩和 (柱 D) |

### 4.1 個体数の数倍が必要な理由

1. **bitmask の表現力**: 90 persona → 2^90 通り。各個体が ~5 persona ON にする
   と C(90, 5) ≈ 4400 万通り。集団 30 体での重複可能性が極小化される。
2. **crossover 余裕**: 親 2 体が共有する persona が多すぎると交配の意味が薄れる。
   個体 × 倍率の library があれば overlap 率を 50% 以下に抑えられる。
3. **mutation 安全余裕**: 突然変異で「未使用 persona に flip」させるとき、
   未使用 persona が常時 50%+ 残っているほうが探索が止まらない。
4. **柱 D (Similarity Quota) との整合**: 多様性のため類似個体は淘汰される。
   ライブラリが小さいと「全員が似たような persona 構成」になり quota 違反多発。

### 4.2 初期スコープ (Phase 1)

- **20 persona** を sample として skeleton 整備
- 集団 size 7-10 程度で smoke test
- 全 90 名は Perplexity 経由で順次収集 (Phase 2)

---

## 5. 偉人候補リスト (~90 名)

### 5.1 数学者 (~20 名)

岡潔, グロタンディーク (Grothendieck), ガロア (Évariste Galois),
ラマヌジャン (Ramanujan), ヒルベルト (Hilbert), ゲーデル (Gödel),
チューリング (Turing), フォン・ノイマン (von Neumann),
エミー・ノアーター (Noether), ポアンカレ (Poincaré),
リーマン (Riemann), オイラー (Euler), ガウス (Gauss),
テレンス・タオ (Terence Tao), グリゴリー・ペレルマン (Perelman),
アンドリュー・ワイルズ (Wiles), マンデルブロー (Mandelbrot),
ポリヤ (Pólya), アンリ・ルベーグ (Lebesgue), 高木貞治

### 5.2 物理学者 (~12 名)

ファインマン (Feynman), アインシュタイン (Einstein), ボーア (Bohr),
ハイゼンベルク (Heisenberg), シュレディンガー (Schrödinger),
ディラック (Dirac), ランダウ (Landau), パウリ (Pauli),
フェルミ (Fermi), オッペンハイマー (Oppenheimer),
ホーキング (Hawking), ペンローズ (Penrose)

### 5.3 計算機科学者 (~12 名)

ドナルド・クヌース (Knuth), エドガー・ダイクストラ (Dijkstra),
アラン・ケイ (Alan Kay), トニー・ホーア (C.A.R. Hoare),
ジョン・マッカーシー (McCarthy), ニクラウス・ヴィルト (Wirth),
バーバラ・リスコフ (Liskov), グレース・ホッパー (Hopper),
ロバート・タージャン (Tarjan), レスリー・ランポート (Lamport),
レイ・トムリンソン (Tomlinson), ティム・バーナーズ＝リー (Berners-Lee)

### 5.4 ソフトウェア技術者 (~10 名)

リチャード・ストールマン (Stallman), リーナス・トーバルズ (Torvalds),
ジョン・カーマック (Carmack), デニス・リッチー (Ritchie),
ケン・トンプソン (Thompson), ロブ・パイク (Rob Pike),
カトラー (Dave Cutler), ビル・ジョイ (Bill Joy), 金子勇 (Kaneko Isamu),
リチャード・ガブリエル (Richard Gabriel)

### 5.5 AI / ML 研究者 (~10 名)

マービン・ミンスキー (Minsky), ジェフリー・ヒントン (Hinton),
ヤン・ルカン (LeCun), ヨシュア・ベンジオ (Bengio),
アンドリュー・ング (Ng), ユルゲン・シュミッドフーバー (Schmidhuber),
スチュアート・ラッセル (Russell), ピーター・ノービッグ (Norvig),
イリヤ・サツケヴァー (Sutskever), アンドレイ・カルパシー (Karpathy)

### 5.6 工学者 (~8 名)

ニコラ・テスラ (Tesla), クロード・シャノン (Shannon),
ノーバート・ウィーナー (Wiener), バックミンスター・フラー (B. Fuller),
スティーブ・ジョブズ (Jobs), スティーブ・ウォズニアック (Wozniak),
本多光太郎 (Honda Kotaro, 鉄鋼磁性), 豊田佐吉 (Toyoda Sakichi)

### 5.7 化学者 / 生物学者 (~8 名)

ライナス・ポーリング (Pauling), マリー・キュリー (Curie),
ロザリンド・フランクリン (Franklin), ドミトリ・メンデレーエフ (Mendeleev),
チャールズ・ダーウィン (Darwin), フランシス・クリック (Crick),
ジェームズ・ワトソン (Watson), 山中伸弥 (Yamanaka Shinya)

### 5.8 哲学者 / 認知科学者 / 経済学者 (~10 名)

ルートヴィヒ・ヴィトゲンシュタイン (Wittgenstein),
カール・ポパー (Popper), トマス・クーン (Kuhn),
ジャン・ピアジェ (Piaget), ハーバート・サイモン (H. Simon),
ダニエル・カーネマン (Kahneman), ノーム・チョムスキー (Chomsky),
ジョン・フォン・ノイマン (in economics: game theory),
ハイマン・ミンスキー (H. Minsky, economist), ナシム・タレブ (Taleb)

合計 ~90 名 — **集団 size 30 の ×3 倍** に到達。

---

## 6. 収集手順 (Phase 1 → Phase 2)

### Phase 1 (this session): Claude 知識ベース で skeleton

私 (Claude) の事前知識で確実に書ける優先 5 名を sample として作成:

1. **岡潔** (mathematician/oka_kiyoshi.md) — 情緒 / 直観 / 数学美
2. **グロタンディーク** (mathematician/grothendieck.md) — 一般化 / 圏論 / 構造
3. **ファインマン** (physicist/feynman.md) — 説明できなければ理解していない
4. **ドナルド・クヌース** (computer_scientist/knuth.md) — literate programming / 美
5. **金子勇** (software_engineer/kaneko_isamu.md) — P2P / 局所学習 / Winny

これらは llive の文脈 ([[project_llive_oka]], [[project_llmesh_p2p_winny]]) で
既出のため出典が確定している。

### Phase 2 (後続セッション): Perplexity 経由で残 ~85 名

`PERPLEXITY_API_KEY` を使い、各偉人について以下を query:

```
"Summarize the unique thinking style, 3 strengths, 3 blind spots, and
2-3 worked examples of {<NAME>}. Include 2-3 primary source citations
(books / papers / lectures). Format in a structure suitable for
distilling into a 200-300 character LLM persona prompt."
```

各 query 結果を `_schema.md` の構造に整形し commit。Perplexity の citation
を `source_refs` に転記し、`sources_collected_via: perplexity` を記録。

### Phase 3 (応用): スタイル A/B test

集団 size 30 で persona library 20 → 90 と段階的に拡張し、各拡張で
**fitness 平均 / diversity entropy / Novelty Lane occupancy** を測定。
ライブラリサイズと進化健全性の相関を honest disclosure で記録。

---

## 7. ライセンス / 出典の取り扱い

- 偉人本人の **公開された著作 / 講義の paraphrase + 出典明示** は fair use 範囲
- 直接引用は **20 字以下に抑える** ($/$ fair use 慣行)
- `license_note` frontmatter で明示 (例: "paraphrase + cited"、"public domain"、"fair use under 引用要件")
- `source_refs` で必ず原典 URL / ISBN を 2 件以上記載
- llive リポは Apache-2.0 + Commercial dual-license なので、persona prompt 自体は
  上記ライセンス配下で再配布可能 (出典明示が責務)

---

## 8. 連動 memory / docs

- 親要件: `requirements_v0.F_genome_two_layer_and_novelty.md` §A-2
- 関連 memory:
  - `project_llive_genome_two_layer` (本 addendum の発端)
  - `project_llive_oka` (岡潔 framework)
  - `project_llmesh_p2p_winny` (金子勇 EDLA / Winny)
  - `feedback_qiita_long_form` (出典明示の重要性)
- 関連 chapter: QIITA #24-02 (10 思考因子 + COG-MESH) の persona 拡張版
- 関連: TRIZ ベース ideation skill (`triz-ideation`), cross-domain ideation
  (`cross-domain-ideation`)
