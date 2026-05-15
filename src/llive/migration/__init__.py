# SPDX-License-Identifier: Apache-2.0
"""llive.migration — Cross-substrate state migration (spec §MI1).

Spec §MI1: 同じ agent state を異なる substrate (host / OS / Python 環境) に
携行して再開できること。MVP は classical-digital 同士の migration を
SQLite + JSONL bundle で実証する。

公開 API:
    - export_state(...) -> Path: 現在の state を tar.gz bundle に書き出す
    - import_state(bundle, dest) -> ImportResult: bundle を展開して state 復元
    - Bundle: bundle メタデータ (manifest.json と一致)
"""

from llive.migration.bundle import SCHEMA_VERSION, Bundle, BundleManifest
from llive.migration.exporter import export_state
from llive.migration.importer import (
    ImportResult,
    IncompatibleBundleError,
    import_state,
)

__all__ = [
    "SCHEMA_VERSION",
    "Bundle",
    "BundleManifest",
    "ImportResult",
    "IncompatibleBundleError",
    "export_state",
    "import_state",
]
