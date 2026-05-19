# FullSense 市場受容性調査 (2026-05-19)

> 「ネタは色々と準備した認識。実社会で受け入れられそうか調べた方がいい」
> という user 指示で実施した WebSearch ベースの 6 軸調査.
> 結論を**まず**書く. 記事執筆方針への影響もまとめる.

## 結論 (1 段落)

**追い風強い**. **on-prem AI + HITL** は 2026 年に「**enterprise baseline
requirement**」に位置付けられた. 日本市場では NTT tsuzumi / NEC cotomi /
リコー / TIS インテック等の大手が **金融 / 医療 / 製造の規制業界**を
ターゲットに本格参入. 個人 OSS の FullSense が直接競合するのは無謀だが、
**個人開発者・スモールチーム / 日本語 / 監査可能性** のニッチで positioning
可能. ただし UI 競合 (Open WebUI 124K stars) と Agent framework 競合
(LangGraph が早期 2026 で CrewAI を star で抜く) は重く、認知の戦いは厳しい.

## 6 軸調査結果

### 軸 1: on-prem LLM enterprise adoption (グローバル)

- **2026 年は on-prem AI が baseline requirement に**
- 18x cheaper per 1M tokens vs cloud API (high-volume workloads)
- HITL は規制業界で **mandatory** ([EU AI Act][eu_ai_act] / [NIST AI
  RMF][nist_ai_rmf] が demonstrable HITL を要求)
- 「uncontrolled model access」「unlogged prompts」「absence of HITL」は
  **compliance risk**

[eu_ai_act]: https://www.strata.io/blog/agentic-identity/practicing-the-human-in-the-loop/
[nist_ai_rmf]: https://www.waxell.ai/blog/human-in-the-loop-vs-human-on-the-loop-ai-agents

→ **FullSense 直撃の市場 fit**. on-prem + HITL + Approval Bus + audit
は要件そのもの.

### 軸 2: Self-hosted LLM UI 競合

| ツール | GitHub stars | 強み |
|---|---|---|
| Open WebUI | **124K+** | ChatGPT 互換 UI、Docker 1 コマンド、最も人気 |
| AnythingLLM | 54K+ | RAG 特化、文書チャット |
| LibreChat | 22K+ | 複数プロバイダ、企業向け |
| Ollama | (バックエンド) | CLI-first、production-grade |
| LM Studio | (バックエンド) | GUI-first、非開発者向け |

→ **UI 領域は飽和**. llove (TUI) は完全にニッチだが、それゆえ被らない.

### 軸 3: AI Agent Framework

- **LangGraph** が早期 2026 で **CrewAI を star で追い抜いた**
  - graph-based architecture + HITL checkpoints + state persistence
  - v0.4 で LangSmith observability 強化
- **CrewAI**: enterprise observability + scheduling 追加
- **AutoGen 1.0 GA**: v2 API default

「LangGraph が production readiness 高、HITL 強い」が業界評価.

→ llive Brief API + Cognitive Mesh は LangGraph と異なる軸 (**4 層メモリ
 + 認知科学的思考因子**) で勝負できるが、認知の戦いは LangGraph 強し.
**HITL 強化** という意味では LangGraph と被るので「LangGraph 互換 backend」
として positioning する案もあり.

### 軸 4: 日本企業 on-prem LLM (最重要)

具体的な参入企業 (2026 年):

1. **TIS インテック** — 2026-01-29 にローカル LLM 導入支援開始. 製造業/金融
   業向けに PoC 環境提供 ([インテックのプレスリリース][intec])
2. **NTT tsuzumi** — 軽量 + 日本語特化、金融/医療向け
3. **NEC cotomi** — オンプレ対応、業務利用特化
4. **リコー オンプレLLMスターターキット** — 2025 日経優秀製品最優秀賞

[intec]: https://www.intec.co.jp/news/2026/0129_1.html

理由:
- 「金融取引 / 医療臨床 / 製造設計図 は規制で外部 NG → on-prem 必須」
- 大手 SIer / メーカが本格営業

→ **日本市場は急成長中**. しかし大手の影響圏も拡大. **FullSense 個人 OSS が
日本企業に売るなら**:
- 個人開発者・スモールチーム (~50 名以下) を ターゲットに
- 大企業へは「軽量 PoC ツール」or「補完 OSS」として
- TIS / NTT / NEC / リコーの **ソリューションに sub-component** として
  組み込ませる路線も検討

### 軸 5: HITL governance OSS

- 「2026 年標準は HITL を **agent code に encode**」
- **risk-tiered oversight model** (低リスク = 自動、中 = 通知、高 = 承認)
- 商用ソリューション (Prefactor / OLOID / Strata) が複数登場
- **OSS で HITL 専門ライブラリは現状不明** (検索では Heliconly /
  ClarityArc 等の SaaS / コンサル系が主)

→ **FullSense の Approval Bus + SqliteLedger は OSS の HITL ライブラリと
して positioning できる**. 「LangGraph に Approval Bus を後付けする
adapter」を出すと話題になる可能性.

### 軸 6: Qiita ローカル LLM trend

人気テーマ (2026):
- 「2026 年版 ローカル LLM 完全ガイド」
- 「Ollama で完全オフライン AI 開発環境を作る」
- 「ローカル LLM って難しそう ← 5 分で動きます」
- Qwen3.5 / Gemma 4 / GPT-OSS が標準モデル
- 「1-2 年前のクラウド最強 = 今年のローカル」(GPT-4o 級が手元で動く)
- 7B-14B でコード補完が実用品質

→ Qiita でローカル LLM 系記事は確実に**伸びている**. 記事執筆方針は正しい.
ただし「Ollama 入門系」「比較系」は飽和気味. **差別化軸**:
- 設計パターン (3 段ロケット / cross-repo schema lock)
- 認知科学 (4 層メモリ / Cognitive Mesh / 思考因子)
- 監査可能性 (Approval Bus / Quarantined Memory / Ed25519)

## SWOT 分析

### Strengths (FullSense の強み)
- on-prem + HITL + audit という **2026 年 baseline 要件をフルカバー**
- 4 層メモリ + Cognitive Mesh = **学術的に独自の領域**
- Apache-2.0 + Commercial dual license (商用化道筋確保)
- 日本語ネイティブ開発者 + Honest disclosure 文化
- 単独で価値を持つ 3 製品 (independence principle)
- M8.x 完成で 1518 PASS の実装裏付け

### Weaknesses (個人 OSS の弱み)
- 認知度: 大手 (NTT / NEC / リコー) と桁違い
- 営業力: 1 人開発者は法人契約に弱い
- 信頼性: production 実績の事例ゼロ
- 開発体制: バス係数 1 (user 1 人)
- UI 競合 (Open WebUI 124K stars) との差別化が説明しにくい
- Agent framework 競合 (LangGraph) との差別化軸が複雑

### Opportunities (市場機会)
- 規制業界の on-prem 需要が **急成長中**
- LangGraph / Open WebUI と異なる軸 (認知科学 / 監査) のニッチ
- 日本企業向け on-prem ソリューションへの **sub-component 提供**
- HITL OSS ライブラリの不在 (Approval Bus を spinoff)
- 個人開発者・スモールチーム向け軽量 PoC tool

### Threats (脅威)
- 大手 SIer / メーカが本格営業 → 個人 OSS が pre-sales で勝てない
- LangGraph + Anthropic Agents SDK が agent 市場を制圧する可能性
- EU AI Act / 中国 AI 弁法等の規制で **個人 OSS 配布が厳しくなる**
  (補足: 中国 AI 弁法は社内専用利用は filing 免除なので影響限定的)
- AI 自動コンテンツ氾濫で記事ROI 低下
- 大手モデル (Claude / GPT / Gemini) の on-prem 提供で oss の優位性弱化

## 戦略提案 (記事執筆方針への反映)

### 推奨ポジショニング 3 軸

1. **「LangGraph / Open WebUI が手薄な日本語 + 監査可能性」**
   - LangGraph には Approval Bus が無い (HITL checkpoint はある)
   - Open WebUI は audit ledger が弱い
   - FullSense は両方持つ
2. **「規制業界 PoC を 1 人で組める軽量さ」**
   - TIS / NTT / NEC / リコーが「PoC 環境」を提供しているが、これらは
     有償サービス
   - FullSense は OSS で同等の体験を提供
3. **「個人開発者・スモールチーム向けの on-prem AI baseline」**
   - 大企業向け = 大手の領域、無理に攻めない
   - 個人〜50 名チームを軸に

### 記事 2 (llgrow) の方向修正

調査の結果、**llgrow (収益化自動化) を Qiita 記事 2 にすると弱い**:
- 「収益化を自動化」は技術記事として薄い
- 「大手と直接競合する個人 OSS の現実」の方が話題性高い
- 「on-prem AI を 1 人で作る現実 (i7 mobile からの挑戦)」もよい

**新案**: 記事 2 は「**llgrow + FullSense の市場受容性ナイーブレポート**」.
- 大手競合の存在を honest disclosure
- 個人 OSS の生存戦略 (ニッチ / 設計パターン / 監査可能性)
- 「AI 開発環境がないところから始める個人開発者の現実」

これは [[feedback-benchmark-honest-disclosure]] と [[feedback-article-humor-style]]
の合わせ技で書ける.

### 短期 action

1. **記事 1** (M8.x マラソン): 公開可能、設計パターンで差別化
2. **記事 2** (新案): 市場現実 + 個人 OSS 生存戦略
3. **記事 3** (将来): llmesh / llove / lldesign / lltrade の cross-product
   利用シナリオ

### 中期 action

1. **「LangGraph 互換 backend」または「LangGraph + Approval Bus adapter」**
   を別 spinoff で出す → LangGraph community に乗る
2. **日本企業向け sub-component pitch** (TIS / NTT / NEC / リコー に「OSS
   ベース化」を提案)
3. **HITL OSS library** として Approval Bus を独立 PyPI 公開

## 関連

- `requirements_v0.9_growth_automation.md` — llgrow 要件 + リスク章
- `monetization_playbook_2026_05.md` — 収益化 10 チャネル実践
- `ai_dev_env_2026_05.md` — 開発環境投資
- portal `docs/spinoff_ideas_2026_05.md` — vertical カタログ
- memory: [[feedback-competitor-benchmark]] / [[project-llmesh-critical-review]] /
  [[project-30day-action-plan-2026-05]]

## Sources (web 調査)

- [50+ LLM Enterprise Adoption Statistics 2026 (index.dev)](https://www.index.dev/blog/llm-enterprise-adoption-statistics)
- [Executive Playbook to On-Premise LLM Deployment 2026 (accrets.com)](https://www.accrets.com/general/on-premise-llm-deployment/)
- [LLM Landscape 2026 EU Compliant (dev.to)](https://dev.to/blckalpaca/llm-landscape-2026-the-enterprise-decision-guide-eu-compliant-153l)
- [7 Agentic AI Trends 2026 (MachineLearningMastery)](https://machinelearningmastery.com/7-agentic-ai-trends-to-watch-in-2026/)
- [Open WebUI vs AnythingLLM vs LibreChat 2026 (toolhalla.ai)](https://toolhalla.ai/blog/open-webui-vs-anythingllm-vs-librechat-2026)
- [LangGraph vs CrewAI vs AutoGen 2026 (towardsai.net)](https://pub.towardsai.net/langgraph-vs-crewai-vs-autogen-which-ai-agent-framework-should-your-enterprise-use-in-2026-3a9ebb407b09)
- [Best Multi-Agent Frameworks 2026 (gurusup.com)](https://gurusup.com/blog/best-multi-agent-frameworks-2026)
- [TIS インテック ローカル LLM 導入支援 2026-01-29](https://www.intec.co.jp/news/2026/0129_1.html)
- [日経 インテック 記事](https://www.nikkei.com/article/DGXZRSP702443_Z20C26A1000000/)
- [リコー オンプレ LLM スターターキット 日経優秀製品賞](https://jp.ricoh.com/info/2026/0105_1)
- [Enforcing HITL Controls for AI Agents (prefactor.tech)](https://prefactor.tech/learn/enforcing-human-in-the-loop-controls)
- [HITL vs HOTL for AI Agents (waxell.ai)](https://www.waxell.ai/blog/human-in-the-loop-vs-human-on-the-loop-ai-agents)
- [HITL: A 2026 Guide to AI Oversight (strata.io)](https://www.strata.io/blog/agentic-identity/practicing-the-human-in-the-loop/)
- [HITL Governance for AI Agents (ClarityArc)](https://www.clarityarc.com/agentic-ai/human-in-the-loop-governance)
- [2026 年 4 月版 ローカル LLM 完全ガイド (Qiita)](https://qiita.com/yun_bow/items/3c920416555c8c31dfeb)
- [ローカル LLM (Ollama) で完全オフライン AI 開発環境を作る (Qiita)](https://qiita.com/miruky/items/026aeee6b59f78df5e9d)
- [2026 年のローカル LLM 事情を整理してみた (DevelopersIO)](https://dev.classmethod.jp/articles/local-llm-guide-2026/)

## Last updated

2026-05-19 — WebSearch 6 軸調査 + SWOT + 戦略提案. 記事 2 の方向修正案.
