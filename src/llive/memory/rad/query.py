"""Keyword + filename search over RAD corpora.

Phase B initial implementation uses stdlib-only token matching:

1. **Filename score** — tokens matching filename get high weight (cheap, very signal-rich for skill-hierarchies).
2. **Content score** — tokens matching file body get lower weight per occurrence.
3. **Total** — ``filename_score * 3 + content_score`` to bias toward title/path matches.

This is intentionally crude — Phase 2 of llive will plug in semantic embedding search
via ``SemanticMemory`` once a corpus encoder is ready. For now, byte-level keyword
matching keeps the dependency footprint at zero.
"""

from __future__ import annotations

import re
from pathlib import Path

from llive.memory.rad.loader import RadCorpusIndex
from llive.memory.rad.types import RadHit

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)
_DEFAULT_MAX_BYTES_PER_FILE = 256 * 1024  # 256 KiB; longer files are scanned in slices
_DEFAULT_EXCERPT_RADIUS = 80


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _normalize_terms(keywords: str | list[str]) -> list[str]:
    if isinstance(keywords, str):
        toks = _tokenize(keywords)
    else:
        toks: list[str] = []
        for k in keywords:
            toks.extend(_tokenize(k))
    # 重複除去 (出現順保持)
    seen: set[str] = set()
    out: list[str] = []
    for t in toks:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _score_filename(path: Path, terms: list[str]) -> tuple[float, list[str]]:
    stem_tokens = set(_tokenize(path.stem.replace("_", " ").replace("-", " ")))
    matched = [t for t in terms if t in stem_tokens]
    return float(len(matched)), matched


def _score_content(text: str, terms: list[str], max_bytes: int) -> tuple[float, list[str], str]:
    """Returns (score, matched_terms, excerpt)."""
    snippet = text[:max_bytes] if len(text) > max_bytes else text
    lower = snippet.lower()
    matched: list[str] = []
    total = 0
    first_hit_pos = -1
    for t in terms:
        if not t:
            continue
        pos = lower.find(t)
        if pos < 0:
            continue
        count = lower.count(t)
        matched.append(t)
        total += count
        if first_hit_pos < 0 or pos < first_hit_pos:
            first_hit_pos = pos
    if first_hit_pos < 0:
        return 0.0, matched, ""
    start = max(0, first_hit_pos - _DEFAULT_EXCERPT_RADIUS)
    end = min(len(snippet), first_hit_pos + _DEFAULT_EXCERPT_RADIUS)
    excerpt = snippet[start:end].replace("\n", " ").strip()
    return float(total), matched, excerpt


def query(
    index: RadCorpusIndex,
    keywords: str | list[str],
    *,
    domain: str | list[str] | None = None,
    limit: int = 10,
    include_learned: bool = True,
    max_bytes_per_file: int = _DEFAULT_MAX_BYTES_PER_FILE,
) -> list[RadHit]:
    """Search RAD corpora for documents matching the given keywords.

    Args:
        index: ``RadCorpusIndex`` instance.
        keywords: A search string or a list of strings.
        domain: Restrict to a single domain or a list of domains. ``None`` = all.
        limit: Maximum number of hits to return.
        include_learned: If ``True``, also search the ``_learned/`` write layer.
        max_bytes_per_file: Truncate each file content scan at this many bytes (perf cap).

    Returns:
        Hits sorted by descending score (top ``limit`` returned).
    """
    terms = _normalize_terms(keywords)
    if not terms:
        return []

    # Resolve domain set
    if domain is None:
        domains = index.list_domains() if include_learned else index.list_read_domains()
    elif isinstance(domain, str):
        domains = [domain]
    else:
        domains = list(domain)
    if not include_learned:
        domains = [d for d in domains if not d.startswith("_learned/")]

    hits: list[RadHit] = []
    for dom in domains:
        if not index.has_domain(dom):
            continue
        for path in index.iter_documents(dom):
            fn_score, fn_matched = _score_filename(path, terms)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            cont_score, cont_matched, excerpt = _score_content(text, terms, max_bytes_per_file)
            total = fn_score * 3.0 + cont_score
            if total <= 0:
                continue
            matched = sorted(set(fn_matched) | set(cont_matched))
            hits.append(
                RadHit(
                    domain=dom,
                    doc_path=path,
                    score=total,
                    excerpt=excerpt,
                    matched_terms=matched,
                )
            )

    hits.sort(key=lambda h: (-h.score, str(h.doc_path)))
    return hits[:limit]
