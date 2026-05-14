"""Scenario 2: append_learning round-trip.

Demonstrates the write layer: append a learned doc, show its
``provenance.json`` sidecar, then query and see it returned alongside
read-layer hits. Highlights how llive's own learnings become first-class
RAD citizens.
"""

from __future__ import annotations

import json
from typing import ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext
from llive.memory.provenance import Provenance
from llive.memory.rad import RadCorpusIndex
from llive.memory.rad.append import append_learning
from llive.memory.rad.query import query

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "_learned/ に学習物を書き、すぐ検索で見える経路を示します。",
        "append": "{domain} に学習物を書き込み...",
        "written": "  ✓ {doc} と {prov} を作成 (合計 {bytes} bytes)",
        "prov_head": "  provenance.json の中身:",
        "search": "書いた直後にキーワード {q!r} で検索...",
        "hit": "  - {domain}/{name}  score={score:.1f}",
        "excerpt": "    抜粋: {excerpt}",
        "summary": "{n} 件ヒット。consolidation 出口の書き戻し経路と同じ仕組みです。",
    },
    "en": {
        "intro": "Write into _learned/ and immediately retrieve it through query.",
        "append": "Writing learned doc into {domain}...",
        "written": "  ok wrote {doc} and {prov} ({bytes} bytes total)",
        "prov_head": "  provenance.json contents:",
        "search": "Querying for {q!r} right after the write...",
        "hit": "  - {domain}/{name}  score={score:.1f}",
        "excerpt": "    excerpt: {excerpt}",
        "summary": "{n} hits. Same path the consolidator uses on its semantic out.",
    },
    "zh": {
        "intro": "向 _learned/ 写入学习记录,并立刻通过查询检索出来。",
        "append": "向 {domain} 写入学习记录...",
        "written": "  ok 写入 {doc} 与 {prov} (共 {bytes} bytes)",
        "prov_head": "  provenance.json 内容:",
        "search": "写入后立即查询 {q!r}...",
        "hit": "  - {domain}/{name}  score={score:.1f}",
        "excerpt": "    片段: {excerpt}",
        "summary": "{n} 条命中。这与 consolidator 语义出口的写回路径一致。",
    },
    "ko": {
        "intro": "_learned/ 에 학습 결과를 쓰고, 바로 검색으로 다시 꺼냅니다.",
        "append": "{domain} 에 학습 문서 쓰는 중...",
        "written": "  ok {doc} 와 {prov} 작성 완료 (총 {bytes} bytes)",
        "prov_head": "  provenance.json 내용:",
        "search": "쓰기 직후 키워드 {q!r} 로 검색...",
        "hit": "  - {domain}/{name}  score={score:.1f}",
        "excerpt": "    발췌: {excerpt}",
        "summary": "{n}건 일치. consolidator 의미 출구의 회수 경로와 동일.",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


class AppendRoundTripScenario(Scenario):
    id = "append-roundtrip"
    titles: ClassVar[dict[str, str]] = {
        "ja": "学習物の書き込み → 即時検索",
        "en": "Write learning -> retrieve immediately",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, object]:
        ctx.say("  " + _t("intro"))
        rad_root = ctx.tmp_path / "rad"
        rad_root.mkdir()
        idx = RadCorpusIndex(root=rad_root)

        ctx.step(1, 2, _t("append", domain="vlm_findings"))
        prov = Provenance(
            source_type="demo",
            source_id="scenario-2",
            confidence=0.85,
            derived_from=["event-001", "event-002"],
        )
        entry = append_learning(
            idx,
            "vlm_findings",
            "# Adversarial patch on stop signs\n\n"
            "Empirical study: physically-applied stickers can flip a vision model's\n"
            "classification of stop signs to speed-limit-45 with ~75% transfer.\n"
            "Mitigation candidates: input randomisation, certified defences.\n",
            prov,
        )
        total_bytes = entry.doc_path.stat().st_size + entry.provenance_path.stat().st_size
        ctx.say(_t(
            "written",
            doc=entry.doc_path.name,
            prov=entry.provenance_path.name,
            bytes=total_bytes,
        ))
        ctx.say(_t("prov_head"))
        prov_data = json.loads(entry.provenance_path.read_text(encoding="utf-8"))
        for k in ("source_type", "source_id", "confidence", "derived_from"):
            ctx.say(f"    {k}: {prov_data.get(k)!r}")

        ctx.step(2, 2, _t("search", q="adversarial patch"))
        hits = query(idx, "adversarial patch", limit=5)
        for h in hits:
            ctx.say(_t("hit", domain=h.domain, name=h.doc_path.name, score=h.score))
            if h.excerpt:
                ctx.say(_t("excerpt", excerpt=h.excerpt[:80]))

        ctx.hr()
        ctx.say("  " + _t("summary", n=len(hits)))
        return {"hits": len(hits), "doc_id": entry.doc_id}
