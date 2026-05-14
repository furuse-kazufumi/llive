"""Scenario 1: RAD quick-tour.

A 30-second flyover of the read API. Builds a tiny synthetic corpus,
runs three queries (filename match, content match, no-match), prints
top hits with excerpt + score.

TRIZ #15 動的化: synthetic 文書を context.tmp_path に乱数なしで生成する
(再現性確保) が、query 結果は score でソートされた表示なので「動きで魅せる」
ところは <strong>結果の差</strong>として現れる。
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext
from llive.memory.rad import RadCorpusIndex
from llive.memory.rad.query import query

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "ミニコーパスを生成して RAD 読み API を 3 通りに当てます。",
        "build": "サンプルコーパスを {root} に作成中...",
        "ready": "  {n} 件のドキュメントを {domain} に配置しました。",
        "query": "クエリ: {q!r}",
        "no_hit": "  (該当なし)",
        "hit": "  - {domain}/{name}  score={score:.1f}  matched={terms}",
        "excerpt": "    抜粋: {excerpt}",
        "summary": "合計 {hits} 件のヒット。クエリの強さは filename 一致が一段強い。",
    },
    "en": {
        "intro": "Build a tiny synthetic corpus and hit the read API three ways.",
        "build": "Creating sample corpus under {root}...",
        "ready": "  Placed {n} docs into {domain}.",
        "query": "Query: {q!r}",
        "no_hit": "  (no matches)",
        "hit": "  - {domain}/{name}  score={score:.1f}  matched={terms}",
        "excerpt": "    excerpt: {excerpt}",
        "summary": "Total {hits} hits. Filename matches dominate as designed.",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


def _seed_corpus(root: Path) -> Path:
    domain = "security_corpus_v2"
    base = root / domain
    base.mkdir(parents=True, exist_ok=True)
    (base / "buffer_overflow.md").write_text(
        "# Buffer Overflow\n\nClassic memory-safety bug: writes that exceed the "
        "allocated buffer corrupt adjacent memory.\nMitigations include "
        "canaries, ASLR, and stack-protector.\n",
        encoding="utf-8",
    )
    (base / "format_string.md").write_text(
        "# Format String\n\nUntrusted format specifiers leak memory via %x or %s.\n",
        encoding="utf-8",
    )
    (base / "race_conditions.md").write_text(
        "# Race conditions\n\nTOCTOU and threading hazards. Use atomics or locks.\n",
        encoding="utf-8",
    )
    return base


class QuickTourScenario(Scenario):
    id = "rad-quick-tour"
    titles: ClassVar[dict[str, str]] = {
        "ja": "RAD 読み API のクイックツアー",
        "en": "RAD read-API quick tour",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, object]:
        ctx.say("  " + _t("intro"))
        ctx.say("  " + _t("build", root=ctx.tmp_path))
        rad_root = ctx.tmp_path / "rad"
        _seed_corpus(rad_root)
        idx = RadCorpusIndex(root=rad_root)
        ctx.say(_t("ready", n=3, domain="security_corpus_v2"))

        total_hits = 0
        for q in ("buffer overflow", "TOCTOU race", "elephant"):
            ctx.step(1, 3, _t("query", q=q))
            hits = query(idx, q, limit=3)
            total_hits += len(hits)
            if not hits:
                ctx.say(_t("no_hit"))
                continue
            for h in hits:
                ctx.say(_t(
                    "hit",
                    domain=h.domain,
                    name=h.doc_path.name,
                    score=h.score,
                    terms=",".join(h.matched_terms),
                ))
                if h.excerpt:
                    ctx.say(_t("excerpt", excerpt=h.excerpt[:80]))
        ctx.hr()
        ctx.say("  " + _t("summary", hits=total_hits))
        return {"queries": 3, "total_hits": total_hits}
