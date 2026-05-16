---
layout: default
title: "Historical Reference — 金子勇 EDLA (1999) と Winny 思想"
---

# Historical Reference — 金子勇 EDLA (1999) と Winny 思想

> **位置づけ**: 本リポジトリ (llive / FullSense ™) の思想的源流の一つとして、
> 1999 年に金子勇氏が公開した **誤差拡散学習法 (EDLA)** と、後に同氏が手がけた
> **Winny (2002)** の P2P 分散思想を参照する。これらは llive の生物学的記憶
> モデル / APO / TLB と、llmesh の ICP (Idle-Collaboration Protocol) /
> distributed mesh 設計の **歴史的 prior art** として明示的に記録する。
>
> 本資料は **二次資料 / 参照記録** であり、当該成果物の license に依存しない
> 形 (URL 引用 + 要旨記述) で保持する。

## 一次情報の在り処

| 資料 | 一次 URL | Wayback (アーカイブ) |
|---|---|---|
| EDLA サンプルプログラム + 論文 | `http://homepage1.nifty.com/kaneko/ed.htm` (リンク切れ) | <https://web.archive.org/web/20070128235739/http://homepage1.nifty.com/kaneko/ed.htm> |
| BP 比較用サンプル | `http://homepage1.nifty.com/kaneko/bp.tgz` (リンク切れ) | 同上ページ内リンク |
| 論文 (改訂版) | `http://homepage1.nifty.com/kaneko/edla2.pdf` (556 KB, リンク切れ) | 同上ページ内 |

公開: 1999/07/12 初版 → 2000/01/04 最終更新 (8 改訂)。

## EDLA — Error Diffusion Learning Algorithm の要旨

金子勇氏が 1999 年に公開した **階層型ニューラルネットワークの教師あり学習
アルゴリズム**。Backpropagation (BP) の代替として提案された。

### 設計上の特徴 (アーカイブから読み取れる範囲)

1. **誤差を局所的に「拡散」させて学習** — BP の大域的逆伝播 (各層を遡って
   gradient を計算) を **局所演算に置き換える**。
2. **生物学的妥当性が高い** — 実際の神経細胞には back-propagation 機構が
   知られていない (Crick 1989 / Lillicrap 2020 等の long-standing 議論)。
   EDLA はその論点に対する 1 解。
3. **階層を「カレント型の一部」とみなす** — 階層構造を有向グラフの特例
   とすることで、recurrent と feedforward を統一的に扱える設計。
4. **トータルエラーを X11 でライブ可視化** — 学習過程を即時観測できる
   UX 思考が当時から徹底していた (現代の WandB / TensorBoard 相当の思想)。

### 著者の自評 (改訂履歴より)

> 「結局、好きなんだなぁ、神経の話」(1999/10/27 改訂)

短い記述だが、神経科学のモデル化を **個人プロジェクトとして長期的に**
取り組んでいたことが読み取れる。

## Winny 思想 (2002, 関連だが本ページの主題)

金子氏は 2002 年に **Winny** (Windows ネットワーク P2P ファイル共有
ソフトウェア) を発表。後の刑事訴追を経て 2011 年最高裁無罪確定。

Winny の技術的特徴:

1. **完全分散 / 中央サーバ不在** — 各ノードが peer として等価
2. **匿名化** — 通信経路をランダムに中継、発信者の特定を困難にする
3. **クラスタリング / 興味の近い peer 同士を発見** — 効率的探索
4. **キャッシュベース転送** — 各ノードが転送中ファイルを部分キャッシュ
5. **暗号化** — 通信内容の保護

## FullSense / llive / llmesh への影響

### llive 側 (memory + learning)

| FullSense 軸 | EDLA の寄与 |
|---|---|
| **5. 生物学的記憶モデル直接埋め込み** | EDLA は BP より生物学的妥当性高 → 学習則の有力候補 |
| **6. 形式検証付き promotion** | 学習則そのものを *promote 候補* として検証する観点 |
| **A-1 ResidentRunner / R5 idle work** | 局所学習は idle CPU で sparse に走らせやすい |
| **APO (Autonomous Performance Optimization)** | 「自分で学習則を選ぶ」自律性の延長線 |
| **TLB (Thought Layer Bridge)** | 多視点の誤差を局所拡散する考え方は Manifold Cache の局所近似と相同 |

### llmesh 側 (distributed mesh)

| FullSense 軸 | Winny の寄与 |
|---|---|
| **ICP (Idle-Collaboration Protocol)** | P2P 分散の **直系の精神的源流**。idle ノードが peer mesh に貢献 |
| **MI1 Substrate independence** | 単一 substrate に閉じない分散実装の前例 |
| **secure LLM hub** | 中央 hub と P2P mesh の併用設計 (現代では federated learning と共通) |
| **A.3 Knowledge autarky** | 完全分散なら主権を取り戻せる、という主軸 |

## 技術的に導入できる部分 (RFC へ橋渡し)

詳細は `docs/llmesh_p2p_mesh_rfc.md` (本セッションで併設) で議論。要点:

1. **P2P node discovery** — mDNS + DHT で peer LLM を発見
2. **クラスタリング** — capability (model size / domain / language) 近い peer
3. **匿名中継 (任意)** — TOR 風 onion routing で query を匿名化
4. **EDLA 学習則の試験** — `src/llive/learning/edla.py` を新設、BP と並走比較
5. **キャッシュ転送** — skill chunks の peer 間複製 (DTKR と相補)
6. **ゴシップ プロトコル** — state を eventual consistency で全 peer に伝播

## license / 倫理上の注意

- EDLA 論文 / コードの **license は不明** (1999 年公開、当時の慣例で
  「個人 web ページに置く = 学術参考用」)。**再配布は控える**、URL 引用のみ。
- Winny 技術それ自体は **合法** (最高裁無罪確定)。とはいえ、現代でも違法
  共有支援に転用しないよう、FullSense 系での P2P 設計は **目的を明示**
  (学習 / 推論協調 / 知識主権) し、コンテンツ流通には使わない。
- 著者への敬意: 本資料は技術史的記録として作成。批判的検討であって、特定の
  人物の遺志を勝手に代弁するものではない。

## 関連

- `docs/llmesh_p2p_mesh_rfc.md` — Winny 思想を LLMesh に技術導入する RFC
- `docs/fullsense_spec_eternal.md` §MI1 (substrate independence)
- `data/rad/neural_signal_corpus_v2/` — 神経モデル一般の RAD コーパス (補助)
- `data/rad/distributed_systems_corpus_v2/` — 分散システム一般 (補助)

## 参考: 後続研究 (BP 代替学習則)

EDLA に直接の影響を受けたか不明だが、同様の方向性として:

- **Target Propagation** (Bengio 2014, Lee et al. 2015)
- **Equilibrium Propagation** (Scellier & Bengio 2017)
- **Random Feedback Alignment** (Lillicrap et al. 2016)
- **Direct Feedback Alignment** (Nøkland 2016)
- **Predictive Coding** (Whittington & Bogacz 2017)
- **Local Learning Rules** (Hinton 2022 — Forward-Forward Algorithm)

EDLA は 1999 年公開、これら現代の代表的研究より **15〜20 年早い**。学術的
インパクトの認知は限定的だが、思想的優先権は明らか。
