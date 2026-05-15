# SPDX-License-Identifier: Apache-2.0
"""Bundle format definition for cross-substrate migration (§MI1).

Bundle layout (tar.gz):
    manifest.json
    approval/ledger.db            (SqliteLedger をそのまま)
    sandbox/records.jsonl         (SandboxRecord 系の log)
    sandbox/denied_emits.jsonl    (production bus DENIED の観測)
    production/records.jsonl      (ProductionOutputBus.records())

manifest.json:
    {
      "schema_version": 1,
      "llive_version": "0.6.0",
      "source_substrate": {
        "platform": "...",
        "python_version": "...",
        "machine": "...",
        "hostname": "..."
      },
      "exported_at": "2026-05-16T08:42:00+00:00",
      "components": ["approval", "sandbox", "production"]
    }

schema_version は importer 側で互換性チェックに使う。MAJOR が違えば import 拒否。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class BundleManifest:
    """Bundle メタデータ. tar.gz 内 manifest.json と相互変換可能."""

    schema_version: int = SCHEMA_VERSION
    llive_version: str = ""
    source_substrate: dict[str, str] = field(default_factory=dict)
    exported_at: str = ""
    components: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> BundleManifest:
        data: dict[str, Any] = json.loads(text)
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            llive_version=str(data.get("llive_version", "")),
            source_substrate=dict(data.get("source_substrate", {})),
            exported_at=str(data.get("exported_at", "")),
            components=list(data.get("components", [])),
        )


@dataclass(frozen=True)
class Bundle:
    """tar.gz bundle の path と manifest のペア."""

    path: Path
    manifest: BundleManifest


__all__ = [
    "MANIFEST_FILENAME",
    "SCHEMA_VERSION",
    "Bundle",
    "BundleManifest",
]
