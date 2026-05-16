# FullSense Family — Setup Status & Pending Manual Steps

> 2026-05-16 時点で **Claude が単独で完了したもの** と **ユーザ手間が必要なもの**
> を一覧化。出かけている間に Claude が進めたのはコード / draft / config まで。
> 実際の操作 (UI / 認証 / 出願) はここから手で進める。

## ✓ Claude が完了

### llive リポジトリ
- [x] FullSense ™ umbrella brand 導入 (TRADEMARK.md / NOTICE / README)
- [x] Apache-2.0 + Commercial dual-license 切替 (v0.6.0)
- [x] NOTICE / CONTRIBUTING (DCO) / SECURITY / TRADEMARK / LICENSE-COMMERCIAL 整備
- [x] 204 .py に SPDX-License-Identifier header 一括追加
- [x] 9 axes skeleton (KAR/DTKR/APO/ICP/TLB/Math/PM/RPAR/SIL) — 前セッション
- [x] **C-1**: Approval Bus production 化 (Policy + SQLite Ledger)
- [x] **C-2**: @govern decorator + ProductionOutputBus (Phase 1+2+3)
- [x] **C-3**: Cross-substrate migration spike (§MI1)
- [x] v1.0.0 PyPI rename migration plan (`docs/v1.0_migration_plan.md`)
- [x] 商標 draft Wave 1 (FullSense × JP/US/EU)
- [x] 商標 draft Wave 2 (llmesh/llive/llove × JP/US/EU)
- [x] GitHub Pages 用 `docs/_config.yml` + `docs/index.md` + `docs/PAGES.md`
- [x] 公開記事 update (linkedin ja/en/zh + qiita 追補)
- [x] 840 tests / ruff clean / 全 push 済

### 他リポジトリ
- [x] llove README に FullSense family バナー (push 済)
- [x] llmesh README に FullSense family バナー (push 済)
- [x] llmesh-suite README に FullSense family バナー (push 済)
- [x] llmesh-demos README に FullSense family バナー (local commit のみ、push 未)

### GitHub Pages family 化 (2026-05-16 追加)
- [x] **llive**: GitHub Pages 有効化済 (ユーザが手動で実施完了。`https://furuse-kazufumi.github.io/llive/`)
- [x] **llive**: theme を `just-the-docs` (左 nav + 検索) に切替済 + custom domain guide 追加
- [x] **llmesh**: `docs/_config.yml` + `docs/index.md` 整備済 (push 済、有効化はユーザ手間)
- [x] **llove**: `docs/_config.yml` + `docs/index.md` 整備済 (push 済、有効化はユーザ手間)

## ⏳ ユーザ手間が必要

### GitHub UI / 認証

- [x] ~~GitHub Pages を有効化~~ — llive 完了 (`https://furuse-kazufumi.github.io/llive/`)
- [ ] **llmesh / llove で Pages を有効化** — Settings → Pages → Source: main / docs を各リポジトリで実施
- [ ] **fullsense umbrella の GitHub repo を作成 + Pages 公開** (新規)
  - local には `D:/projects/fullsense/` に portal の README + docs/_config.yml + docs/index.md 整備済 (commit 済)
  - `gh repo create furuse-kazufumi/fullsense --public --source D:/projects/fullsense --remote origin --push --description "FullSense umbrella portal — llmesh / llive / llove family"`
  - 続けて Settings → Pages → Source: main / docs で公開
  - 期待 URL: `https://furuse-kazufumi.github.io/fullsense/`
  - FullSense → 3 製品の親子関係を URL 上で明示できる
- [ ] **llmesh-demos の GitHub repo を作成**
  - `gh repo create furuse-kazufumi/llmesh-demos --public --source D:/projects/llmesh-demos --remote origin --push`
  - Claude が試みたが PAT に `repo` scope なし。Token 設定変更 or GitHub UI で作成
- [ ] (任意) PAT に admin / repo scope を追加して、次回以降 Claude が単独で UI 操作できるように
- [ ] **(任意) カスタムドメイン適用** — `docs/custom_domain_guide.md` 参照
  - ドメイン取得 (fullsense.dev / .ai / .io 候補)
  - DNS の CNAME/A レコード設定
  - 各リポジトリで Add domain
  - Enforce HTTPS

### 商標 pre-search (出願前必須)

- [ ] J-PlatPat (<https://www.j-platpat.inpit.go.jp/>) で `FullSense` / `フルセンス` / `llmesh` / `llive` / `llove` の称呼検索
- [ ] USPTO TESS で同じ 4 mark を検索
- [ ] EUIPO eSearch plus + TMview で同じ 4 mark を検索
- [ ] WIPO Madrid Monitor で国際登録なし確認

### ドメイン取得検討

- [ ] `fullsense.com` / `.ai` / `.dev` / `.io` / `.org` の取得可否
- [ ] `llive.dev` / `llmesh.dev` / `llove.dev` も検討
- [ ] 取得後 `docs/_config.yml` の `url` を更新し、GitHub Pages の Custom domain を設定 (CNAME)

### 商標出願 (3 段階)

- [ ] **Wave 1**: FullSense (umbrella) を JP → US → EU で出願
- [ ] **Wave 2**: llmesh / llive / llove (子 mark) を同 jurisdictions で出願
- [ ] 自己出願 or 弁理士依頼の選択
- [ ] 出願後 6-12 ヶ月で登録完了、TRADEMARK.md の ™ → ® に更新

### PyPI 名予約 (v0.7.x で実施)

- [ ] `fullsense`, `fullsense-llmesh`, `fullsense-llive`, `fullsense-llove`, `fullsense-suite` の空 release を予約 push
- [ ] 旧名 README に rename 予告

### v1.0.0 cut 時の作業 (将来)

- [ ] `pyproject.toml` で PyPI 名を `fullsense-*` に rename
- [ ] 旧 `llmesh-*` パッケージを alias / shim として v1.0.0 まで維持
- [ ] CHANGELOG / docs / 各種記事 (linkedin / qiita) の言及置換

## 参考

- 商標 draft: `docs/legal/trademark/`
- v1.0.0 migration: `docs/v1.0_migration_plan.md`
- ライセンス: `LICENSE` (Apache-2.0) + `LICENSE-COMMERCIAL`
- 連絡先: kazufumi@furuse.work
