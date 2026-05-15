# ruff: noqa: RUF001
"""Scenario 11 — 全人類知識吸収 (RAD 横断検索) デモ.

『**人類が絶滅する前に全人類の知識を吸収する**』というユーザの長期計画
(KAR: Knowledge Autarky Roadmap) を、現時点で持っている RAD コーパスで
operational に体感させる scenario。Spec §A*3 Knowledge autarky の minimal
実証。

実演する操作:
1. ``RadCorpusIndex`` に取り込み済の **49 分野** を列挙
2. 横断検索クエリを 3 件投げて、分野跨ぎでヒットが集まる様子を見る
   (例: "Bayesian surprise" → information_theory + cognitive_ai + statistics)
3. 各 hit の domain / score / excerpt を表示
4. 「数学的アプローチ」用コーパス (multivariate_analysis / optimization /
   information_theory / statistics) を抜き出して KAR と接続

scenario tmp_path に小型 mini-RAD を作って動かすので、巨大な
``D:/projects/llive/data/rad`` を読まずに完結する (オフライン + 軽量)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext
from llive.memory.rad import RadCorpusIndex
from llive.memory.rad.query import query as rad_query

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "KAR (Knowledge Autarky Roadmap) — 人類知識を吸収する長期計画の現時点スナップショット。RAD コーパスを横断検索して、複数分野からヒントが集まる様子を体感します。",
        "domains_header": "  取り込み済 RAD 分野 ({n} 個):",
        "domain_row": "    - {name}",
        "math_header": "  数学的基盤 (KAR Mathematical Toolkit):",
        "query_header": "[Query {n}/3] {q!r}",
        "hit_row": "    [{score:.2f}] {domain}/{path}",
        "excerpt": "        excerpt: {text}",
        "no_hits": "    (該当なし — mini-RAD のため大規模 RAD と差があります)",
        "outro": "  ✨ {hits} 件のヒントを {domains} 分野から拾えました。KAR 短期目標 = RAD 100 分野へ拡張。",
    },
    "en": {
        "intro": "KAR (Knowledge Autarky Roadmap) — snapshot of the long-term mission of absorbing human knowledge. Cross-search RAD corpora and observe how hints converge across domains.",
        "domains_header": "  Ingested RAD domains ({n}):",
        "domain_row": "    - {name}",
        "math_header": "  Mathematical foundations (KAR Mathematical Toolkit):",
        "query_header": "[Query {n}/3] {q!r}",
        "hit_row": "    [{score:.2f}] {domain}/{path}",
        "excerpt": "        excerpt: {text}",
        "no_hits": "    (no hits — mini-RAD differs from production RAD scale)",
        "outro": "  ✨ {hits} hints gathered from {domains} domains. KAR short-term goal = RAD 100 domains.",
    },
    "zh": {
        "intro": "KAR (Knowledge Autarky Roadmap) — 吸收人类知识的长期使命的当前快照。跨域检索 RAD 语料，观察多领域 hint 汇聚的样子。",
        "domains_header": "  已取入的 RAD 域 ({n} 个):",
        "domain_row": "    - {name}",
        "math_header": "  数学基础 (KAR Mathematical Toolkit):",
        "query_header": "[Query {n}/3] {q!r}",
        "hit_row": "    [{score:.2f}] {domain}/{path}",
        "excerpt": "        excerpt: {text}",
        "no_hits": "    (无匹配 — mini-RAD 与生产 RAD 规模有差距)",
        "outro": "  ✨ 从 {domains} 个域共收集到 {hits} 条 hint。KAR 短期目标 = RAD 扩展到 100 域。",
    },
    "ko": {
        "intro": "KAR (Knowledge Autarky Roadmap) — 인류 지식 흡수의 장기 미션 현재 스냅샷. RAD 코퍼스를 가로지르며 여러 영역에서 hint 가 모이는 모습을 체험.",
        "domains_header": "  적재된 RAD 영역 ({n} 개):",
        "domain_row": "    - {name}",
        "math_header": "  수학적 기반 (KAR Mathematical Toolkit):",
        "query_header": "[Query {n}/3] {q!r}",
        "hit_row": "    [{score:.2f}] {domain}/{path}",
        "excerpt": "        excerpt: {text}",
        "no_hits": "    (해당 없음 — mini-RAD 와 production RAD 의 규모 차이)",
        "outro": "  ✨ {domains} 개 영역에서 {hits} 건의 hint 수집. KAR 단기 목표 = RAD 100 영역 확장.",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


# 軽量 mini-RAD: 8 分野 × 1-2 ファイル
_MINI_RAD: dict[str, list[tuple[str, str]]] = {
    "information_theory_corpus_v2": [
        (
            "bayesian_surprise.md",
            "Bayesian surprise is the KL divergence between prior and posterior. "
            "Used in active inference and Friston free-energy principle.",
        ),
        (
            "shannon_entropy.md",
            "Shannon entropy H(X) = -sum p(x) log p(x). "
            "Foundation of mutual information and information-theoretic surprise.",
        ),
    ],
    "multivariate_analysis_corpus_v2": [
        (
            "manifold_learning.md",
            "Manifold learning approximates a high-dimensional dataset by a "
            "low-dimensional manifold. UMAP and t-SNE preserve local "
            "neighborhood structure.",
        ),
    ],
    "optimization_corpus_v2": [
        (
            "gradient_descent.md",
            "Gradient descent is the workhorse optimizer for convex problems. "
            "Stochastic gradient descent generalizes to non-convex.",
        ),
        (
            "convex_optimization.md",
            "Convex optimization guarantees global optima via duality and "
            "interior-point methods.",
        ),
    ],
    "statistics_corpus_v2": [
        (
            "confidence_intervals.md",
            "A 95% confidence interval contains the true parameter 95% of the "
            "time under repeated sampling. Bayesian credible intervals differ.",
        ),
    ],
    "reinforcement_learning_corpus_v2": [
        (
            "multi_armed_bandit.md",
            "The multi-armed bandit is the simplest RL problem. UCB and Thompson "
            "sampling balance exploration vs exploitation.",
        ),
    ],
    "cognitive_ai_corpus_v2": [
        (
            "active_inference.md",
            "Active inference minimizes Bayesian surprise (free energy). "
            "Agents act to confirm their model of the world.",
        ),
    ],
    "security_corpus_v2": [
        (
            "buffer_overflow.md",
            "A buffer overflow writes past an allocated boundary. Stack "
            "canaries and DEP mitigate but do not eliminate.",
        ),
    ],
    "hci_corpus_v2": [
        (
            "fitts_law.md",
            "Fitts' law: movement time = a + b * log2(D/W + 1). Applies to "
            "pointing tasks in UI design.",
        ),
    ],
}


_MATH_FAMILIES = (
    "information_theory_corpus_v2",
    "multivariate_analysis_corpus_v2",
    "optimization_corpus_v2",
    "statistics_corpus_v2",
)


def _build_mini_rad(root: Path) -> RadCorpusIndex:
    """tmp_path に small mini-RAD を生成し RadCorpusIndex を返す."""
    root.mkdir(parents=True, exist_ok=True)
    for domain, docs in _MINI_RAD.items():
        dom_dir = root / domain
        dom_dir.mkdir(exist_ok=True)
        for fname, text in docs:
            (dom_dir / fname).write_text(text + "\n", encoding="utf-8")
    return RadCorpusIndex(root=root)


class RadOmniscienceScenario(Scenario):
    id = "rad-omniscience"
    titles: ClassVar[dict[str, str]] = {
        "ja": "全人類知識吸収 — RAD 横断検索 (KAR 進捗スナップショット)",
        "en": "Human knowledge absorption — RAD cross-search (KAR snapshot)",
        "zh": "人类知识吸收 — RAD 跨域检索 (KAR 进度快照)",
        "ko": "인류 지식 흡수 — RAD 횡단 검색 (KAR 진행 스냅샷)",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, Any]:
        ctx.say("  " + _t("intro"))

        idx = _build_mini_rad(ctx.tmp_path / "rad")

        domains = sorted(idx.list_read_domains())
        ctx.say(_t("domains_header", n=len(domains)))
        for d in domains:
            ctx.say(_t("domain_row", name=d))

        ctx.say("")
        ctx.say(_t("math_header"))
        for fam in _MATH_FAMILIES:
            ctx.say(_t("domain_row", name=fam))

        queries = [
            "Bayesian surprise active inference",
            "gradient descent convex optimization",
            "buffer overflow exploitation",
        ]
        per_query: list[dict[str, Any]] = []
        for i, q in enumerate(queries, start=1):
            ctx.say("")
            ctx.say(_t("query_header", n=i, q=q))
            hits = rad_query(idx, q, limit=4, include_learned=False)
            if not hits:
                ctx.say(_t("no_hits"))
                per_query.append({"q": q, "hits": 0, "domains": []})
                continue
            seen_domains: set[str] = set()
            for h in hits:
                rel = h.doc_path.relative_to(idx.root / h.domain).as_posix()
                ctx.say(_t("hit_row", score=h.score, domain=h.domain, path=rel))
                ctx.say(_t("excerpt", text=h.excerpt[:80]))
                seen_domains.add(h.domain)
            per_query.append(
                {"q": q, "hits": len(hits), "domains": sorted(seen_domains)}
            )

        total_hits = sum(d["hits"] for d in per_query)
        domains_touched = sorted(
            {d for q in per_query for d in q["domains"]}
        )
        ctx.hr()
        ctx.say(_t("outro", hits=total_hits, domains=len(domains_touched)))

        return {
            "ingested_domains": domains,
            "math_families": list(_MATH_FAMILIES),
            "queries": per_query,
            "total_hits": total_hits,
            "domains_touched": domains_touched,
        }
