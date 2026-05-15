# SPDX-License-Identifier: Apache-2.0
"""KAR Mathematical Toolkit — 数学コーパス向け query wrapper.

PROGRESS.md の Mathematical Toolkit テーブルを参照しながら、RAD の数学系
コーパスに対する一発検索 API を提供する。実装単位の各章 (TLB Bridge / APO
Optimizer / DTKR Predictive / ICP Consensus 等) が `gather_hints(topic)` を
呼ぶだけで「自分の章に対応する数学コーパス」の hint が返る。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from llive.memory.rad import RadCorpusIndex
from llive.memory.rad.query import RadHit
from llive.memory.rad.query import query as rad_query

# PROGRESS.md Mathematical Toolkit の「章 → corpus」マッピング
_CHAPTER_CORPUS_MAP: dict[str, tuple[str, ...]] = {
    "tlb_bridge": ("multivariate_analysis_corpus_v2",),
    "tlb_coordinator": ("information_theory_corpus_v2",),
    "apo_optimizer": ("optimization_corpus_v2",),
    "apo_verifier": ("formal_methods_corpus_v2", "automated_theorem_proving_corpus_v2"),
    "apo_metrics": ("statistics_corpus_v2",),
    "dtkr_prefetch": ("reinforcement_learning_corpus_v2",),
    "dtkr_eviction": ("optimization_corpus_v2", "statistics_corpus_v2"),
    "icp_consensus": ("statistics_corpus_v2", "information_theory_corpus_v2"),
    "f1_salience": ("information_theory_corpus_v2",),
    "multitrack": ("multivariate_analysis_corpus_v2",),
    "f6_time_horizon": ("numerical_methods_corpus_v2",),
}


@dataclass
class MathHintBundle:
    """Mathematical Toolkit query の結果バンドル."""

    chapter: str
    topic: str
    domains_queried: tuple[str, ...]
    hits: list[RadHit]


def gather_hints(
    index: RadCorpusIndex,
    chapter: str,
    topic: str,
    *,
    limit: int = 5,
) -> MathHintBundle:
    """指定 chapter に対応する数学コーパスから topic に関する hint を返す.

    Args:
        index: RAD index
        chapter: PROGRESS.md Mathematical Toolkit の章 ID
        topic: keyword string (RAD query へそのまま渡る)
        limit: 返す hit 数の上限

    Returns:
        MathHintBundle. 該当 chapter が未登録なら空 hits.
    """
    domains = _CHAPTER_CORPUS_MAP.get(chapter, ())
    if not domains:
        return MathHintBundle(
            chapter=chapter, topic=topic, domains_queried=(), hits=[]
        )
    # 存在する domain だけに絞って query
    avail = tuple(d for d in domains if index.has_domain(d))
    if not avail:
        return MathHintBundle(
            chapter=chapter, topic=topic, domains_queried=avail, hits=[]
        )
    hits = rad_query(
        index, topic, domain=list(avail), limit=limit, include_learned=False
    )
    return MathHintBundle(
        chapter=chapter, topic=topic, domains_queried=avail, hits=hits
    )


def list_chapters() -> Iterable[str]:
    return _CHAPTER_CORPUS_MAP.keys()


__all__ = [
    "MathHintBundle",
    "gather_hints",
    "list_chapters",
]
