# 2 日で 9 軸の生産化が進んだ ― llive v0.6.0 進捗更新

> [前回 (2026-05-14)](./post_2026-05-14_overview.ja.md) から 2 日。
> `llmesh-llive` は 9 軸の MVP skeleton 完成 → 最初の軸の production 化 +
> dual-license 切替まで一気に進みました。**変化のスピードを記録に残す**意味で
> 短い update を投下します。

## 何が起きたか (2026-05-14 → 2026-05-16)

| 領域 | 2026-05-14 (前回) | 2026-05-16 (今) |
|---|---|---|
| テスト数 | 444 PASS | **815 PASS** (+371) |
| アーキ軸 | 8 設計柱 | **9 軸 skeleton 完了**（KAR / DTKR / APO / ICP / TLB / Math / PM / RPAR / SIL） |
| Conformance Manifest | 未集計 | **holds=24 / violated=0 / undecidable=1** |
| Approval Bus | in-memory MVP | **policy + SQLite ledger で production 化**（C-1 完了） |
| ライセンス | MIT | **Apache-2.0 + Commercial の dual-license** に切替（v0.6.0） |
| ガバナンス | LICENSE のみ | NOTICE / CONTRIBUTING (DCO) / SECURITY / TRADEMARK 整備 |
| SPDX ヘッダ | なし | **全 204 .py に `SPDX-License-Identifier: Apache-2.0`** 自動挿入 |

## 9 軸 skeleton ― FullSense Spec v1.1 の最終形

FullSense Spec を 9 軸まで広げ、各軸を最小実装で揃えました。

- **KAR (Knowledge Autarky)** — RAD 49 分野を 100 分野へ拡張するロードマップ、知識主権の長期計画
- **DTKR (Disk-Tier Knowledge Routing)** — MoE のディスク版。1 skill = 1 ファイルで動的進化
- **APO (Autonomous Performance Optimization)** — 自分で自分を tune（§E2 bounded modification）
- **ICP (Idle-Collaboration Protocol)** — idle 時間に他 Local LLM と協調（LLMesh 思想直系）
- **TLB (Thought Layer Bridge)** — 多視点並列の指数爆発を Manifold Cache + Global Coordinator で抑制
- **Math Toolkit** — 各軸の数学的根拠を RAD コーパスから直接引く運用
- **PM (Publication Media)** — asciinema / SVG / GIF / mp4 を README に埋め込む説明力強化
- **RPAR (Robotic Process Automation Realisation)** — Sandbox → Permitted-action の段階移行
- **SIL (Self-Interrogation Layer)** — 5 Interrogator で自分を多角的に詰める内省層

Conformance Manifest が **holds=24 / violated=0** で揃ったので、9 軸の MVP は仕様適合。

## Approval Bus の production 化 (C-1 完了)

RPA (Robotic Process Automation) で外部副作用を扱うとき、**承認バス**が要になります。
v0.5.x では in-memory MVP でしたが、v0.6.0 で以下を production 化:

- **Policy 抽象** — `AllowList` / `DenyList` / `CompositePolicy` で auto-approve / deny。`deny_overrides(allow, deny)` ヘルパで「deny を優先」の典型を 1 行で構成
- **SQLite 永続化** — stdlib `sqlite3` のみ。schema v1 (requests / responses / meta) で再起動越しに replay
- **後方互換** — `ApprovalBus()` 引数なしは旧挙動と完全一致 (既存 8 件テスト無修正)

`@govern(policy)` を ProductionOutputBus に統合する C-2 が次ターゲット。

## Dual-license に切替えた理由

OSS 普及を最優先にしつつ、長期で「特許攻撃に晒されないこと」「商用展開の余地を残すこと」を両立するため、v0.6.0 で **MIT → Apache-2.0 + Commercial** に切替えました。

- Apache-2.0 = OSS 利用者には**明示的な特許 grant** + 寄与者の特許訴訟リスク低減
- Commercial = SLA / 補償 / クローズドソース統合が必要な企業向けに別枠

合わせて NOTICE / CONTRIBUTING (DCO 1.1) / SECURITY / TRADEMARK を整備。`@apache` / `@cncf` 文脈で見慣れた OSS 慣行に合わせた形に揃いました。

## キャリアの観点で何が増えたか

前回の記事で書いた「設計判断の蓄積」に、この 2 日で 4 つ追加:

1. **9 軸 spec を unit test で固定化する経験** ― 形式検証ではなく runtime conformance manifest で「仕様に準拠してることを毎回 CI で検証」
2. **承認バスの production 化** ― auto-policy + persistent ledger + 後方互換の 3 拍子を、後付けで non-breaking に入れる設計
3. **OSS と商用の境界を引く実務** ― MIT を選ぶか Apache を選ぶか、dual-license の理由を Stakeholder に説明できる語彙
4. **SPDX / NOTICE / DCO / SBOM の運用** ― 「コード品質」だけでなく「ライセンス品質」を CI で測る発想

特に 3 は、AI スタートアップ・規制業界の AI 導入チームともに**実は文書のほうで止まる**領域です。

## ここまでの数字

- **v0.6.0** (本日 cut) ― 9 軸 skeleton + C-1 production + dual-license
- **815 tests / ruff clean** (v0.5.0 444 + 371)
- PyPI: `pip install llmesh-llive`
- 4 リポジトリ並行運用: llive / llmesh / llove / llmesh-demos

## 何を見せたいか

短く言えば「**個人プロジェクトでもここまで詰められる**」を実証したいです。
2 日でこのペースを継続できるのは、ロードマップが具体的 + テストが先に書かれていて 0→1 の見積もりが狂わないこと、Spec が CLAUDE.md と CONTRIBUTING.md で固定されていて意思決定の往復が少ないこと、が両輪です。

> GitHub: <https://github.com/furuse-kazufumi/llive>
> PyPI: `pip install llmesh-llive`

#AI #LLM #ContinualLearning #MLOps #OpenSource #ApacheLicense #個人開発 #キャリア
