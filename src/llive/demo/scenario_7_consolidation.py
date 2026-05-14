"""Scenario 7: consolidation → RAD mirror flow.

The biological-memory headline feature of llive. Writes a small cluster of
``EpisodicEvent`` rows about a topic, runs one ``Consolidator`` cycle, and
shows that the resulting ``ConceptPage`` ends up mirrored into
``_learned/<page_type>/<concept_id>.md`` with a provenance.json that
points back at the raw event ids (LLW-AC-01 source-anchored).

Uses the deterministic ``MockCompileLLM`` (set ``LLIVE_CONSOLIDATOR_MOCK=1``)
so the scenario does not need an LLM API key.

TRIZ #5 結合 — episodic / semantic / RAD を単一サイクルで結合。
TRIZ #19 周期的アクション — consolidation サイクルは繰り返し走る前提。
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext
from llive.memory.consolidation import Consolidator, ConsolidatorConfig
from llive.memory.episodic import EpisodicEvent, EpisodicMemory
from llive.memory.provenance import Provenance
from llive.memory.rad import RadCorpusIndex
from llive.memory.structural import StructuralMemory

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "EpisodicEvent → cluster → ConceptPage → _learned/ への自動ミラー経路を 1 サイクルで示します。",
        "events": "3 件の類似 episodic event を書き込み...",
        "cycle": "Consolidator.run_once() を実行 (Mock LLM、ネットワーク不要)...",
        "result": "  pages_created={created} / pages_updated={updated} / clusters={clusters}",
        "mirrored": "  _learned/<page_type>/ に書かれたファイル:",
        "prov": "  provenance.json (LLW-AC-01 source-anchored):",
        "summary": "{n} 件の learned doc が生成。derived_from で生 event id まで追跡可能です。",
    },
    "en": {
        "intro": "Watch one consolidator cycle turn episodic events into a ConceptPage mirrored to _learned/.",
        "events": "Writing 3 similar episodic events...",
        "cycle": "Running Consolidator.run_once() (Mock LLM, no network)...",
        "result": "  pages_created={created} / pages_updated={updated} / clusters={clusters}",
        "mirrored": "  Files written into _learned/<page_type>/:",
        "prov": "  provenance.json (LLW-AC-01 source-anchored):",
        "summary": "{n} learned docs produced. derived_from traces back to the raw event ids.",
    },
    "zh": {
        "intro": "用 1 个 cycle 展示 EpisodicEvent → cluster → ConceptPage → _learned/ 的自动镜像路径。",
        "events": "写入 3 条相似的 episodic event...",
        "cycle": "执行 Consolidator.run_once() (Mock LLM,无需网络)...",
        "result": "  pages_created={created} / pages_updated={updated} / clusters={clusters}",
        "mirrored": "  写入到 _learned/<page_type>/ 的文件:",
        "prov": "  provenance.json (LLW-AC-01 source-anchored):",
        "summary": "生成 {n} 条 learned doc。可凭 derived_from 追溯到原始 event id。",
    },
    "ko": {
        "intro": "한 사이클로 EpisodicEvent → cluster → ConceptPage → _learned/ 자동 미러 경로를 보여줍니다.",
        "events": "유사한 episodic event 3건 쓰는 중...",
        "cycle": "Consolidator.run_once() 실행 (Mock LLM, 네트워크 불필요)...",
        "result": "  pages_created={created} / pages_updated={updated} / clusters={clusters}",
        "mirrored": "  _learned/<page_type>/ 에 작성된 파일:",
        "prov": "  provenance.json (LLW-AC-01 source-anchored):",
        "summary": "{n}건의 learned doc 생성. derived_from 으로 원본 event id 까지 추적 가능.",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


def _write_events(ep: EpisodicMemory) -> list[str]:
    contents = [
        "Heap spray exploitation requires precise allocation timing.",
        "Heap spray attacks fill the heap with attacker-controlled payloads.",
        "Heap spray is a classic technique for unreliable use-after-free escalation.",
    ]
    ids: list[str] = []
    for c in contents:
        ev = EpisodicEvent(
            content=c,
            provenance=Provenance(source_type="demo", source_id="scenario-7"),
        )
        ep.write(ev)
        ids.append(ev.event_id)
    return ids


class ConsolidationMirrorScenario(Scenario):
    id = "consolidation-mirror"
    titles: ClassVar[dict[str, str]] = {
        "ja": "生物学的記憶モデルから RAD への書き戻し",
        "en": "Biological memory consolidation -> RAD mirror",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, Any]:
        import os

        prior = os.environ.get("LLIVE_CONSOLIDATOR_MOCK")
        os.environ["LLIVE_CONSOLIDATOR_MOCK"] = "1"
        ctx.say("  " + _t("intro"))

        rad_root = ctx.tmp_path / "rad"
        rad_root.mkdir()
        idx = RadCorpusIndex(root=rad_root)

        ep = EpisodicMemory(db_path=ctx.tmp_path / "ep.duckdb")
        sm = StructuralMemory(db_path=ctx.tmp_path / "s.kuzu")
        cons = Consolidator(
            episodic=ep,
            structural=sm,
            config=ConsolidatorConfig(
                sample_size=20,
                cluster_min_size=2,
                cluster_similarity_threshold=0.22,
            ),
            rad_index=idx,
        )

        try:
            ctx.step(1, 2, _t("events"))
            event_ids = _write_events(ep)
            ctx.say(f"    event_ids = {event_ids}")

            ctx.step(2, 2, _t("cycle"))
            result = cons.run_once(limit=10)
            ctx.say(_t(
                "result",
                created=result.pages_created,
                updated=result.pages_updated,
                clusters=result.clusters,
            ))

            ctx.say(_t("mirrored"))
            learned_files: list[str] = []
            if idx.learned_root.exists():
                for p in sorted(idx.learned_root.rglob("*.md")):
                    rel = p.relative_to(idx.learned_root)
                    learned_files.append(str(rel))
                    ctx.say(f"    - {rel}")

            # Show one provenance.json
            ctx.say(_t("prov"))
            for p in sorted(idx.learned_root.rglob("*.provenance.json")):
                data = json.loads(p.read_text(encoding="utf-8"))
                for k in ("source_type", "source_id", "confidence", "derived_from"):
                    ctx.say(f"    {k}: {data.get(k)!r}")
                break  # 1 example is enough for the demo
            ctx.hr()
            ctx.say("  " + _t("summary", n=len(learned_files)))
            return {
                "pages_created": result.pages_created,
                "learned_files": len(learned_files),
                "errors": list(result.errors),
            }
        finally:
            ep.close()
            sm.close()
            if prior is None:
                os.environ.pop("LLIVE_CONSOLIDATOR_MOCK", None)
            else:
                os.environ["LLIVE_CONSOLIDATOR_MOCK"] = prior
