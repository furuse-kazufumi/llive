<!--
title: i7 ノートで AI 開発しようとしたら NTT も NEC もリコーも本気で参戦していた件 ― FullSense の SWOT と個人 OSS 生存戦略
tags: AI,LLM,オンプレミス,OSS,キャリア
-->

# i7 ノートで AI 開発しようとしたら NTT も NEC もリコーも本気で参戦していた件 ― FullSense の SWOT と個人 OSS 生存戦略

> 何が起きたか 1 行で: 自宅の i7-1065G7 (mobile) + 16GB + Iris 内蔵 GPU で
> on-prem LLM フレームワークを書いていたら、いつの間にか大手 SIer が
> 同じ市場に大艦隊で来ていた。`pytest` を回す手が一瞬止まった。

---

## 0. 前置き — 環境を晒すという潔さ

私の開発機のスペックです。

```
CPU:  Intel i7-1065G7 @ 1.30GHz  (10th gen mobile / Ice Lake)
RAM:  15.7 GB
GPU:  Intel Iris Plus Graphics    (integrated)
Disk: D ドライブ 1340 GB free
```

Mac Studio M2 Ultra を持っていないどころか、外付け GPU すらありません。
[前夜の記事][prev] で書いた `1518 PASS` の COG-MESH framework は、すべて
CPU 推論の Ollama 3B でテストされています (LLM 接続は cloud API 経由)。

[prev]: https://qiita.com/furuse-kazufumi/items/cab6bb47a72ebedf5436

そんな個人開発者が「**FullSense ™** という on-prem AI ファミリー OSS を
作っています」と言うわけです。

人類はナメられるのに耐性がない動物だと言いますが、人類学者の証言を待つ
までもなく、私もすでに耐性が無い。

> **雑談 1**: 「on-prem」と打鍵するたびに、自宅のオンプレ機 (Iris 内蔵
> ノート) が「いやお前」と言ってくる気がする。プレミスがオンしていない。

---

## 1. 「他に誰がいるか」を調べたら、心が折れそうになった

今日 (2026-05-19)、半日かけて WebSearch で **「on-prem LLM、誰がやって
いるか」**を 6 軸で調べました。結論を 1 行ずつ:

### 1.1 グローバル: on-prem AI は **baseline 要件** に格上げ済

[Index.dev の調査][stat] (2026):
- on-prem 開放重みモデルは **18 倍安い** (1M tokens あたり、対 cloud)
- HITL は規制業界で **mandatory**
- 「**uncontrolled model access**」「**unlogged prompts**」「**absence of
  HITL**」は compliance risk
- [EU AI Act][eu_ai] と [NIST AI RMF][nist] が「**demonstrable HITL**」を
  明示的に要求

[stat]: https://www.index.dev/blog/llm-enterprise-adoption-statistics
[eu_ai]: https://www.strata.io/blog/agentic-identity/practicing-the-human-in-the-loop/
[nist]: https://www.waxell.ai/blog/human-in-the-loop-vs-human-on-the-loop-ai-agents

「demonstrable HITL」ってつまり**証明可能な人間関与**で、これは FullSense
の Approval Bus + SqliteLedger そのものなんです。市場としては大正解。
**ただしそれは大手も同じ正解にたどり着いているということ**でもある。

### 1.2 日本: 大手 SIer が **本気で**参戦している

- **TIS インテック** (2026-01-29): ローカル LLM 導入支援開始. PoC 環境を
  小規模で提供 [(プレスリリース)][intec]
- **NTT tsuzumi**: 軽量 + 日本語特化 + 金融/医療向け
- **NEC cotomi**: オンプレ対応 + 業務利用特化
- **リコー オンプレ LLM スターターキット**: 2025 年 **日経優秀製品最優秀賞**
  ([リコー側 IR][ricoh])

[intec]: https://www.intec.co.jp/news/2026/0129_1.html
[ricoh]: https://jp.ricoh.com/info/2026/0105_1

`日経優秀製品最優秀賞`。
私が `pytest -q` を回している横で、リコーは賞を取っていた。

> **雑談 2**: 日経優秀製品賞って 1958 年から続いている老舗の賞で、過去
> 受賞には FAX とかカラオケとか入っているやつ。そこに「オンプレ LLM」が
> 入ったのが 2025 年。歴史の進み方が早すぎる。

### 1.3 OSS UI 領域: Open WebUI 124K stars が支配

| ツール | GitHub stars |
|---|---|
| **Open WebUI** | **124,000+** |
| AnythingLLM | 54,000+ |
| LibreChat | 22,000+ |

私の llove (TUI 版) は、せいぜい数十 stars です。電卓の桁が変わっています。

### 1.4 OSS Agent framework: LangGraph が CrewAI を抜く

[Towards AI の比較記事][towardsai] (2026):
- **LangGraph** が早期 2026 で CrewAI を star で追い抜いた
- v0.4 で **HITL checkpoint** + state persistence + LangSmith 観測
- **production readiness 最高**

[towardsai]: https://pub.towardsai.net/langgraph-vs-crewai-vs-autogen-which-ai-agent-framework-should-your-enterprise-use-in-2026-3a9ebb407b09

LangGraph が HITL checkpoint を持っているということは、FullSense の
Approval Bus と機能的に**衝突**します。直接競合です。

### 1.5 Qiita: ローカル LLM 記事は伸びている (が入門系飽和)

[Qiita の人気記事を 10 件抜粋][qiita]:
- 「2026 年 4 月版 ローカル LLM 完全ガイド」
- 「Ollama で完全オフライン AI 開発環境を作る」
- 「ローカル LLM って難しそう ← 5 分で動きます」

[qiita]: https://qiita.com/yun_bow/items/3c920416555c8c31dfeb

入門系・比較系が中心. **設計パターン系・認知科学系には余地**.

### 1.6 HITL OSS ライブラリ: 不在

検索しても出てこない. [Prefactor][pref] / [OLOID][oloid] / [Strata][strata]
等の **商用 SaaS** が主. OSS は LangGraph に embed されている形のみ.

[pref]: https://prefactor.tech/learn/enforcing-human-in-the-loop-controls
[oloid]: https://www.oloid.com/press-releases/oloid-expands-its-vision-for-frontline-ai-governance-with-human-in-the-loop-controls
[strata]: https://www.strata.io/blog/agentic-identity/practicing-the-human-in-the-loop/

ここに**機会**があるかもしれない。Approval Bus を独立 PyPI で出すと。

> **雑談 3**: 「機会」って単語、就活セミナーで聞きすぎて以来、苦手な
> 単語ベスト 5 に入っている。でもここで「機会」と言わないと表現が
> 弾まないので、しょうがない、使う。

---

## 2. SWOT 分析 — Honest Disclosure で正直に

メンタル防衛のため、希望と絶望を 2x2 に並べます。

### Strengths (うちの強み)

- on-prem + HITL + audit を **2026 baseline 要件にフルカバー**
- 4 層メモリ + Cognitive Mesh = **学術的に独自の領域** (LangGraph に無い)
- Apache-2.0 + Commercial dual license (商用化道筋あり)
- 日本語ネイティブ開発者 + Honest disclosure 文化
- 単独で価値を持つ 3 製品 (independence principle、組合せで増幅)
- M8.x 完成で **1518 PASS の実装裏付け**

### Weaknesses (うちの弱み、目を背けるな)

- **認知度**: 大手 (NTT / NEC / リコー) と桁違い
- **営業力**: 1 人開発者は法人契約に弱い
- **信頼性**: production 実績の事例 **ゼロ**
- **開発体制**: バス係数 1 (私が風邪ひいたら開発停止)
- UI 競合 (Open WebUI 124K stars) との差別化が**説明しにくい**
- Agent framework 競合 (LangGraph) との差別化軸が**複雑**

「**バス係数 1**」というのはソフトウェア工学用語で、「**何人がバスに
轢かれたらプロジェクトが死ぬか**」の指標です。1 名 OSS は 1。
ちなみに Linux は推定 200+。差を感じる。

### Opportunities (機会)

- 規制業界の on-prem 需要が **急成長中**
- LangGraph / Open WebUI と**異なる軸** (認知科学 / 監査) のニッチ
- 日本企業向け on-prem ソリューションへの **sub-component 提供**
- **HITL OSS ライブラリの不在** (Approval Bus を spinoff PyPI)
- 個人開発者・スモールチーム向け軽量 PoC tool

### Threats (脅威、震える)

- 大手 SIer / メーカが本格営業 → 個人 OSS が pre-sales で勝てない
- **LangGraph + Anthropic Agents SDK が agent 市場を制圧する可能性**
- EU AI Act / 中国 AI 弁法等の規制で個人 OSS 配布が窮屈になる可能性
- AI 自動コンテンツ氾濫で記事 ROI 低下
- **大手モデル提供者 (Anthropic / OpenAI / Google) が自前で on-prem
  提供**を始めたら、OSS の優位性が消える

書いていて胃が痛い。

> **雑談 4**: SWOT 分析、本来「強み → 機会で攻め、弱み → 脅威に備える」
> 4 マスをぐるぐる読むやつ。でも 1 人 OSS の SWOT を書くと「弱み」が
> 「脅威」に直結して結局 1 マスを長時間眺めることになる。SWOT じゃなくて
> 「2x2 メンタルマット」と呼んだ方がいい。

---

## 3. 個人 OSS の生存戦略 — 3 軸の positioning

開き直りましょう。**正面突破は無理**です。
ニッチに 3 軸 positioning します。

### 3.1 「LangGraph / Open WebUI が手薄な日本語 + 監査可能性」

LangGraph の HITL は checkpoint であり、Approval Bus と異なる:
- LangGraph: 「途中で人間に処理権を渡す」モデル
- FullSense: 「**人間が決して関わらない処理を技術的に禁じる**」モデル

似てるようで違う. 後者は規制 → 監査 → 法廷で「人間関与を技術的に保証」
できる. 金融機関の compliance 要員にウケる。

Open WebUI は audit ledger が弱い (chat 履歴は残るが、approval ledger
ではない). FullSense の SqliteLedger は SOX 監査に耐えうる構造を持つ。

**日本語**は機能ではなく **態度**です. README / docs / Qiita / コメ返信
全てを日本語で書く. これだけで「**日本企業の現場担当者に近い**」立場を
取れる. NTT / NEC は法人語で語る. FullSense は現場語で語る. 立場が違う.

### 3.2 「規制業界 PoC を 1 人で組める軽量さ」

TIS / NTT / NEC / リコーが提供する PoC 環境は**有償サービス**です. 数百万
〜数千万円. これ、社内決済が通らない or 通すまでに 3 ヶ月かかる規模.

FullSense は OSS で同等の体験を提供できる:
- `pip install llmesh-suite` で 3 製品セットアップ (5 分)
- `python -m llive.cognitive_mesh.demo` で 10 機能体験 (1 分)
- `python -m llove.demo.cog_mesh_demo` で TUI 確認 (subprocess 化済)

「**社内決済を待たずに 5 分で PoC を組める個人 OSS**」 — 大手のサービス
が「3 ヶ月後の PoC キックオフ」を提案している間に、FullSense は「**昨日
動いた**」と言える.

### 3.3 「個人開発者・スモールチーム (~50 名) 向け on-prem AI baseline」

大企業向けは大手の領域. ターゲットを **個人 + 50 名以下チーム** に絞る:
- スタートアップ 30 名
- 大学研究室 10 名
- 個人事業主 1 名
- フリーランス連合 5 名

これらは **大手 SIer に発注すると割が合わない** 規模. でも on-prem AI は
やりたい. ここに OSS で寄り添うのが FullSense の現実的市場.

---

## 4. 「3 段ロケット設計」が個人 OSS で効く理由

[前夜記事][prev] で詳しく書いた「**skeleton → 本実装 → production wire**」
の 3 段ロケット設計. これが個人 OSS の生存戦略と密接に関わってます.

### 4.1 リソース制約の中で進む

大手 SIer は予算でゴリ押せる. 1 人開発者は時間と集中力が有限. **「3 段
に分けて毎段で出荷可能」**にすることで、途中で死んでも 1 段目までは残る.

私が今日 風邪をひいて寝込んでも、COG-MESH の skeleton は M8.0 まで終わって
います. これは「**バス係数 1 の OSS が積み残しを最小化する**」設計則として
他の 1 人 OSS にも勧めたい.

### 4.2 backward compatibility を技術的に強制する

```python
@dataclass
class TitleRecallPlanner:
    similarity_fn: Callable[[str, str], float] | None = None
    # None なら従来挙動 / 注入されれば新挙動
```

これで「**新機能追加で既存利用者を裏切らない**」を default にできる. 大手
SIer は「v2.0 で互換性切ります」を強行できるが、個人 OSS は信頼を失うと
即死. 既存利用者を絶対裏切らない設計則が**売り**になる.

### 4.3 cross-repo schema lock

llive ↔ llmesh ↔ llove の 3 リポを連携させた M8.1 では、両側 unit test
で schema を独立にロックした. これは microservice 系の人なら常識だが、
個人 OSS でこれをやると **「3 リポ間で勝手に drift しない」** という
信頼が積み上がる. 私が忘れても test が覚えている.

---

## 5. llgrow — 「補助線」として軽く触れる

ここまで読んだ人は気づいているはず. 「Approval Bus とか SqliteLedger とか
3 段ロケットとか、いいこと言ってるけど、開発する時間あんの?」

開発時間を AI で自動化するために、私は **llgrow** という補助線を引きました.

llgrow は要件レベルで:
- 記事 / 動画 / 配信 / コメント返信を **AI 下書き + 人間最終承認** で半自動化
- 効果測定を **llove の TUI dashboard** に統合
- スポンサー対応を **Approval Bus 経由で自動応答下書き**

つまり「**FullSense 自身を FullSense で運用する**」というメタな構図.
これ自体が「AI が AI を作る」の **自己言及的な検証ループ**になっていて、
honest disclosure (AI 自動生成と明記) を技術的に強制する設計を含む.

詳細は [requirements_v0.9 (リポ内)][reqv09] で書いた. 興味ある人だけ
読んでください. **本記事の主題ではない**.

[reqv09]: https://github.com/furuse-kazufumi/llive/blob/main/docs/requirements_v0.9_growth_automation.md

> **雑談 5**: 「自己言及的」って大学の論理学で習った時に「ラッセルの
> パラドックスがどうのこうの」と聞いて寝た記憶がある. でも実装してみると
> 「あ、これ普通にやれるな」と気づく. AI が AI を売る、AI が AI を運用
> する. 哲学者が寝てる間にエンジニアが現実化してしまった.

---

## 6. AI 開発環境投資の現実 — お互いの利益のために

「**i7 ノートで AI 書いてます**」と言うと「いやいやでも GPU は?」と
聞かれる. ありません. クラウド GPU で凌いでます.

[ai_dev_env_2026_05.md (リポ内)][env] にロードマップを書きました:

[env]: https://github.com/furuse-kazufumi/llive/blob/main/docs/ai_dev_env_2026_05.md

| Phase | 投資 | 内容 |
|---|---|---|
| 0 | ¥0 | Ollama 3B で CPU 推論 (今やってる) |
| 1 | ¥5-20k/月 | Together.ai / vast.ai でクラウド GPU 試用 |
| 2 Mid | ¥293,000 | RTX 4070 Ti SUPER 16GB BTO |
| 2 High | ¥625,000 | RTX 4090 24GB BTO |
| 2 Mac | ¥990,000 | Mac Studio M2 Ultra 192GB |
| 3 | ¥500k-1M | 専用サーバ + 副機 |

これを **どう捻出するか** が現実問題. リコーが日経優秀製品賞を取って
売上を立てている間、私はリソース捻出の方法を考えていた. それが llgrow.

> **雑談 6**: BTO を「Build To Order」って略すと知ってから、人生のあらゆる
> もの BTO じゃね? と思った. キャリアも人生も BTO. ただし発注主は自分で、
> 部品は時間と気力. 在庫切れが多い.

---

## 7. 教訓 — 個人 OSS で生き延びる 5 ヶ条

honest disclosure で書きます.

### 7.1 「正面突破」を最初から諦める

大手と同じ市場で同じやり方は無理. 上位 3% の作品を出すよりも、ニッチの
**自分しかいない場所** を見つける. FullSense なら「**監査可能性 + 認知
科学 + 日本語**」の 3 重ニッチ.

### 7.2 設計パターンを売る (機能ではなく)

機能で大手と勝負しても勝てない. **「**3 段ロケット設計**」「**Approval
Bus**」「**Cognitive Mesh 思考因子**」** といった設計パターン・概念で
差別化. これは大手が真似しても**「コア概念は元著者にある」**ことが残る.

### 7.3 honest disclosure を最強の武器にする

[[feedback-benchmark-honest-disclosure]] で内訳を晒す習慣を作ると、
「**信頼できる個人 OSS**」というブランドが立ち上がる. 大手は法務確認で
正直になれない. 個人 OSS の最大の武器.

### 7.4 「お互いの利益のために」を真面目に書く

FullSense は **個人開発者** + **AI** の 2 者協働. 大手 SIer は人間の
社員総動員. 個人 OSS は「**AI が読みやすい**」「**AI が貢献しやすい**」
設計を意識的にやると、長期的に AI 側からの contribution も入る. 私が
寝ている間に AI が PR を投げてくる時代は、たぶん 2027 年.

### 7.5 「**バス係数 1**」を直視する

私が風邪ひくと開発が止まる. 「co-maintainer 探す」「OSS Conservancy
加盟」「Foundation 化」のどれかは中期で着手しないと、せっかくの設計が
霧散する. これも honest disclosure としてここに書く.

---

## 8. 次の一歩 (実務)

### 今週

- [ ] **個人事業主 開業届** を出す (e-Tax で 15 分、無料、青色申告承認も同時)
- [ ] **GitHub Sponsors waitlist** 登録
- [ ] **Buy Me a Coffee** アカウント作成
- [ ] **商標出願** (オンライン弁理士 Toreru / Cotobox で 9 類のみ ¥48k)

### 今月

- [ ] note 有料記事 1 本 (FullSense 全体像、¥980)
- [ ] Zenn Book 目次 (1 冊目)
- [ ] LangGraph community に Approval Bus adapter 提案
- [ ] **NTT tsuzumi / NEC cotomi のスタータキットに OSS sub-component 提案** (将来)

### 6 ヶ月後

- [ ] **GPU マシン投資** (Phase 2 Mid ¥293k or Phase 2 High ¥625k)
- [ ] **Commercial license 1 件目** (スタートアップ向け ¥50k/年〜)
- [ ] **法人成り** (合同会社 ¥6 万) — 売上 ¥500 万超え時

---

## 9. おわりに — 自分への手紙

私はこれから何を作るかを決めるとき、いつも「**お互いの利益のために**」
という言葉を思い出すことにします. 私と、私の隣で動いている AI と、
こっそり読んでくれた読者と、(将来) 法人化したときの最初の顧客と.

大手のロードマップにある「**金融機関 100 社導入**」は私には書けない. でも
「**個人事業主 10 名チームで動く on-prem AI**」は書ける. その上に、
今は孤独だが、いつか「**この個人 OSS が大手を補完する形でエコシステムを
作る**」を目指したい. それが見えたとき、私のバス係数は 1 ではなくなって
いるはず.

`pip install llmesh-llive` — 試してくれた人、ありがとうございます.

---

## 関連

- 前夜記事: [1 セッションで +154 テスト ― COG-MESH 全件を 3 段ロケット
  設計で踏み抜けた話](https://qiita.com/furuse-kazufumi/) (公開後リンク差し替え)
- リポ: <https://github.com/furuse-kazufumi/llive>
- portal: <https://furuse-kazufumi.github.io/fullsense/>
- 市場調査レポート (詳細): [`market_research_2026_05_19.md`][mr]
- spinoff カタログ: [`spinoff_ideas_2026_05.md`][si]

[mr]: https://github.com/furuse-kazufumi/llive/blob/main/docs/market_research_2026_05_19.md
[si]: https://github.com/furuse-kazufumi/fullsense/blob/main/docs/spinoff_ideas_2026_05.md

---

**Co-Authored-By**: Claude Opus 4.7 (1M context) ― 本記事は AI 協働で
執筆. honest disclosure として明示.

**🤖 Generated with [Claude Code](https://claude.com/claude-code)**

## Sources (調査根拠)

- [50+ LLM Enterprise Adoption Statistics 2026 (index.dev)](https://www.index.dev/blog/llm-enterprise-adoption-statistics)
- [Open WebUI vs AnythingLLM vs LibreChat 2026 (toolhalla.ai)](https://toolhalla.ai/blog/open-webui-vs-anythingllm-vs-librechat-2026)
- [LangGraph vs CrewAI vs AutoGen 2026 (Towards AI)](https://pub.towardsai.net/langgraph-vs-crewai-vs-autogen-which-ai-agent-framework-should-your-enterprise-use-in-2026-3a9ebb407b09)
- [TIS インテック ローカル LLM 導入支援 2026-01](https://www.intec.co.jp/news/2026/0129_1.html)
- [リコー オンプレ LLM スターターキット 日経優秀製品賞](https://jp.ricoh.com/info/2026/0105_1)
- [Enforcing HITL Controls for AI Agents (Prefactor)](https://prefactor.tech/learn/enforcing-human-in-the-loop-controls)
- [2026 年 4 月版 ローカル LLM 完全ガイド (Qiita)](https://qiita.com/yun_bow/items/3c920416555c8c31dfeb)
