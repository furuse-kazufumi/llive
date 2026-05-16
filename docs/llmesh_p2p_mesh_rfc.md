---
layout: default
title: "RFC — Winny 思想を LLMesh に技術導入する P2P mesh 設計"
nav_order: 80
---

# RFC — Winny 思想を LLMesh に技術導入する P2P mesh 設計

> Status: **Draft** (2026-05-16). FullSense umbrella の `llmesh` 製品ライン
> に対し、金子勇 Winny (2002) の P2P 分散思想を起点に **technical
> introduction proposal** を整理する RFC。実装着手は llmesh v2.0 系を想定。
>
> 一次資料: [docs/references/historical/edla_kaneko_1999.md](references/historical/edla_kaneko_1999.md)

## 背景 (なぜ今 P2P か)

llmesh v1.x は **オンプレ MCP hub** として設計されており、構造上 **中央
集権** (1 hub, n client)。これは中小企業のオンプレ運用や個人開発機では
合理的だが、以下のユースケースで限界が出る:

1. **複数 home / 複数事業所** — それぞれ独立した hub を運用すると knowledge
   が分散しコラボが進まない
2. **idle 機の有効活用** — 多くの家庭・小規模オフィスにアイドル中の PC が
   存在する (llive ICP §R5 と整合)
3. **知識主権 (autarky)** — 中央 hub が落ちると全停止、政治・経済リスクの
   集中
4. **連合学習** — 各 peer のローカルデータを互いに共有せず、学習結果のみを
   共有する設計の需要 (GDPR / HIPAA / 業界規制)

Winny の P2P 分散思想は **2002 年時点で既にこれらを技術的に解いていた**。
ただし当時の文脈は ファイル共有、現代の文脈は LLM 推論 / 学習。**目的は
完全に違う** が、**プロトコル設計の知見は転用可能**。

## 既存資産との関係

| 層                    | 既存 (v1.x)                      | 本 RFC で拡張する部分                |
|-----------------------|-----------------------------------|--------------------------------------|
| Hub topology          | 1 hub, n client                   | mesh-of-hubs (各 hub が peer)        |
| Discovery             | static config                     | mDNS + DHT (Kademlia)                |
| Routing               | direct hub → client               | overlay routing (中継 1〜3 hop)      |
| Privacy               | TLS + audit chain                 | onion routing (optional)             |
| Knowledge sharing     | manual import_rad.py              | skill chunk replication (DTKR 連動)  |
| Learning              | (none in v1.x)                    | local learning rules (EDLA 候補)     |
| Coordination          | (none in v1.x)                    | gossip + consensus                   |

## 6 つの技術導入候補 (優先度順)

### 1. P2P Node Discovery (priority HIGH)

**Why**: 中央 registry なしで peer LLM hub を発見する。これがあれば残り
の機能 (sharing / routing / learning) が成立する。

**How**:

- **mDNS** (Multicast DNS) — 同一 LAN 内の peer を `_llmesh._tcp.local`
  service として広告。Python `zeroconf` パッケージで実装可。
- **DHT (Kademlia)** — 広域インターネット越しの peer 発見。`kademlia`
  Python パッケージ or 自前実装。
- **設定 fallback** — `~/.llmesh/peers.yaml` で静的 bootstrap peer を指定。

**Spec 上の根拠**: ICP (Idle-Collaboration Protocol) の §1 idle 検出 と
セットで動く。

```mermaid
flowchart LR
    LH1[Local hub A]
    LH2[Local hub B]
    LH3[Local hub C]
    DHT[DHT bootstrap node<br/>(任意)]
    LH1 <-->|mDNS LAN| LH2
    LH1 <-->|Kademlia| DHT
    LH3 <-->|Kademlia| DHT
```

### 2. Capability-aware Clustering (priority HIGH)

**Why**: 全 peer に均一にブロードキャストするのは O(n²) で非効率。peer
ごとに得意分野が違うので、**近い capability の peer 同士でクラスタ** を
作る (Winny の "クラスタリング" 概念の再導入)。

**How**:

- 各 peer が `capabilities` を宣言:
  ```yaml
  capabilities:
    model_size: 7B
    domains: [code, math, ja_law]
    languages: [ja, en]
    gpu_vram_gb: 12
    online_hours: [9..18 JST]
  ```
- DHT key は capabilities の hash 部分集合 → 同 cluster 内で発見しやすい
- Query 時に capability matching score でルーティング

### 3. Skill Chunk Replication (priority MEDIUM, DTKR と連動)

**Why**: DTKR (Disk-Tier Knowledge Routing) で skill = 1 file。これを
**peer 間で複製** すれば、片方のノードがダウンしても可用性維持。Winny の
キャッシュ転送と直系。

**How**:

- 1 skill chunk = 10〜50 KB の text (DTKR 仕様準拠)
- BitTorrent 風の merkle tree で integrity check (SHA-256)
- 各 peer は LRU + popular skill のみ保持 (full mirror は不要)
- skill version は signed (`INTEGRITY.json` 流用)

**注意**: 著作権付き素材は当然対象外。FullSense 系で扱う skill は **OSS
ライセンス済または合法的再利用可能** なものに限定する。

### 4. Onion Routing (priority LOW, optional)

**Why**: peer 間 query 経路を匿名化したいケース (e.g. 法務相談、医療
プライバシ、競合分析)。

**How**:

- 3 hop relay (entry / middle / exit) で発信 peer を秘匿
- 各 hop で 1 層復号 (RSA / Curve25519)
- TOR 風だが mini-scale (peer 数百〜数千)
- **取扱注意**: 違法用途への流用を防ぐため、デフォルト OFF + 用途明示
  (`policy.yaml` で `allow_onion: false` がデフォルト)

### 5. EDLA-based Local Learning (priority MEDIUM, llive 連動)

**Why**: 各 peer がローカルデータで継続学習し、**学習結果 (Δ weight or
skill chunk) のみ** を peer に共有する federated learning 風アーキテクチャ。
EDLA (BP 代替) は **局所演算で完結する** ので peer ごとに独立に走らせやすい。

**How**:

- `src/llive/learning/edla.py` を新設 (実装スケッチは別 RFC で詳細化)
- 各層の更新は誤差を局所拡散させて完結 (BP の全層逆伝播不要)
- 学習結果は signed `weight_delta_<peer_id>_<round>.safetensors` として
  peer 間で交換
- Aggregation は FedAvg 風の重み付き平均 or その他 (TBD)
- Hub 側で SHA-256 audit chain に commit、原データの逆推定を防ぐ DP-SGD
  (Differential Privacy) も併用検討

### 6. Gossip Protocol + Eventual Consistency (priority MEDIUM)

**Why**: peer 間で状態 (peer list / skill version / approval ledger
の transient state) を eventual consistency で伝播。中央 hub なしで
state convergence。

**How**:

- SWIM 風 (Lifeguard / memberlist) または HyParView
- 各 peer は K (= 3〜5) 個の peer に periodic に push
- conflict resolution は last-writer-wins or CRDT (TBD)
- 既存 SqliteLedger に gossip-sync 層を追加

## 実装ロードマップ

| Phase | 内容                                              | 目標 release |
|-------|---------------------------------------------------|--------------|
| **0** | RFC 確定 (本書) + 反対意見の集約                  | v0.6.x (now) |
| **1** | mDNS discovery 実装 + LAN demo (2 peer)           | v0.7.0       |
| **2** | DHT (Kademlia) + capability clustering            | v0.8.0       |
| **3** | skill chunk replication (DTKR と統合)             | v0.9.0       |
| **4** | gossip protocol + eventual consistency            | v0.10.0      |
| **5** | EDLA learning rule の試験 + federated PoC         | v0.11.0      |
| **6** | onion routing (optional) + DP-SGD                  | v0.12.0      |
| **GA**| v2.0 として安定化 + commercial license の対象      | v2.0.0       |

## 倫理 / 法的注意

- **目的の明示**: 本プロトコルは **学習 / 推論協調 / 知識主権** が目的で
  あり、著作権侵害素材の P2P 流通には使用しない。`AUP.md` (Acceptable
  Use Policy) を別途整備。
- **コンテンツモデレーション**: §F5 ethical hard-filter の peer 間版を
  実装。違反 peer は cluster から自動排除。
- **法域** (jurisdictional reach): 各 peer の所在国の法に従う。商用利用
  時は地域 deployment ガイドを提供。

## 評価指標 (KPI for the mesh)

| 指標                            | 目標 (v2.0)                 |
|---------------------------------|------------------------------|
| LAN discovery latency           | < 200 ms                     |
| DHT lookup latency (50% tile)   | < 2 s                        |
| skill chunk replication success | > 99 %                       |
| federated round time            | < 60 s (10 peer, 7B model)   |
| node churn 耐性                 | 50 % churn でも query 続行可 |

## 関連

- [docs/references/historical/edla_kaneko_1999.md](references/historical/edla_kaneko_1999.md) — 歴史的参照
- [docs/fullsense_spec_eternal.md](fullsense_spec_eternal.md) §MI1 / §ICP
- `src/llive/idle/` (将来) — ICP の OS 別 idle 検出
- `src/llive/mesh/` (将来) — peer registry / dispatcher / consensus

## 想定 FAQ

**Q. Winny の前科イメージは商用展開で不利では?**
A. プロトコル設計上の知見と、当該実装の社会的扱いは別問題。最高裁無罪
確定 (2011) を踏まえ、技術的優先権を明示しつつ、用途を学習 / 推論協調に
限定するのが妥当。AUP で明示。

**Q. 連合学習なら既存の Flower / PySyft で良いのでは?**
A. それらは学習レイヤのみ。本 RFC は **discovery + clustering + routing +
sharing + learning + consensus** を 1 つの mesh プロトコルとして統合する点が
差別化。Flower 等は library として組込み候補。

**Q. P2P って GDPR / HIPAA と相性悪いのでは?**
A. データそのものは共有しない (EDLA / DP-SGD で学習結果のみ共有)。原データ
は各 peer のローカルに留まる。これが federated learning の本懐。

**Q. EDLA を本当に採用する?**
A. v0.11.0 時点で BP との parity 比較。EDLA の精度 / 速度 / 生物学的妥当性
が現代 SoTA (Forward-Forward 等) と並ぶか劣るか、定量評価後に判断。
歴史的経緯から候補に挙げているが盲信はしない。
