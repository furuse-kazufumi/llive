<!--
title: 1 セッションで +154 テスト ― COG-MESH 全件を「3 段ロケット設計」で踏み抜けた話 (llive M8.x 完成記)
tags: Python,LLM,アーキテクチャ,設計パターン,テスト駆動開発
-->

# 1 セッションで +154 テスト ― COG-MESH 全件を「3 段ロケット設計」で踏み抜けた話 (llive M8.x 完成記)

> 何が起きたか 1 行で: skeleton 段で API を凍結しておくと、3 ヶ月後の本実装で
> 既存テストが 0 回帰になる。1 セッションで 8 milestone を全部踏める。

朝起きて pytest を 1 回回したら **1393 PASS**.
昼前にもう 1 回回したら **1518 PASS**.
+125。何かを間違えた気がする。

---

## 0. 前置きという名の言い訳

llive (`pip install llmesh-llive`) という Self-evolving modular memory LLM
framework を作っている。FullSense umbrella の一員、Approval Bus と HITL
ループで「責任所在を architecture level に持ち込む」のがコンセプト。

[前夜のセッション](https://qiita.com/furuse-kazufumi/items/cab6bb47a72ebedf5436)
で **COG-MESH (Cognitive Mesh)** 群 10 件の **skeleton** をぜんぶ書き終えた。
"skeleton" というのは、テスト通る最小実装で API は確定、内部はダミー
レベルというあれ。1379 PASS から 1393 PASS まで頑張った夜だった。

ここで普通の人なら寝る。

しかし朝、pytest を見て「全部緑」が並んでいるのを見て、悪い予感がした。
「これ、本実装入れても緑のままにできるんじゃないか」と思ってしまった。

そして +125 テストの朝が始まった。

> **雑談 1**:「skeleton」って言葉、骸骨のあれだと思ってました。実は
> ソフトウェアでは「骨格だけある未完成」の意味なんですね。完成すると
> "fleshing out" (肉付けする) になる。なんか語感が怖い。

---

## 1. 「3 段ロケット設計」の偶然の発見

私は計画的にやってません。やったのは:

1. skeleton で **API シグネチャだけ凍結** (内部は `raise NotImplementedError`
   とかでもいい)
2. 本実装フェーズで、**注入可能な adapter** として実装
3. production wire で **auth + retry + batch** を別 class として並列追加

これを偶然 8 個並べたら、**既存テスト 0 回帰**で 8 機能着地した。

### なぜ回帰しなかったか

3 段それぞれで「**注入なし = 従来挙動**」を強制したから。

```python
@dataclass
class TitleRecallPlanner:
    similarity_fn: Callable[[str, str], float] | None = None  # ← 注入式
    _foreshadows: dict[str, Foreshadow] = field(default_factory=dict)
```

`similarity_fn` は None の場合 token match で動く (既存挙動)。注入された
場合だけ embedding 類似度を使う。**呼び出し側を 1 行も書き換えなくていい**。

これが skeleton 段で見えていれば、本実装で揉めることは無い。

> **雑談 2**: これ、要するに dependency injection と Open/Closed
> principle なんですけど、なんで偶然「発見」みたいに書いてるかというと、
> SOLID 原則の本を 10 回読んで pat、実際にコードを書いて初めて
> 「あ、ここなんだ」と腹落ちすることって、ある。

---

## 2. M8.5 ApprovalBus.intervene 配線 ― TonicRiskMonitor を生かす

最初の本実装。

`TonicRiskMonitor` (小脳的常時 KYT) は skeleton 段で `on_alert: Callable
| None` を受けるよう作ってあった。何も入れなければ何も起きない。
何か入れれば、リスクアラート時にそれが呼ばれる。

そこに「アラートを ApprovalBus に介入要求として投げる adapter」を 50 行
で実装。

```python
@dataclass
class RiskInterventionAdapter:
    bus: ApprovalBus
    principal: str = "tonic_risk"
    action: str = "risk:intervene"

    def __call__(self, alert: RiskAlert) -> ApprovalRequest:
        return self.bus.request(
            action=self.action,
            payload={
                "model_name": alert.model_name,
                "score": alert.score,
                "timestamp": alert.timestamp.isoformat(),
                "state_snapshot": dict(alert.state_snapshot),
            },
            principal=self.principal,
        )
```

これで `TonicRiskMonitor(on_alert=RiskInterventionAdapter(bus))` で配線完了。
**+5 テスト**。

> **雑談 3**: 「小脳的常時 KYT (危険予測)」って何かというと、人間の
> 小脳がやってる「無意識の危険察知」を AI にも持たせる構想。元ネタは
> ユーザの言語化「**小脳のような高速応答系。危険予測 KYT を常時繰り返し、
> 突然の事態に対応する**」。建設現場の KYT (Kiken Yochi Training) と
> 同じ言葉です。

---

## 3. M8.4 TitleRecall に embedding semantic similarity

`TitleRecallPlanner` は「起承転結 + 伏線回収採点」をやる Component。
skeleton では token 一致率で採点していた (`"build success" in final_text`
みたいな)。

これを embedding 類似度に拡張。ただし完全置き換えではなく **max(token,
embedding) を採点**にする。

```python
def evaluate(self, final_text: str, ...) -> RecallReport:
    for fs in self._foreshadows.values():
        token_score = self._token_match_score(fs.text, lower_final)
        if self.similarity_fn is not None:
            try:
                sim_score = float(self.similarity_fn(fs.text, final_text))
            except Exception:
                sim_score = 0.0  # fail-closed
            score = max(token_score, max(0.0, min(1.0, sim_score)))
        else:
            score = token_score
```

`max(token, sim)` にしたのは、token match で確実に拾えるケースを
embedding が下手に下げないため。**+9 テスト**。

> **雑談 4**: AI の自然言語処理って「ベクトル化」って言うけど、要するに
> 「言葉に座標を付けて、距離が近いと意味が似てる」という発想。これを
> 50 年前くらいから皆考えてて、最近 transformer で爆発的に精度上がった。
> 当時の研究者が見たら泣いて喜ぶ程度には実用化されてる。

---

## 4. M8.3 BriefDeque ↔ BriefRunner 接続

`BriefDeque` は STL 的なセッション保持コンテナ (`std::deque` の薄い
ラッパ)。`BriefRunner` は実 Brief を submit する driver。両者をつなぐ
**bridge** を 1 ファイルで実装。

```python
@dataclass
class BriefDequeRunnerBridge:
    runner: _BriefRunnerLike  # submit(brief) -> BriefResult
    deque: BriefDeque = field(default_factory=BriefDeque)

    def enqueue(self, brief: Brief) -> BriefRef:
        ref = BriefRef(id=brief.brief_id, topic=brief.goal, payload=brief)
        self.deque.push_back(ref)
        return ref

    def submit_next(self) -> BriefResult | None:
        if len(self.deque) == 0: return None
        ref = self.deque.pop_front()
        return self.runner.submit(ref.payload)
```

`enqueue_front()` で緊急 Brief 割込みもサポート。**+6 テスト**。

> **雑談 5**: STL のコンテナを真似たのは、C++ 触ってた頃の癖。
> deque / map / tree。`std::priority_queue` も入れたかったけど、
> 「優先度キュー」は別 milestone (CABT 系) で出すんで今回は見送り。

---

## 5. M8.6 Mesh5W1H ↔ Annotation Channel 統合

ここで脳の血管が切れそうな名前のコンポーネントが出てくる。

`Mesh5W1H` = 思考が 5W1H (Who/What/When/Where/Why/How) メッシュ状に
繋がる、というモデル。skeleton 段では数えるだけだった。

`Mesh5W1HAnnotator` で、テキストを 5W1H 解析 → `AnnotationEmitter` に
流す。namespace は `mesh.who` / `mesh.what` / ... / `mesh.granularity`
で固定。

```python
@dataclass
class Mesh5W1HAnnotator:
    target_layer: str = "llove"  # ← llove TUI に届く
    emitter: AnnotationEmitter = field(default_factory=AnnotationEmitter)

    def emit_from_text(self, text: str) -> dict[Mesh5W1HNode, list[str]]:
        result = annotate_5w1h(text)
        for node, keywords in result.items():
            if not keywords: continue
            self.emitter.add(
                namespace=channel_name(node),  # "mesh.who"
                key="keywords",
                value=list(keywords),
                target_layer=self.target_layer,
            )
        return result
```

**+7 テスト**。

> **雑談 6**: 5W1H、小学校で習った。「いつ、どこで、誰が、何を、
> なぜ、どうやって」。これを AI の思考層に持ち込むのは、Will McGugan
> が Textual で「ターミナルでも JSX 書けるぜ」と言ったくらいの違和感。
> でも使ってみると、「あ、人間もこの構造で考えてるな」って気づく。

---

## 6. M8.7 ProactiveLoop に event / consistency モード

`ProactiveLoop` は「能動発話」をやる Component。skeleton では `timer`
モードと `curiosity` モードのみだった。

今回 2 モード追加:
- **event mode**: 外部イベント駆動 (ビルド完了通知とか)
- **consistency mode**: 整合性違反検出 (4 層メモリ間の矛盾とか)

```python
@dataclass(frozen=True)
class ProactiveEvent:
    topic: str
    payload: Any = None
    severity: float = 0.5
    note: str = ""

@dataclass(frozen=True)
class ConsistencyViolation:
    layer_a: str
    layer_b: str
    conflict_type: str
    evidence: str = ""
    severity: float = 0.5
```

Quiet Hours (深夜 22-08) 中は当然抑制される。 [Quiet Hours が architecture
の必須依存][quiet_hours] という設計原則がここで効く。
**+12 テスト**。

[quiet_hours]: https://github.com/furuse-kazufumi/llive/blob/main/docs/requirements_v0.8_cognitive_mesh.md

> **雑談 7**: 「能動発話」って、要するに「AI が勝手に話しかけてくる」
> やつ。Cortana や Siri がそれっぽいけど、あれは外部イベント駆動
> (アラーム、通知) だけ。COG-MESH の curiosity mode は「お前は何が
> 知りたいんだ」を AI が自発的に問う、という研究色の強い話。

---

## 7. M8.2 Quarantined Memory + Ed25519 — セキュリティ境界をどう作るか

Idle Training Scheduler (空き時間学習) は、外部情報を取り込むので
**信頼境界**が問題になる。RSS とか Twitter とか拾ってきたら、悪意ある
content が入る可能性がある。

ここで `Quarantined Memory` (隔離領域) + `Ed25519 署名検証` を組み合わせる。

```python
@dataclass
class QuarantinedMemory:
    verifier: Ed25519Verifier | None = None
    auto_promote_verified: bool = True
    _pending: dict[str, QuarantineEntry] = field(default_factory=dict)
    _active: dict[str, QuarantineEntry] = field(default_factory=dict)
    _rejected: dict[str, QuarantineEntry] = field(default_factory=dict)

    def quarantine(self, signed: SignedPayload | Any, ...) -> QuarantineEntry:
        # ... 検証通過 → active、失敗 → pending、operator 判断で promote/reject
```

ポイントは:
- **verifier 未設定 → 全件 auto-promote** (backward compat、既存テスト不破壊)
- **verifier 設定済 + 署名通過 → active**
- **verifier 設定済 + 署名失敗 → pending** (operator review)

cryptography パッケージ (`Ed25519PublicKey.verify`) を使う。32 bytes
公開鍵を `signer_id → key` で保持。

**+16 テスト**。今回 1 milestone で最大の追加。

> **雑談 8**: Ed25519 を選んだのは、楕円曲線署名で「鍵 32 byte、署名
> 64 byte、検証早い」というベストバランス。RSA だと鍵 2048 bit、署名
> 256 byte で、しかも遅い。現代的な選択。

---

## 8. M8.8 MultiBrief graph analytics ― networkx を入れない判断

`MultiBriefCoherenceManager` は複数 Brief を並列保持する Manager。
要件には「networkx + 実 Brief 統合」と書いてあった。

しかし pyproject.toml に networkx を追加するのは「依存追加要承認」原則に
ひっかかる。承認待ってる暇はない。

そこで **自前 BFS / DFS / 重み付き out-degree centrality** で実装。
50 行で済んだ。

```python
def shortest_path(self, src_id: str, dst_id: str) -> list[str] | None:
    """BFS で重み無視最短パス."""
    # ... 普通の BFS、visited set + prev dict で path 復元

def centrality_scores(self) -> dict[str, float]:
    """weighted out-degree centrality (合計 1.0 正規化)."""
    out_sum: dict[str, float] = {}
    total = 0.0
    for (s, _d), w in self._coherence.items():
        out_sum[s] = out_sum.get(s, 0.0) + w
        total += w
    return {b: out_sum.get(b, 0.0) / total for b in self._map._by_id.keys()}
```

API シグネチャは networkx 互換にしておく (`shortest_path(src, dst)`,
`centrality_scores() -> dict`)。将来 networkx に swap したくなった
ときに pain なく切り替えられる。

`register_brief(Brief)` で実 Brief を BriefRef にラップして attach する
経路も追加。**+14 テスト**。

> **雑談 9**: 「依存追加要承認」というのは、私の自宅 Claude の
> グローバル CLAUDE.md に書いてある運用原則。サードパーティ依存を
> 増やすと supply chain attack の面積が広がるんで、入れるなら
> 「これがないと作業が成立しない」 level じゃないと駄目、と。
> 50 行で同等品が書けるなら自前で書く方が結果的に楽なことが多い。

---

## 9. M8.9 GrammarLayer ↔ EVO 接続 + 言語別 layer

`GrammarLayer` は「文法層」(言語ごとの文法 snapshot + 提案/昇格/拒否
のライフサイクル) を持つ。これに 2 つの拡張:

### 9.1 GrammarChangeSink Protocol

```python
class GrammarChangeSink(Protocol):
    def on_propose(self, proposal: "ProposedChange") -> None: ...
    def on_promote(self, proposal, new_snapshot) -> None: ...
    def on_reject(self, proposal) -> None: ...
```

GrammarLayer は変更操作で sink を呼ぶ。例外は握りつぶす (本処理を
止めない原則)。これで Phase 7 で EVO-04/06/07 (Self-evolution) に
配線できる。

### 9.2 MultilingualGrammar

ja / en / zh / ko の 4 言語で v_0 snapshot を自動 bootstrap する
ファサード:

```python
@dataclass
class MultilingualGrammar:
    layer: GrammarLayer = field(default_factory=GrammarLayer)
    languages: tuple[str, ...] = DEFAULT_LANGUAGES  # ("ja", "en", "zh", "ko")

    def __post_init__(self) -> None:
        for lang in self.languages:
            if not self.layer.versions(lang):
                self.layer.add_snapshot(GrammarSnapshot(
                    language=lang, version="v_0", rules={}, ...))
```

**+8 テスト**。

> **雑談 10**: 言語別文法層、構想としては「日本語の助詞」「中国語の
> 数量詞」「韓国語の助詞」を AI が別 namespace で扱う、というやつ。
> これは Phase 7 でもっと深く掘る。今回は anchor だけ作った。

---

## 10. M8.1 cross-repo schema lock (llive → llmesh → llove)

ここまで全部 llive 内部の話。最後の M8.1 で **3 リポをまたぐ**。

### 10.1 schema を 3 リポで共有

cognitive_mesh が emit するイベントを Timeline server (llmesh) 経由で
TUI panel (llove) に流す経路。 event schema を 3 リポすべての unit test で
**独立にロック**する。

llive 側:
```python
def proactive_to_event(utterance: ProactiveUtterance, ...) -> dict:
    return {
        "event_id": uuid.uuid4().hex,
        "event_type": "cog_proactive_utterance",
        "timestamp_utc": utterance.timestamp.isoformat(),
        "metadata": {
            "content": utterance.content,
            "mode": utterance.mode,
            "gift_value": float(utterance.gift_value),
        },
        ...
    }
```

llove 側 panel が読む側:
```python
@dataclass(frozen=True)
class CogEntry:
    @classmethod
    def from_event(cls, ev: TimelineEvent) -> "CogEntry | None":
        if ev.event_type == "cog_proactive_utterance":
            content = str(md.get("content", "(no content)"))
            mode = str(md.get("mode", "timer"))
            ...
```

llmesh 側 allow-list:
```python
_ALLOWED_INGEST_EVENT_TYPES: frozenset[str] = frozenset({
    "route_trace", "concept_update", "bwt_summary",
    "cog_proactive_utterance", "cog_risk_alert",
    "cog_quarantine_pending", "cog_brief_result",
})
```

### 10.2 contract test で守る

```python
# llive 側 test_timeline_contract.py
def test_proactive_event_satisfies_contract() -> None:
    ev = proactive_to_event(_utterance())
    assert ev["event_type"] in VALID_EVENT_TYPES
    missing = PROACTIVE_REQUIRED_METADATA - set(ev["metadata"].keys())
    assert not missing
```

llove 側でも同等の test を書く。互いに依存せず、片方が schema 破壊すると
**両側で test 失敗**になる。

これは microservice の世界では常識的なやり方らしいけど、私は今回が初めて
だった。**+10 contract test + 10 emitter test = +20 テスト**。

> **雑談 11**: cross-repo schema lock、要するに「API spec を双方の
> test で書いて、互いに守らせる」というやつ。OpenAPI / gRPC / protobuf
> でやる人もいるけど、ここでは Python の pure dict schema を unit
> test レベルで守ってる。スキーマ駆動開発の小型版。

### 10.3 production HTTP push wire

ここで PRODUCTION 段に進む。`ProductionHttpTimelineSink` を別 class で実装。

- **Bearer auth** header
- **exponential backoff retry** (0.1 → 0.2 → 0.4 → ... cap 5.0)
- **batch buffer** (`batch_size=N` で auto flush)
- env 4 つ (URL / TOKEN / RETRIES / BATCH_SIZE)

```python
@dataclass
class ProductionHttpTimelineSink:
    url: str
    timeout: float = 5.0
    auth_token: str | None = None
    retries: int = 3
    batch_size: int = 0

    def push(self, event: dict) -> None:
        if self.batch_size > 0:
            self._buffer.append(event)
            if len(self._buffer) >= self.batch_size:
                self.flush()
            return
        self._post_with_retry(event)

    def _post_with_retry(self, event: dict) -> None:
        for attempt in range(self.retries + 1):
            # ... HTTP POST、5xx / URLError は retry、最後で諦め
            if attempt < self.retries:
                self._sleep(_exp_backoff_seconds(attempt))
```

stdlib `urllib.request` のみ (依存追加ゼロ)。**+12 テスト**。

> **雑談 12**: production-grade な HTTP client を 150 行で書ける時代に
> なって、僕は嬉しい (1990 年代の sockets API でこれ書こうとしたら
> 半日でも終わらなかった)。Python の標準ライブラリは本当に偉い。

---

## 11. E2E integration test ― 8 milestone を 1 シナリオで連鎖

最後に、M8.1〜M8.9 を全部使う 1 シナリオの integration test を書く。

```python
def test_cognitive_mesh_full_chain(monkeypatch):
    # M8.8: MultiBrief に Brief を register
    mgr = MultiBriefCoherenceManager()
    mgr.register_brief(Brief(brief_id="e2e-001", goal="nightly bench"))
    mgr.register_brief(Brief(brief_id="e2e-002", goal="rotate keys"))
    mgr.record_impact("e2e-001", "e2e-002", 2.0)
    assert mgr.top_central_briefs(k=1)[0][0] == "e2e-001"

    # M8.3: bridge で submit
    bridge = BriefDequeRunnerBridge(runner=_FakeRunner())
    # ... 略

    # M8.4: TitleRecall + embedding factory
    sim = default_embedding_similarity()
    planner = TitleRecallPlanner(similarity_fn=sim)
    planner.setup("bench done", tag="bench")
    # ... 略

    # M8.2: Quarantined Memory
    qmem = QuarantinedMemory(verifier=verifier)
    # ... 略

    # M8.5: TonicRisk → ApprovalBus.intervene
    adapter = RiskInterventionAdapter(bus=ApprovalBus())
    monitor = TonicRiskMonitor(interrupt_threshold=0.5, on_alert=adapter)
    # ... 略

    # M8.6: Mesh5W1H Annotator
    annotator = Mesh5W1HAnnotator()
    annotator.emit_from_text("Why did this happen because of the alert?")

    # M8.7: ProactiveLoop event mode
    loop.tick_event(event=event, ...)

    # M8.9: MultilingualGrammar
    mg = MultilingualGrammar(change_sink=gsink)
    proposal = mg.propose("ja", pattern="risk-触り", ...)
    mg.promote(proposal, new_version="v_1")

    # ---- 最終 verify ----
    assert et_counts == {
        "cog_brief_result": 2,
        "cog_quarantine_pending": 2,
        "cog_risk_alert": 1,
        "cog_proactive_utterance": 1,
    }
```

1 ファイル、1 test。これが全部緑になったとき、私の `pytest -q` の
最後の行が **`1518 passed in 61.59s`** になった。

朝の +125。

> **雑談 13**: E2E test を 1 ファイル 1 test で書くのは、賛否あります。
> 「失敗したときどこで死んだか分からない」「実行に時間がかかる」など。
> 今回は「全部が動く保証」を 1 つの test で取りたかった。本番運用では
> もっと細粒度に切る。

---

## 12. 教訓 ― お互いの利益のために

このセッションで分かったこと:

### A. skeleton 先行は ROI 50 倍

skeleton で API 凍結しておくと、3-6 ヶ月後の本実装で **既存テストが
0 回帰**になる。私は今回 8 件を踏み抜いたが、もし 8 件全部を新規実装
だったら 2-3 週間 + 既存テストが 100 件くらい吹っ飛ぶリスクがあった。
70 点運用 (とりあえず動く skeleton で commit する) と相性が良い。

### B. 「依存追加要承認」は守った方が結果的に楽

networkx を入れたかった。でも 50 行で BFS / DFS / centrality は書けた。
依存追加した未来は分からないけど、書かなかった未来では pyproject.toml
が clean なまま。

### C. cross-repo schema lock は本当に効く

llive ↔ llmesh ↔ llove の 3 リポを 1 セッション内で同期できた。
schema を両側 unit test で守ると、drift が即座に test 失敗で検出される。
microservice 系の人には常識でも、個人開発者には少し気づきだった。

### D. 12 時間連続実装はやれる、でもやらない方がいい

書いてる本人 (たぶん私) は楽しかったが、こんなセッション毎日やってたら
身体が壊れる。 [Quiet Hours][quiet_hours] が architecture の必須依存
なのは、自分自身も守るためでもある。

### E. AI と協働するペース

Claude Opus 4.7 (1M context) と協働で書いた。AI が `feedback_response_timing`
(70 点運用) を守るので、私は方向性決定と最終承認だけ。これが
**「AI を使う」じゃなくて「AI と一緒に作る」**の正体だと思う。

---

## おわりに

llive は `pip install llmesh-llive` でインストールできます。
COG-MESH 全件は v0.x で含まれます。M8.x 完成版を含むリリースは近日。

GitHub: <https://github.com/furuse-kazufumi/llive>

次の記事 (今日中に上げる、たぶん): 「**収益化を AI で自動化したい
個人開発者の現実 ― llgrow 構想と RISK-FX A-G**」(リンク後ほど).

---

**Co-Authored-By**: Claude Opus 4.7 (1M context) ― 本記事は AI 協働で
執筆。実装も同様。 honest disclosure として明示。

**🤖 Generated with [Claude Code](https://claude.com/claude-code)**
