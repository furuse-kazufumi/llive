# v0.J — MCP over Genome フィジビリティ判定

**日付:** 2026-05-22
**PoC:** `experiments/mcp_genome_poc/poc.py`
**結果ファイル:** `experiments/mcp_genome_poc/poc_result.json`
**判定者:** Claude (sub-agent) + 主要 Claude (sub-agent dispatch)

---

## 背景

ユーザー指摘 (2026-05-22 深夜):
> 「ゲノムが MCP を介して相互に連結されるような構造は優位性がありますかね?」

主要 Claude 側分析の結論 — **層別アプローチが正解**:

| 層 | MCP 適性 | 理由 |
|---|---|---|
| 層 1 (inner loop, in-process crossover) | **不要** | RTT 重すぎ. dataclass 直接が桁違いに速い |
| 層 2 (cross-substrate 越境) | **適切** | Python ↔ Rust ↔ Cython 等の越境は元々 IPC 経由 |
| 層 3 (governance / approval) | **適切** | MCP elicitation flow が Approval Bus と自然整合 |
| 層 4 (phylogeny discovery / 共有読み出し) | **適切** | resource として content-addressable 読み出し |

本 PoC は層 1 / 層 2 の **timing 比較** で「層 2-4 限定なら許容可」仮説を実測検証する.

---

## 実測結果 (50 世代 × 10 個体 × 3 trial)

| 項目 | 内側ループ (in-proc) | MCP 越し (JSON-RPC mock) |
|---|---|---|
| 1 op あたり | ~18 us | ~120 us |
| 50×10 op 合計 | ~9 ms | ~60 ms |
| **overhead 比 (中央値)** | — | **6.7x** |

### honest disclosure (重要)

実 MCP transport (stdio subprocess + pipe / sse + httpx) は本 PoC の **10-100x 重い** と
想定される. つまり実環境の overhead は **~60x to ~670x**.

本 PoC の 6.7x は **下限見積り** であり, 「これより悪くなり得ても良くなることはない」
という意味で feasibility 議論の床として機能する.

---

## 8 項目判定表

| 項目 | 結果 | コメント |
|---|---|---|
| 計算量 | 条件付き OK | 内側 O(N) × MCP RTT (実測 6.7x mock; 実 transport で ~60-670x). 層 2-4 限定なら層 1 は in-proc のため total 影響小 |
| メモリ | OK | MCP server / client 各々のヒープ. 個体 1 体 ~2KB JSON, 1000 体 ~2MB. 通常使用域内 |
| コスト | OK | server 立ち上げ ~100ms (asyncio + stdio). 1 セッションで amortize 可 |
| 依存 | OK | `mcp` (公式 anthropic SDK, MIT, optional extra) + asyncio (stdlib). PoC 実機で import 成功確認済 (`C:\Users\puruy\AppData\Local\Programs\Python\Python311\Lib\site-packages\mcp\__init__.py`) |
| ライセンス | OK | mcp SDK は MIT, llive は Apache-2.0 + Commercial dual. 衝突なし |
| 倫理 / 規制 | OK | MCP elicitation flow を Approval Bus と統合可. frozen_gene の rules を resource として expose 可. EAR 観点も on-prem subprocess なら問題なし |
| デバッグ性 | OK | JSON-RPC log を素のまま hold 可. wire format が JSON なので diff / replay 容易 |
| 暴走 | 条件付き OK | timeout / kill switch / Approval Bus 経由でのみ tool 呼出可 とする設計が必要. 実装時に MUST |

---

## 判定: **条件付き OK**

### 採用条件 (skeleton 段階で明示すべき)

1. **層 1 (inner loop) で MCP を使わない** — `MCPSubstrateAdapter` は `cross_substrate.py` の `Substrate.MCP_REMOTE` enum 専用. `Substrate.PYTHON` の inner crossover は dataclass 直接.
2. **層 2/3/4 の越境 / governance / phylogeny 読み出しのみ MCP 経由** — tool として `crossover` / `mutate` / `evaluate_novelty`, resource として `individual` / `population/manifest` / `phylogeny/<id>/ancestors`.
3. **Approval Bus 統合** — `auth_elicitation` を全 tool 呼出の前段に挟む. frozen_gene と連動.
4. **timeout / kill switch** — 全 tool 呼出に timeout (default 30s). budget 超過時 abort.
5. **batch 化を front-load** — 1 op = 1 RPC ではなく, 1 RPC で N op をバッチ送信できる API 設計を初日から取り入れる ([[feedback_rust_usage_matters]] FFI 教訓と同型).

### 再 PoC が必要な状況

- 実 MCP stdio transport の overhead が想定外 (>1000x) になった場合
- batch 化しても per-op cost が下がらない場合
- MCP elicitation flow が Approval Bus と統合できない場合

これらは v0.J 本実装フェーズで `experiments/mcp_genome_poc/poc2_real_transport.py` として再測定する.

---

## skeleton 着地方針

本 FEASIBILITY をもって `src/llive/perf/evolutionary/mcp_substrate_adapter.py` の
skeleton 実装に進む. 並列実行中の別 Agent (cross_substrate.py 編集中) と
**file 競合しないよう**, `Substrate.MCP_REMOTE` の enum 追加は別 commit に分け,
adapter file 側からは `cross_substrate.Substrate` の値を **動的に参照** する
設計とする (enum 未追加でも import 落ちしない fallback あり).

---

## 参考

- [[project_idea_predictive_verification]] — Z3/TLA+ 前段ゲートで本 feasibility を更に予測可能化
- [[feedback_benchmark_honest_disclosure]] — 「mock 6.7x」を「実 transport 6.7x」と誤読しないための明示
- [[feedback_poc_feasibility_first]] — v0.J ルールとして PoC + フィジビリティ先行
- llive `docs/requirements_v0.I_meta_evolution_and_cross_substrate.md` §7 — 越境ゲノムの形式化
