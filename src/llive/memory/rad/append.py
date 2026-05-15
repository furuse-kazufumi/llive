# SPDX-License-Identifier: Apache-2.0
"""Write layer: persist llive-learned entries into ``data/rad/_learned/<domain>/``.

Each learned entry consists of two files:

* ``<doc_id>.md`` — the textual content (Markdown by convention).
* ``<doc_id>.provenance.json`` — required provenance metadata (``Provenance`` model).

``doc_id`` is generated as ``YYYYMMDDTHHMMSSZ-<shorthash>`` for sort-friendliness.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from llive.memory.provenance import Provenance
from llive.memory.rad.loader import RadCorpusIndex
from llive.memory.rad.types import LearnedEntry


def _now_iso_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _short_hash(content: str, n: int = 8) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:n]


def _sanitize_domain(name: str) -> str:
    # Forbid path separators in domain names (defensive against caller mistakes)
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"invalid domain name for learned write: {name!r}")
    return name


def append_learning(
    index: RadCorpusIndex,
    domain: str,
    content: str,
    provenance: Provenance,
    *,
    doc_id: str | None = None,
) -> LearnedEntry:
    """Persist a learned document into the write layer for ``domain``.

    Args:
        index: ``RadCorpusIndex`` controlling the write layer location.
        domain: Logical domain name (will be created under ``_learned/<domain>/``).
        content: Textual body to persist.
        provenance: Required ``Provenance`` metadata (source_type, source_id, ...).
        doc_id: Optional pre-computed doc id. Default = timestamp + short content hash.

    Returns:
        ``LearnedEntry`` pointing at the newly written files.

    Raises:
        ValueError: If ``domain`` contains path separators or is dot-prefixed.
    """
    safe = _sanitize_domain(domain)
    if doc_id is None:
        doc_id = f"{_now_iso_compact()}-{_short_hash(content)}"

    dest_dir = index.learned_root / safe
    dest_dir.mkdir(parents=True, exist_ok=True)

    doc_path = dest_dir / f"{doc_id}.md"
    prov_path = dest_dir / f"{doc_id}.provenance.json"

    doc_path.write_text(content, encoding="utf-8")
    prov_path.write_text(provenance.to_json(), encoding="utf-8")

    # Invalidate cached domain scan so the new write is visible
    index.reload()

    return LearnedEntry(
        domain=f"_learned/{safe}",
        doc_id=doc_id,
        doc_path=doc_path,
        provenance_path=prov_path,
    )
