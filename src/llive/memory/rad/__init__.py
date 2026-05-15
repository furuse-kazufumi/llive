# SPDX-License-Identifier: Apache-2.0
"""RAD (Research Aggregation Directory) — Raptor 由来の知識庫。

llive の長期記憶層として、Raptor が育てた RAD コーパス (49 分野) を読み、
さらに生物学的記憶モデル (semantic → consolidation) から学習結果を
``_learned/<domain>/`` に書き戻すための統合 API。

レイアウト::

    data/rad/
      <domain>_v2/        ← 読み層 (Raptor 由来、不変)
      _learned/<domain>/  ← 書き層 (llive 学習堆積、provenance.json 付き)
      _index.json         ← scripts/import_rad.py が生成するメタ

Phase B (llive v0.2.1) で実装。`RadCorpusIndex` を単一エントリポイントとして
``list_domains()`` / ``query()`` / ``append_learning()`` を提供する。
"""

from llive.memory.rad.loader import RadCorpusIndex
from llive.memory.rad.types import DomainInfo, LearnedEntry, RadHit

__all__ = [
    "DomainInfo",
    "LearnedEntry",
    "RadCorpusIndex",
    "RadHit",
]
