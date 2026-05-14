"""Pure-Python tool implementations exposed via MCP.

Each ``tool_*`` function takes JSON-serialisable arguments and returns a
JSON-serialisable result. The MCP transport layer (``server.py``) is a thin
wrapper that calls these. This separation lets unit tests cover the actual
logic without needing an MCP runtime.

Default ``RadCorpusIndex`` instance is resolved lazily so the module imports
cheaply and tests can inject their own index via the ``index`` parameter.
"""

from __future__ import annotations

from typing import Any

from llive.memory.provenance import Provenance
from llive.memory.rad import RadCorpusIndex
from llive.memory.rad.append import append_learning
from llive.memory.rad.query import query
from llive.memory.rad.skills import detect_skill_index

_DEFAULT_INDEX: RadCorpusIndex | None = None


def get_default_index() -> RadCorpusIndex:
    """Lazy-init shared ``RadCorpusIndex`` for MCP tools."""
    global _DEFAULT_INDEX
    if _DEFAULT_INDEX is None:
        _DEFAULT_INDEX = RadCorpusIndex()
    return _DEFAULT_INDEX


def reset_default_index() -> None:
    """For tests: drop the cached default index."""
    global _DEFAULT_INDEX
    _DEFAULT_INDEX = None


def tool_list_rad_domains(
    *,
    index: RadCorpusIndex | None = None,
    include_learned: bool = True,
) -> list[dict[str, Any]]:
    """Return all known RAD domains with metadata."""
    idx = index or get_default_index()
    domains = idx.list_domains() if include_learned else idx.list_read_domains()
    out: list[dict[str, Any]] = []
    for name in domains:
        info = idx.get_domain_info(name)
        if info is None:
            continue
        out.append(
            {
                "name": info.name,
                "path": str(info.path),
                "file_count": info.file_count,
                "bytes": info.bytes,
                "is_learned": info.is_learned,
                "imported_at": info.imported_at,
            }
        )
    return out


def tool_get_domain_info(
    domain: str,
    *,
    index: RadCorpusIndex | None = None,
) -> dict[str, Any] | None:
    """Return metadata for a single domain, including corpus2skill hints if present."""
    idx = index or get_default_index()
    info = idx.get_domain_info(domain)
    if info is None:
        return None
    result: dict[str, Any] = {
        "name": info.name,
        "path": str(info.path),
        "file_count": info.file_count,
        "bytes": info.bytes,
        "is_learned": info.is_learned,
        "imported_at": info.imported_at,
    }
    skill = detect_skill_index(info.path, info.name)
    if skill is not None:
        result["skill_index"] = {
            "index_path": str(skill.index_path),
            "metadata": skill.metadata,
            "sections": skill.sections,
        }
    return result


def tool_query_rad(
    keywords: str | list[str],
    *,
    domain: str | list[str] | None = None,
    limit: int = 10,
    include_learned: bool = True,
    index: RadCorpusIndex | None = None,
) -> list[dict[str, Any]]:
    """Search RAD corpora for documents matching the given keywords."""
    idx = index or get_default_index()
    hits = query(
        idx,
        keywords,
        domain=domain,
        limit=limit,
        include_learned=include_learned,
    )
    return [
        {
            "domain": h.domain,
            "doc_path": str(h.doc_path),
            "score": h.score,
            "excerpt": h.excerpt,
            "matched_terms": h.matched_terms,
        }
        for h in hits
    ]


def tool_read_document(
    domain: str,
    rel_path: str,
    *,
    max_bytes: int = 64 * 1024,
    index: RadCorpusIndex | None = None,
) -> dict[str, Any]:
    """Return a single document's text (truncated at ``max_bytes`` for safety)."""
    idx = index or get_default_index()
    text = idx.read_document(domain, rel_path)
    truncated = False
    if len(text) > max_bytes:
        text = text[:max_bytes]
        truncated = True
    return {
        "domain": domain,
        "rel_path": rel_path,
        "text": text,
        "truncated": truncated,
    }


def tool_append_learning(
    domain: str,
    content: str,
    *,
    source_type: str = "llm_generation",
    source_id: str = "",
    confidence: float = 1.0,
    derived_from: list[str] | None = None,
    doc_id: str | None = None,
    index: RadCorpusIndex | None = None,
) -> dict[str, Any]:
    """Persist a learned document into ``_learned/<domain>/``."""
    idx = index or get_default_index()
    prov = Provenance(
        source_type=source_type,
        source_id=source_id,
        confidence=confidence,
        derived_from=list(derived_from or []),
    )
    entry = append_learning(idx, domain, content, prov, doc_id=doc_id)
    return {
        "domain": entry.domain,
        "doc_id": entry.doc_id,
        "doc_path": str(entry.doc_path),
        "provenance_path": str(entry.provenance_path),
    }


def tool_describe() -> list[dict[str, Any]]:
    """Return a JSON schema-style description of all tools for MCP registration."""
    return [
        {
            "name": "list_rad_domains",
            "description": "List all RAD knowledge-base domains with file counts and learned-flag.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "include_learned": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include _learned/ write-layer domains.",
                    },
                },
            },
        },
        {
            "name": "get_domain_info",
            "description": "Get metadata for one domain (including corpus2skill hints if present).",
            "input_schema": {
                "type": "object",
                "required": ["domain"],
                "properties": {"domain": {"type": "string"}},
            },
        },
        {
            "name": "query_rad",
            "description": "Search RAD corpora for documents matching the given keywords.",
            "input_schema": {
                "type": "object",
                "required": ["keywords"],
                "properties": {
                    "keywords": {"type": ["string", "array"], "items": {"type": "string"}},
                    "domain": {"type": ["string", "array", "null"]},
                    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
                    "include_learned": {"type": "boolean", "default": True},
                },
            },
        },
        {
            "name": "read_document",
            "description": "Read a specific document from a RAD domain.",
            "input_schema": {
                "type": "object",
                "required": ["domain", "rel_path"],
                "properties": {
                    "domain": {"type": "string"},
                    "rel_path": {"type": "string"},
                    "max_bytes": {"type": "integer", "default": 65536},
                },
            },
        },
        {
            "name": "append_learning",
            "description": "Persist a learned document into the _learned/ write layer with provenance.",
            "input_schema": {
                "type": "object",
                "required": ["domain", "content"],
                "properties": {
                    "domain": {"type": "string"},
                    "content": {"type": "string"},
                    "source_type": {"type": "string", "default": "llm_generation"},
                    "source_id": {"type": "string"},
                    "confidence": {"type": "number", "default": 1.0, "minimum": 0.0, "maximum": 1.0},
                    "derived_from": {"type": "array", "items": {"type": "string"}},
                    "doc_id": {"type": "string"},
                },
            },
        },
    ]


def dispatch(name: str, arguments: dict[str, Any]) -> Any:
    """Generic dispatch — used by the MCP server wiring.

    Raises:
        KeyError: if ``name`` is unknown.
    """
    args = dict(arguments or {})
    if name == "list_rad_domains":
        return tool_list_rad_domains(**args)
    if name == "get_domain_info":
        return tool_get_domain_info(**args)
    if name == "query_rad":
        return tool_query_rad(**args)
    if name == "read_document":
        return tool_read_document(**args)
    if name == "append_learning":
        return tool_append_learning(**args)
    raise KeyError(f"unknown tool: {name}")


# Public re-export
__all__ = [
    "dispatch",
    "get_default_index",
    "reset_default_index",
    "tool_append_learning",
    "tool_describe",
    "tool_get_domain_info",
    "tool_list_rad_domains",
    "tool_query_rad",
    "tool_read_document",
]

# Keep import linter happy by referencing imported `asdict` even when unused;
# Phase C-2.1 will use it when adding tool_recall_memory.
_ = asdict
