# Enabling GitHub Pages for llive

> Manual one-time setup. Run after merging the docs/_config.yml + docs/index.md commit.

## Steps

1. Go to <https://github.com/furuse-kazufumi/llive/settings/pages>
2. Under **Build and deployment**:
   - **Source**: `Deploy from a branch`
   - **Branch**: `main`
   - **Folder**: `/docs`
3. Click **Save**
4. Wait ~1 minute for the first build to complete
5. Site is published at: <https://furuse-kazufumi.github.io/llive>

## Custom domain (optional, requires DNS setup)

If you obtain `fullsense.dev` (or another domain):

1. In the same GitHub Pages settings, set **Custom domain** = `docs.fullsense.dev`
2. At your DNS provider, add a CNAME record:
   ```
   docs   IN CNAME furuse-kazufumi.github.io
   ```
3. Wait for DNS propagation (5-60 min)
4. Enable **Enforce HTTPS** (after Let's Encrypt provisioning)

## Verification

```bash
# Local Jekyll preview (optional, requires Ruby + bundler)
gem install jekyll bundler jekyll-theme-cayman jekyll-relative-links jekyll-seo-tag
cd docs
jekyll serve
# → http://localhost:4000
```

## Source

- `docs/_config.yml` — Jekyll config (theme = cayman)
- `docs/index.md` — landing page
- All other `*.md` files under `docs/` are auto-rendered as Pages

## Notes

- GitHub Pages **does not** require Jekyll plugins beyond the
  [allowlisted set](https://pages.github.com/versions/). `jekyll-relative-links`
  and `jekyll-seo-tag` are both in the allowlist.
- `.html` files take precedence over `.md` if both exist with the same basename.
- `docs/demos.html` and `docs/v0.2_rad_techdoc.html` will be served as-is.

## Disabling

If GitHub Pages is no longer desired, set Source = `None` in the same
settings page. The `docs/_config.yml` and `docs/index.md` can stay
without affecting anything.
