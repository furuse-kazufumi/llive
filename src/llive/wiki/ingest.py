# SPDX-License-Identifier: Apache-2.0
"""External source ingest (LLW-06).

Supported source types: ``text`` / ``markdown`` / ``pdf`` / ``arxiv`` / ``url``.
PDF / arXiv / URL handlers require the ``[ingest]`` extra
(``pip install llmesh-llive[ingest]``); ``text`` and ``markdown`` work with
the core install.

After ingest, content is split into chunks (default 500 tokens-ish, char
fallback) and each chunk is written to ``EpisodicMemory`` with a
``Provenance`` row pointing at the source URI.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from llive.memory.episodic import EpisodicEvent, EpisodicMemory
from llive.memory.provenance import Provenance

# Chunk target ~500 tokens; we approximate with characters (≈4 chars/token).
DEFAULT_CHUNK_CHARS = 2000


@dataclass
class IngestResult:
    source: str
    source_type: str
    n_chunks: int
    event_ids: list[str]
    notes: list[str]


def _chunk_text(text: str, max_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    # split by paragraph first, then re-pack
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []
    cur_len = 0
    for p in paragraphs:
        plen = len(p) + 2
        if cur_len + plen > max_chars and buf:
            chunks.append("\n\n".join(buf))
            buf = [p]
            cur_len = plen
        else:
            buf.append(p)
            cur_len += plen
    if buf:
        chunks.append("\n\n".join(buf))
    # final guard: hard-split anything still too long
    final: list[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            final.append(c)
        else:
            for i in range(0, len(c), max_chars):
                final.append(c[i : i + max_chars])
    return final


def _chunk_markdown(text: str, max_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    """Split on markdown headings, keeping each section as one chunk (sub-split if too long)."""
    parts = re.split(r"(?m)^(#{1,6}\s+.*)$", text)
    # parts alternates [pre, heading, body, heading, body, ...]
    sections: list[str] = []
    if parts and parts[0].strip():
        sections.append(parts[0].strip())
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections.append(f"{heading}\n\n{body}".strip())
    out: list[str] = []
    for sec in sections:
        if len(sec) <= max_chars:
            out.append(sec)
        else:  # pragma: no cover - depends on huge markdown sections
            out.extend(_chunk_text(sec, max_chars))
    return [s for s in out if s.strip()]


# ---------------------------------------------------------------------------
# Source handlers
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_pdf(path: Path) -> str:  # pragma: no cover - optional dep
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PDF ingest requires the [ingest] extra: pip install llmesh-llive[ingest]"
        ) from exc
    reader = PdfReader(str(path))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def _fetch_arxiv(arxiv_id: str) -> str:  # pragma: no cover - network
    try:
        import arxiv
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "arXiv ingest requires the [ingest] extra: pip install llmesh-llive[ingest]"
        ) from exc
    search = arxiv.Search(id_list=[arxiv_id])
    result = next(iter(search.results()))
    return f"{result.title}\n\n{result.summary}"


def _fetch_url(url: str) -> str:  # pragma: no cover - network
    try:
        import requests
        from readability import Document
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "URL ingest requires the [ingest] extra: pip install llmesh-llive[ingest]"
        ) from exc
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    doc = Document(resp.text)
    return doc.summary(html_partial=False)


# ---------------------------------------------------------------------------
# Ingestor
# ---------------------------------------------------------------------------


class WikiIngestor:
    """Coordinates source-reading + chunking + episodic memory writes."""

    def __init__(self, episodic: EpisodicMemory) -> None:
        self.episodic = episodic

    def ingest(
        self,
        source: str,
        source_type: str = "text",
        *,
        chunk_chars: int = DEFAULT_CHUNK_CHARS,
        extra_tags: Iterable[str] = (),
    ) -> IngestResult:
        notes: list[str] = []
        if source_type == "text":
            content = _read_text(Path(source))
            chunks = _chunk_text(content, chunk_chars)
        elif source_type == "markdown":
            content = _read_markdown(Path(source))
            chunks = _chunk_markdown(content, chunk_chars)
        elif source_type == "pdf":  # pragma: no cover - requires pypdf + actual PDF
            content = _read_pdf(Path(source))
            chunks = _chunk_text(content, chunk_chars)
        elif source_type == "arxiv":  # pragma: no cover - requires arxiv + network
            content = _fetch_arxiv(source)
            chunks = _chunk_text(content, chunk_chars)
        elif source_type == "url":  # pragma: no cover - requires readability + network
            content = _fetch_url(source)
            chunks = _chunk_markdown(content, chunk_chars)
        else:
            raise ValueError(f"unknown source_type {source_type!r}")
        notes.append(f"chunked into {len(chunks)} chunk(s)")
        event_ids: list[str] = []
        for idx, chunk in enumerate(chunks):
            provenance = Provenance(
                source_type="imported",
                source_id=f"{source}#chunk_{idx}",
                confidence=0.8,
            )
            metadata = {"chunk_index": idx, "source_type": source_type, "tags": list(extra_tags)}
            event = EpisodicEvent(content=chunk, provenance=provenance, metadata=metadata)
            event_ids.append(self.episodic.write(event))
        return IngestResult(
            source=source, source_type=source_type, n_chunks=len(chunks), event_ids=event_ids, notes=notes
        )
