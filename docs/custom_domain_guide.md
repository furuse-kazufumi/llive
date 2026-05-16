---
layout: default
title: "Custom Domain Setup (CNAME) Guide"
nav_order: 99
---

# Custom Domain Setup — fullsense.dev / .ai / .io / ...

GitHub Pages の **Custom domain** (Add domain) を使うための手順。ドメイン
取得後にこの順で進めれば 30〜60 分で `https://docs.fullsense.dev/...` 等の
URL で公開できるようになる。

## Phase 1: ドメイン取得 (ユーザ手間)

候補レジストラ:

- **Cloudflare Registrar** — 卸値、DNS 込み、推奨
- **Google Domains** (旧) / **Squarespace Domains** — UI 平易
- **Namecheap** — 安価、UI 普通
- **お名前.com** — 日本語サポート、価格は普通

候補ドメイン (推奨優先):

| Domain               | 用途                                | 備考                                |
|----------------------|--------------------------------------|-------------------------------------|
| `fullsense.dev`      | docs / 公式 portal                   | `.dev` は Google TLD、HTTPS 強制    |
| `fullsense.ai`       | brand 強化                           | `.ai` は高価 ($60-200/年)           |
| `fullsense.io`       | tech ブランド一般                    | `.io` は $30-50/年                  |
| `fullsense.com`      | corporate                            | 取得不可なら squatter チェック       |
| `fullsense.org`      | OSS organization 感                  | 安価                                |

複数取得して 1 つを primary、残りは redirect 用にするのが定石。

## Phase 2: DNS レコード追加 (取得先で実施)

GitHub Pages のサブドメイン → CNAME / 4 種類の A レコードのどちらか。

### 推奨: サブドメインを CNAME で publish

例: `docs.fullsense.dev` を llive docs にする

```
docs   IN CNAME   furuse-kazufumi.github.io.
```

Cloudflare 等の UI では:

| Type  | Name (host) | Content / Target           | TTL   |
|-------|-------------|----------------------------|-------|
| CNAME | docs        | furuse-kazufumi.github.io  | Auto  |

(CNAME の値の末尾 `.` はレジストラによっては自動付与)

### Apex (ルート) ドメインの場合

`fullsense.dev` 自体 (subdomain なし) を Pages にあてたい場合、CNAME は
RFC 上 root に置けないので **4 つの A レコード** を追加:

```
@   IN A   185.199.108.153
@   IN A   185.199.109.153
@   IN A   185.199.110.153
@   IN A   185.199.111.153
```

これは GitHub Pages の固定 IP (公式 docs と整合)。

### サブドメインを複数 (llive / llmesh / llove)

```
docs        IN CNAME   furuse-kazufumi.github.io.
docs-mesh   IN CNAME   furuse-kazufumi.github.io.
docs-love   IN CNAME   furuse-kazufumi.github.io.
```

GitHub Pages は **どのレポを返すか** を Custom domain 設定で識別するため、
複数サブドメインを 1 つの `furuse-kazufumi.github.io` に向けて、それぞれの
リポで別の Custom domain を設定すれば OK。

## Phase 3: GitHub Repository 側で Custom domain を入力

各リポジトリで:

1. `https://github.com/<repo>/settings/pages` を開く
2. **Custom domain** 入力欄に `docs.fullsense.dev` (或いは `docs-mesh.fullsense.dev` 等) を入力
3. **Save** をクリック
4. GitHub が DNS 解決を検証 (~1 分)
5. 検証成功すると緑のチェック + `dns_check_passed` メッセージ
6. **Enforce HTTPS** にチェック (Let's Encrypt 自動発行、~10 分)

### 失敗時のチェック

- DNS 反映を確認: `nslookup docs.fullsense.dev` で `furuse-kazufumi.github.io` が返るか
- `dig docs.fullsense.dev CNAME` で CNAME record が見えるか
- DNS が反映されていない → 数分〜数時間待つ (TTL 次第)
- 反映済だが GitHub が認識しない → Save をもう一度押す

## Phase 4: リポジトリに CNAME ファイルを commit (推奨)

GitHub UI から Save すると自動で `docs/CNAME` が作成される **が**、稀に
deploy 時にリセットされる場合があるので、明示的に commit すると安全:

```
docs/CNAME      ← 1 行だけ、ドメイン名を書く
# docs/CNAME の中身:
docs.fullsense.dev
```

リポジトリに pushed `CNAME` がある場合、GitHub Pages は build 時にそれを
正として扱う。

## Phase 5: 各 docs/_config.yml の url 更新

```yaml
url: https://docs.fullsense.dev        # llive
# url: https://docs-mesh.fullsense.dev  # llmesh
# url: https://docs-love.fullsense.dev  # llove
```

これで Sitemap.xml や SEO tags のリンクが新ドメインを向く。

## Phase 6: 検証

```bash
curl -I https://docs.fullsense.dev/
# HTTP/2 200
# location ヘッダ無し、cache-control ヘッダあり
```

ブラウザで `https://docs.fullsense.dev/` を開いて、`https://furuse-kazufumi.github.io/llive/` と同じコンテンツが見えれば成功。

## 関連

- `docs/family_setup_status.md` — 全 family の setup status
- `docs/PAGES.md` — Pages 有効化基本手順
- `_config.yml` — Jekyll 設定
