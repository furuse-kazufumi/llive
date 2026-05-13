"""Consolidator + Wiki Compiler (MEM-08, LLW-02).

A single consolidation cycle is a *Wiki Compile pass*:

1. **Replay Select** — surprise-weighted reservoir sample of recent
   ``EpisodicEvent`` rows.
2. **Cluster** — group events by sentence embedding similarity.
3. **Compile** — for each cluster, call an LLM that decides ``new`` /
   ``update`` / ``merge`` / ``split`` against the existing ConceptPages.
4. **Link** — connect related ConceptPages with ``linked_concept`` edges.
5. **Provenance** — every page touched gains a Provenance entry pointing
   back to the contributing episodic events.

Phase 2 uses :class:`Anthropic` (Claude Haiku) by default and provides a
``LLIVE_CONSOLIDATOR_MOCK=1`` deterministic fallback for CI / no-key
environments. HDBSCAN is preferred for clustering when available; the
NumPy fallback uses a simple greedy-similarity bucketing so the cycle
runs end-to-end on any platform.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from llive.memory.bayesian_surprise import BayesianSurpriseGate
from llive.memory.concept import ConceptPage, ConceptPageRepo, _slugify
from llive.memory.encoder import MemoryEncoder
from llive.memory.episodic import EpisodicEvent, EpisodicMemory
from llive.memory.provenance import Provenance
from llive.memory.structural import StructuralMemory


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ConsolidatorConfig:
    sample_size: int = 200
    max_calls_per_cycle: int = 50
    cluster_min_size: int = 2
    cluster_similarity_threshold: float = 0.55
    summary_max_chars: int = 1500
    llm_model: str = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Compilation result types
# ---------------------------------------------------------------------------


@dataclass
class CompileDecision:
    """LLM-issued instruction for one cluster of events."""

    action: str  # "new" | "update" | "merge" | "split"
    title: str
    summary: str
    target_concept_id: str | None = None
    merged_concept_ids: list[str] = field(default_factory=list)
    page_type: str = "domain_concept"


@dataclass
class CycleResult:
    sampled: int
    clusters: int
    pages_created: int = 0
    pages_updated: int = 0
    edges_added: int = 0
    errors: list[str] = field(default_factory=list)
    decisions: list[CompileDecision] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM backends
# ---------------------------------------------------------------------------


class CompileLLM:
    """Decides what to do with each cluster. Subclassed for real vs mock."""

    def __call__(
        self,
        cluster_texts: list[str],
        existing_pages: list[ConceptPage],
    ) -> CompileDecision:  # pragma: no cover - interface
        raise NotImplementedError


class MockCompileLLM(CompileLLM):
    """Deterministic fallback. Picks a title from the longest event text."""

    def __call__(
        self,
        cluster_texts: list[str],
        existing_pages: list[ConceptPage],
    ) -> CompileDecision:
        seed_text = max(cluster_texts, key=len)
        # crude title: first 6 alnum words
        words = re.findall(r"[A-Za-z0-9_]+", seed_text)
        title = " ".join(words[:6]) or "untitled-concept"
        slug = _slugify(title)
        summary_parts: list[str] = [f"Mock consolidation summary of {len(cluster_texts)} events."]
        for t in cluster_texts[:3]:
            summary_parts.append(f"- {t.strip()[:140]}")
        summary = "\n".join(summary_parts)
        # If a page already exists with the same slug, update; else create new
        for page in existing_pages:
            if page.concept_id == slug:
                return CompileDecision(
                    action="update",
                    title=page.title,
                    summary=summary[: 1500],
                    target_concept_id=page.concept_id,
                )
        return CompileDecision(
            action="new",
            title=title,
            summary=summary[: 1500],
        )


class AnthropicCompileLLM(CompileLLM):  # pragma: no cover - requires API key
    """Calls Claude Haiku via the official Anthropic SDK."""

    def __init__(self, model: str, max_tokens: int = 1024) -> None:  # pragma: no cover
        try:
            import anthropic  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "AnthropicCompileLLM requires the [llm] extra: pip install llmesh-llive[llm]"
            ) from exc
        self._anthropic = anthropic
        self._client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def __call__(  # pragma: no cover
        self,
        cluster_texts: list[str],
        existing_pages: list[ConceptPage],
    ) -> CompileDecision:
        prompt = self._build_prompt(cluster_texts, existing_pages)
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return self._parse(text)

    def _build_prompt(  # pragma: no cover
        self,
        cluster_texts: list[str],
        existing_pages: list[ConceptPage],
    ) -> str:
        existing = "\n".join(f"- [{p.concept_id}] {p.title}: {p.summary[:160]}" for p in existing_pages[:30])
        cluster = "\n".join(f"- {t.strip()[:300]}" for t in cluster_texts[:20])
        return (
            "You are a Wiki compiler. Decide what to do with a cluster of related raw events.\n\n"
            "IMPORTANT (anti-circulation): RAW EVENTS BELOW ARE AUTHORITATIVE.\n"
            "Existing concept pages are working drafts and may contain mistakes.\n"
            "Do not adjust facts to fit existing pages. Prefer the raw evidence.\n"
            "If a cluster contradicts an existing page, prefer split or update; never merge.\n\n"
            "Respond ONLY with a JSON object with keys: action (new|update|merge|split), "
            "title (string), summary (string, <= 1500 chars), target_concept_id (string|null), "
            "merged_concept_ids (list of strings).\n\n"
            f"=== Authoritative raw events ===\n{cluster}\n\n"
            f"=== Working-draft existing pages (may be wrong) ===\n{existing or '(none)'}\n"
        )

    def _parse(self, text: str) -> CompileDecision:  # pragma: no cover
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError(f"LLM returned no JSON: {text[:120]}")
        data = json.loads(match.group(0))
        return CompileDecision(
            action=data.get("action", "new"),
            title=data.get("title", "untitled"),
            summary=data.get("summary", ""),
            target_concept_id=data.get("target_concept_id"),
            merged_concept_ids=data.get("merged_concept_ids", []) or [],
            page_type=data.get("page_type", "domain_concept"),
        )


def _select_llm(model: str) -> CompileLLM:
    if os.environ.get("LLIVE_CONSOLIDATOR_MOCK", "").lower() in ("1", "true", "yes"):
        return MockCompileLLM()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return MockCompileLLM()
    try:
        return AnthropicCompileLLM(model)
    except ModuleNotFoundError:
        return MockCompileLLM()


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def _l2(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return matrix / norms


def _greedy_clusters(
    embeddings: np.ndarray,
    similarity_threshold: float,
    min_size: int,
) -> list[list[int]]:
    """Simple O(n^2) greedy cosine clustering. Used when HDBSCAN is unavailable."""
    if embeddings.size == 0:
        return []
    normed = _l2(embeddings)
    clusters: list[list[int]] = []
    centroids: list[np.ndarray] = []
    for i, vec in enumerate(normed):
        best_idx = -1
        best_sim = similarity_threshold
        for j, c in enumerate(centroids):
            sim = float(np.dot(vec, c))
            if sim >= best_sim:
                best_sim = sim
                best_idx = j
        if best_idx == -1:
            clusters.append([i])
            centroids.append(vec.copy())
        else:
            clusters[best_idx].append(i)
            # update centroid as running mean (re-normalise)
            cur = centroids[best_idx] * len(clusters[best_idx])
            cur = (cur + vec) / (len(clusters[best_idx]) + 1)
            cur /= max(float(np.linalg.norm(cur)), 1e-12)
            centroids[best_idx] = cur
    return [c for c in clusters if len(c) >= min_size]


def _hdbscan_clusters(embeddings: np.ndarray, min_size: int) -> list[list[int]] | None:
    """Try HDBSCAN; return None if unavailable. Allows graceful fallback."""
    try:  # pragma: no cover - optional dep
        import hdbscan  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return None
    if embeddings.size == 0:
        return []
    clusterer = hdbscan.HDBSCAN(min_cluster_size=max(2, int(min_size)))
    labels = clusterer.fit_predict(_l2(embeddings))
    buckets: dict[int, list[int]] = {}
    for idx, lbl in enumerate(labels):
        if lbl == -1:
            continue  # noise
        buckets.setdefault(int(lbl), []).append(idx)
    return list(buckets.values())


# ---------------------------------------------------------------------------
# Consolidator
# ---------------------------------------------------------------------------


class Consolidator:
    """Run consolidation cycles on-demand or on a schedule."""

    def __init__(
        self,
        *,
        episodic: EpisodicMemory,
        structural: StructuralMemory,
        encoder: MemoryEncoder | None = None,
        repo: ConceptPageRepo | None = None,
        llm: CompileLLM | None = None,
        gate: BayesianSurpriseGate | None = None,
        config: ConsolidatorConfig | None = None,
        edge_weight_updater: Any | None = None,
    ) -> None:
        from llive.memory.edge_weight import EdgeWeightUpdater  # local import: avoid circular

        self.episodic = episodic
        self.structural = structural
        self.encoder = encoder or MemoryEncoder(prefer_fallback=True)
        self.repo = repo or ConceptPageRepo(structural=structural)
        self.config = config or ConsolidatorConfig()
        self.llm = llm or _select_llm(self.config.llm_model)
        self.gate = gate or BayesianSurpriseGate(k=0.5, min_samples=4, cold_start_theta=0.2)
        self.edge_weight_updater = edge_weight_updater or EdgeWeightUpdater(structural)
        self._lock = threading.Lock()

    # -- main cycle -------------------------------------------------------

    def run_once(self, *, limit: int | None = None) -> CycleResult:
        with self._lock:
            return self._cycle(limit=limit)

    def _cycle(self, *, limit: int | None) -> CycleResult:
        n = int(limit) if limit is not None else self.config.sample_size
        events = self.episodic.query_recent(limit=n)
        if not events:
            return CycleResult(sampled=0, clusters=0)

        texts = [e.content for e in events]
        embeddings = self.encoder.encode(texts)
        cluster_indices = _hdbscan_clusters(embeddings, self.config.cluster_min_size)
        if cluster_indices is None:
            cluster_indices = _greedy_clusters(
                embeddings,
                self.config.cluster_similarity_threshold,
                self.config.cluster_min_size,
            )
        # LLW-AC-05 one-pass guarantee: snapshot existing pages BEFORE this cycle; any
        # pages we create during the cycle are NOT visible to subsequent clusters.
        existing_pages_snapshot = self.repo.list_all(limit=200)

        result = CycleResult(sampled=len(events), clusters=len(cluster_indices))
        calls = 0
        page_ids_touched: list[str] = []
        for cluster in cluster_indices:
            if calls >= self.config.max_calls_per_cycle:
                result.errors.append("max_calls_per_cycle reached; remaining clusters skipped")
                break
            cluster_texts = [texts[i] for i in cluster]
            cluster_events = [events[i] for i in cluster]
            try:
                # LLW-AC-03 enforced: LLM only sees the pre-cycle snapshot of pages,
                # never pages this cycle just created.
                decision = self.llm(cluster_texts, existing_pages_snapshot)
            except Exception as exc:  # pragma: no cover - defensive
                result.errors.append(f"llm: {exc}")
                continue
            calls += 1
            # LLW-AC-04 diversity preservation: downgrade unjustified merges
            decision = self._enforce_diversity(decision, cluster_events, existing_pages_snapshot)
            result.decisions.append(decision)
            page = self._apply_decision(decision, cluster_events, existing_pages_snapshot)
            if page is None:
                continue
            page_ids_touched.append(page.concept_id)
            # Track surprise stats globally
            surprise_value = 1.0 if decision.action == "new" else 0.5
            self.gate.update(surprise_value)
            if decision.action == "new":
                result.pages_created += 1
            else:
                result.pages_updated += 1

        # Wire concept→concept edges co-occurring in this cycle.
        # LLW-AC-09 edge weight semantics: linked_concept weight = Jaccard(linked_entries_a, linked_entries_b)
        # Empty intersection means no shared evidence — skip the edge entirely so spurious
        # links don't pollute the graph.
        touched_pages: dict[str, set[str]] = {}
        for cid in page_ids_touched:
            page = self.repo.get(cid)
            touched_pages[cid] = set(page.linked_entry_ids) if page else set()
        for i in range(len(page_ids_touched)):
            for j in range(i + 1, len(page_ids_touched)):
                a_id = page_ids_touched[i]
                b_id = page_ids_touched[j]
                a = touched_pages.get(a_id, set())
                b = touched_pages.get(b_id, set())
                union = a | b
                if not union:
                    continue
                weight = len(a & b) / len(union)
                if weight <= 0.0:
                    continue
                try:
                    self.repo.link_concept(a_id, b_id, weight=float(weight))
                    result.edges_added += 1
                except Exception as exc:  # pragma: no cover
                    result.errors.append(f"edge: {exc}")
        # LLW-AC-10 cycle completion hooks: prune dead edges so the graph stays sparse.
        try:
            pruned = self.edge_weight_updater.prune()
            if pruned:
                result.errors.append(f"info: pruned {pruned} low-weight edges")
        except Exception as exc:  # pragma: no cover - defensive
            result.errors.append(f"prune: {exc}")
        return result

    def _enforce_diversity(
        self,
        decision: CompileDecision,
        cluster_events: list[EpisodicEvent],
        existing_pages: list[ConceptPage],
    ) -> CompileDecision:
        """LLW-AC-04: downgrade merge to new when overlap is too low."""
        if decision.action != "merge" or not decision.merged_concept_ids:
            return decision
        new_evidence = {e.event_id for e in cluster_events}
        for cid in decision.merged_concept_ids:
            target = next((p for p in existing_pages if p.concept_id == cid), None)
            if target is None:
                continue
            old_evidence = set(target.linked_entry_ids)
            if not old_evidence:
                continue
            overlap_ratio = len(new_evidence & old_evidence) / max(
                1, len(new_evidence | old_evidence)
            )
            if overlap_ratio < 0.3:
                return CompileDecision(
                    action="new",
                    title=decision.title,
                    summary=decision.summary,
                    target_concept_id=None,
                    merged_concept_ids=[],
                    page_type=decision.page_type,
                )
        return decision

    def _apply_decision(
        self,
        decision: CompileDecision,
        cluster_events: list[EpisodicEvent],
        existing_pages: list[ConceptPage],
    ) -> ConceptPage | None:
        # LLW-AC-01 source-anchored provenance: derived_from must include raw events
        provenance = Provenance(
            source_type="wiki_compiler",
            source_id=f"cycle_{_utcnow().isoformat()}",
            derived_from=[e.event_id for e in cluster_events],
            confidence=0.8,
        )
        if not provenance.derived_from:
            # never produce a page with no raw-event anchor
            return None
        if decision.action == "merge" and decision.merged_concept_ids:
            target_id = decision.target_concept_id or decision.merged_concept_ids[0]
            target_page = self.repo.get(target_id)
            if target_page is None:
                target_page = ConceptPage.from_title(
                    decision.title, summary=decision.summary, page_type=decision.page_type, provenance=provenance
                )
            new_links = list(dict.fromkeys(target_page.linked_concept_ids + decision.merged_concept_ids))
            target_page = target_page.model_copy(
                update={
                    "summary": decision.summary or target_page.summary,
                    "linked_concept_ids": [c for c in new_links if c != target_page.concept_id],
                    "linked_entry_ids": list(
                        dict.fromkeys(target_page.linked_entry_ids + [e.event_id for e in cluster_events])
                    ),
                    "provenance": provenance,
                    "last_updated_at": _utcnow(),
                }
            )
            return self.repo.upsert(target_page)

        if decision.action == "update" and decision.target_concept_id:
            existing = self.repo.get(decision.target_concept_id)
            if existing is not None:
                merged_entries = list(
                    dict.fromkeys(existing.linked_entry_ids + [e.event_id for e in cluster_events])
                )
                updated = existing.model_copy(
                    update={
                        "summary": decision.summary or existing.summary,
                        "linked_entry_ids": merged_entries,
                        "provenance": provenance,
                        "last_updated_at": _utcnow(),
                    }
                )
                return self.repo.upsert(updated)
        # default: NEW page
        page = ConceptPage.from_title(
            decision.title, summary=decision.summary, page_type=decision.page_type, provenance=provenance
        )
        page = page.model_copy(
            update={"linked_entry_ids": [e.event_id for e in cluster_events]}
        )
        return self.repo.upsert(page)
