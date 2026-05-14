"""``RadCorpusIndex`` — unified read + write entry point for the RAD knowledge base."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from llive.memory.rad.types import DomainInfo

INDEX_FILE = "_index.json"
LEARNED_DIR = "_learned"


def _resolve_root(arg: Path | str | None) -> Path:
    """Resolve RAD root directory.

    Precedence: ``arg`` > ``$LLIVE_RAD_DIR`` > ``$RAPTOR_CORPUS_DIR`` > ``<repo>/data/rad``.
    """
    if arg is not None:
        return Path(arg).resolve()
    env = os.environ.get("LLIVE_RAD_DIR") or os.environ.get("RAPTOR_CORPUS_DIR")
    if env:
        return Path(env).resolve()
    # repo's data/rad/  (llive/src/llive/memory/rad/loader.py から 4 階層上が repo root)
    repo_root = Path(__file__).resolve().parents[4]
    return (repo_root / "data" / "rad").resolve()


class RadCorpusIndex:
    """Single entry point that exposes both Raptor RAD (read) and llive learned writes.

    Thread-safe: directory scans are guarded by an internal lock so multiple consumers
    can share one index instance.
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root: Path = _resolve_root(root)
        self._lock = threading.Lock()
        self._domains: dict[str, DomainInfo] | None = None  # lazy
        self._index_data: dict | None = None

    # -- root / metadata ---------------------------------------------------

    @property
    def learned_root(self) -> Path:
        return self.root / LEARNED_DIR

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_FILE

    def reload(self) -> None:
        """Force re-scan on next call."""
        with self._lock:
            self._domains = None
            self._index_data = None

    def _load_index_file(self) -> dict | None:
        path = self.index_path
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    # -- domain enumeration -----------------------------------------------

    def list_domains(self) -> list[str]:
        """Return all known domain names (read mirrors + learned write layer)."""
        return sorted(self._scan().keys())

    def list_read_domains(self) -> list[str]:
        """Return only read-side domains (Raptor mirrors). Excludes ``_learned/``."""
        return sorted(name for name, info in self._scan().items() if not info.is_learned)

    def list_learned_domains(self) -> list[str]:
        """Return only learned write-layer domains."""
        return sorted(name for name, info in self._scan().items() if info.is_learned)

    def get_domain_info(self, name: str) -> DomainInfo | None:
        return self._scan().get(name)

    def has_domain(self, name: str) -> bool:
        return name in self._scan()

    def _scan(self) -> dict[str, DomainInfo]:
        with self._lock:
            if self._domains is not None:
                return self._domains
            domains: dict[str, DomainInfo] = {}
            if not self.root.exists():
                self._domains = domains
                return domains

            index_data = self._load_index_file() or {}
            corpora_meta = index_data.get("corpora", {}) if isinstance(index_data, dict) else {}

            # 1) Raptor mirror directories (any dir except _learned and dot-prefixed)
            for child in self.root.iterdir():
                if not child.is_dir():
                    continue
                if child.name.startswith("_") or child.name.startswith("."):
                    continue
                meta = corpora_meta.get(child.name, {}) if isinstance(corpora_meta, dict) else {}
                domains[child.name] = DomainInfo(
                    name=child.name,
                    path=child,
                    file_count=int(meta.get("file_count", 0)) if isinstance(meta, dict) else 0,
                    bytes=int(meta.get("bytes", 0)) if isinstance(meta, dict) else 0,
                    is_learned=False,
                    imported_at=str(meta.get("imported_at", "")) if isinstance(meta, dict) else "",
                )

            # 2) Learned write layer (_learned/<domain>/)
            learned = self.learned_root
            if learned.is_dir():
                for sub in learned.iterdir():
                    if not sub.is_dir() or sub.name.startswith("_") or sub.name.startswith("."):
                        continue
                    # Prefix learned entries with "_learned/" to avoid name collision with read mirrors
                    domains[f"_learned/{sub.name}"] = DomainInfo(
                        name=f"_learned/{sub.name}",
                        path=sub,
                        is_learned=True,
                    )

            self._domains = domains
            self._index_data = index_data if isinstance(index_data, dict) else None
            return domains

    # -- document retrieval -----------------------------------------------

    def iter_documents(self, domain: str) -> list[Path]:
        """List all file paths under a domain (non-recursive into subdirs is fine for flat corpora)."""
        info = self.get_domain_info(domain)
        if info is None:
            return []
        return sorted(p for p in info.path.rglob("*") if p.is_file())

    def read_document(self, domain: str, rel_path: str | Path) -> str:
        """Read a single document's text content (UTF-8 with replacement on decode errors)."""
        info = self.get_domain_info(domain)
        if info is None:
            raise FileNotFoundError(f"unknown domain: {domain}")
        full = (info.path / rel_path).resolve()
        # Anti path-traversal: ensure full path stays within domain root
        try:
            full.relative_to(info.path.resolve())
        except ValueError as exc:
            raise PermissionError(f"path traversal blocked: {rel_path}") from exc
        if not full.is_file():
            raise FileNotFoundError(f"not a file: {rel_path}")
        return full.read_text(encoding="utf-8", errors="replace")
