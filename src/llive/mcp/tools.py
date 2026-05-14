"""Pure-Python tool implementations exposed via MCP.

Each ``tool_*`` function takes JSON-serialisable arguments and returns a
JSON-serialisable result. The MCP transport layer (``server.py``) is a thin
wrapper that calls these. This separation lets unit tests cover the actual
logic without needing an MCP runtime.

Default ``RadCorpusIndex`` instance is resolved lazily so the module imports
cheaply and tests can inject their own index via the ``index`` parameter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from llive.llm import GenerateRequest, LLMBackend, get_default_backend
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


def _resolve_backend(backend: LLMBackend | None) -> LLMBackend:
    return backend if backend is not None else get_default_backend()


def tool_vlm_describe_image(
    image_path: str | Path,
    *,
    prompt: str = "Describe this image in concrete detail.",
    domain_hint: str | None = None,
    model: str | None = None,
    max_tokens: int = 512,
    backend: LLMBackend | None = None,
    index: RadCorpusIndex | None = None,
) -> dict[str, Any]:
    """Phase C-2.1: describe an image with a VLM, optionally augmenting the prompt
    with RAD hints pulled from ``domain_hint``.

    If ``domain_hint`` is provided, the top 3 ``query_rad`` hits for the prompt
    text are prepended as a ``# RAD hints`` system block, so the VLM grounds its
    description in domain-specific terminology.
    """
    img = Path(image_path)
    if not img.is_file():
        raise FileNotFoundError(f"image not found: {img}")
    be = _resolve_backend(backend)
    if not be.supports_vlm:
        raise RuntimeError(
            f"backend {be.name!r} does not support VLM inputs; "
            f"set LLIVE_LLM_BACKEND=ollama (with a VLM model) or anthropic / openai with a vision-capable model"
        )
    system_parts: list[str] = []
    hint_used: list[str] = []
    if domain_hint:
        idx = index or get_default_index()
        hits = query(idx, prompt, domain=domain_hint, limit=3)
        if hits:
            system_parts.append("# RAD hints")
            for h in hits:
                hint_used.append(str(h.doc_path))
                if h.excerpt:
                    system_parts.append(f"- {h.excerpt}")
    req = GenerateRequest(
        prompt=prompt,
        system="\n".join(system_parts) if system_parts else None,
        images=[img],
        model=model,
        max_tokens=int(max_tokens),
    )
    resp = be.generate(req)
    return {
        "text": resp.text,
        "backend": resp.backend,
        "model": resp.model,
        "finish_reason": resp.finish_reason,
        "image_path": str(img),
        "rad_hints_used": hint_used,
    }


def tool_code_complete(
    code_context: str,
    instruction: str,
    *,
    model: str | None = None,
    max_tokens: int = 1024,
    backend: LLMBackend | None = None,
) -> dict[str, Any]:
    """Phase C-2.1: code completion / edit suggestion via the active LLM backend.

    The prompt format is conventional for code-specialised models
    (Qwen2.5-Coder / DeepSeek-Coder / Code Llama):

        <instruction>

        ```
        <code_context>
        ```
    """
    be = _resolve_backend(backend)
    prompt = f"{instruction}\n\n```\n{code_context}\n```\n"
    req = GenerateRequest(
        prompt=prompt,
        system="You are a coding assistant. Reply with only the requested code, no prose.",
        model=model,
        max_tokens=int(max_tokens),
        temperature=0.0,
    )
    resp = be.generate(req)
    return {
        "text": resp.text,
        "backend": resp.backend,
        "model": resp.model,
        "finish_reason": resp.finish_reason,
    }


def tool_code_review(
    code: str,
    *,
    domain: str = "security_corpus_v2",
    model: str | None = None,
    max_tokens: int = 1024,
    hint_limit: int = 5,
    backend: LLMBackend | None = None,
    index: RadCorpusIndex | None = None,
) -> dict[str, Any]:
    """Phase C-2.1: security code review with RAD hints from ``security_corpus_v2``.

    Searches RAD for terms in the code (tokenised) and prepends the top
    ``hint_limit`` excerpts so the LLM grounds its review in known
    vulnerability patterns from Raptor's hacker / security corpora.
    """
    idx = index or get_default_index()
    # Use the first 200 characters of code as the search query; this catches
    # function names and identifier tokens better than the full body.
    hits = query(idx, code[:200], domain=domain, limit=int(hint_limit))
    hint_text = ""
    hint_used: list[str] = []
    if hits:
        lines = ["# Relevant security knowledge from RAD"]
        for h in hits:
            hint_used.append(str(h.doc_path))
            if h.excerpt:
                lines.append(f"- {h.excerpt}")
        hint_text = "\n".join(lines)

    system_prompt = (
        "You are a security-focused code reviewer. "
        "Identify potential vulnerabilities, unsafe patterns, and edge cases. "
        "Cite specific lines. Output a Markdown bullet list."
    )
    if hint_text:
        system_prompt = f"{system_prompt}\n\n{hint_text}"

    be = _resolve_backend(backend)
    req = GenerateRequest(
        prompt=f"Review this code:\n\n```\n{code}\n```",
        system=system_prompt,
        model=model,
        max_tokens=int(max_tokens),
        temperature=0.1,
    )
    resp = be.generate(req)
    return {
        "text": resp.text,
        "backend": resp.backend,
        "model": resp.model,
        "finish_reason": resp.finish_reason,
        "rad_hints_used": hint_used,
        "domain": domain,
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
        {
            "name": "vlm_describe_image",
            "description": (
                "Describe an image with a vision-language model. "
                "Optionally augments the prompt with RAD hints from a domain."
            ),
            "input_schema": {
                "type": "object",
                "required": ["image_path"],
                "properties": {
                    "image_path": {"type": "string"},
                    "prompt": {"type": "string", "default": "Describe this image in concrete detail."},
                    "domain_hint": {"type": "string"},
                    "model": {"type": "string"},
                    "max_tokens": {"type": "integer", "default": 512, "minimum": 1, "maximum": 8192},
                },
            },
        },
        {
            "name": "code_complete",
            "description": "Code completion / edit suggestion via the active LLM backend.",
            "input_schema": {
                "type": "object",
                "required": ["code_context", "instruction"],
                "properties": {
                    "code_context": {"type": "string"},
                    "instruction": {"type": "string"},
                    "model": {"type": "string"},
                    "max_tokens": {"type": "integer", "default": 1024, "minimum": 1, "maximum": 16384},
                },
            },
        },
        {
            "name": "code_review",
            "description": (
                "Security-focused code review with RAD hints. "
                "Pulls top-N excerpts from `security_corpus_v2` (or a custom domain) "
                "and grounds the LLM review in known vulnerability patterns."
            ),
            "input_schema": {
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {"type": "string"},
                    "domain": {"type": "string", "default": "security_corpus_v2"},
                    "model": {"type": "string"},
                    "max_tokens": {"type": "integer", "default": 1024, "minimum": 1, "maximum": 16384},
                    "hint_limit": {"type": "integer", "default": 5, "minimum": 0, "maximum": 50},
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
    if name == "vlm_describe_image":
        return tool_vlm_describe_image(**args)
    if name == "code_complete":
        return tool_code_complete(**args)
    if name == "code_review":
        return tool_code_review(**args)
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
