# SPDX-License-Identifier: Apache-2.0
"""Cross-Substrate Genome — 物理基盤越境ゲノム core (llive v0.I EV-37 案 E §7.2).

llive v0.F / v0.I で着地した 3 階建てゲノム
(:class:`ImplChromosome` / :class:`PromptChromosome` / :class:`MetaChromosome`,
:class:`Genome3D`) は **Python ランタイム上の個体** を前提とした表現だった.
本 module は v0.I 案 E (要件 §7) — Genome を **物理基盤 (substrate) に依存しない
抽象表現** で保持し, Python individual ↔ Rust individual ↔ neuromorphic chip ↔
BCI 経由人間個体 で同じ genotype を共有する skeleton — の core 部分を提供する.

具体 SubstrateAdapter 実装 (Python / Rust / Cython / Neuromorphic / BCI /
TypeScript) は :mod:`llive.perf.evolutionary.substrate_adapters` 側.

形式化 (要件 v0.I §7.2):

```python
@dataclass(frozen=True)
class AbstractGenome:
    intent: tuple[float, ...]            # 高次元意図 embedding (16 dim default)
    capabilities: tuple[str, ...]         # substrate 非依存能力 list
    rules: tuple[str, ...]                # 倫理 + 規律 (frozen_gene と連動可)
    history_hash: str                     # provenance (SHA-256 hex)
    intended_substrate: Substrate         # 主に動く想定の基盤

class SubstrateAdapter(Protocol):
    substrate: Substrate
    def from_abstract(self, g: AbstractGenome) -> object: ...
    def to_abstract(self, phenotype: object) -> AbstractGenome: ...
    def can_handle(self, intended: Substrate) -> bool: ...
```

設計方針:

- ``AbstractGenome`` は **完全に state-less / frozen / hashable**. EvolutionLoop /
  selector / fitness 評価は touch しない. tuple のみで構成し dict / list を
  含まないため pickle / json round-trip が容易.
- ``kolmogorov_proxy()`` は gzip ベース (Schmidhuber 2003 Gödel Machine /
  Cilibrasi & Vitanyi 2005 系の計算可能近似). 既存 MetaChromosome /
  ImplChromosome と同じ API.
- ``SubstrateAdapter`` は ``runtime_checkable`` Protocol. 各 substrate ごとに
  1 つ実装する. Python / Rust は :mod:`substrate_adapters` に skeleton stub,
  他は将来.

References:

- llive ``docs/requirements_v0.I_meta_evolution_and_cross_substrate.md`` §7.
- Schmidhuber, J. (2003). *Gödel Machines: Self-Referential Universal Problem
  Solvers Making Provably Optimal Self-Improvements.*
- Cilibrasi, R. & Vitányi, P. (2005). *Clustering by Compression.* IEEE TIT.
- Davies, M. et al. (2018). *Loihi: A Neuromorphic Manycore Processor.* IEEE Micro.
- Furber, S. B. et al. (2014). *The SpiNNaker Project.* Proc. IEEE.

Status (2026-05-22 着地): skeleton. AbstractGenome + Substrate enum +
SubstrateAdapter Protocol のみ. 具体 adapter は substrate_adapters.py 側.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: AbstractGenome.intent の default 次元. LLM embedding 圧縮後の固定長.
#: 16 dim は skeleton の妥協 (将来 256 / 1024 dim に拡張可).
DEFAULT_INTENT_DIM: int = 16


# ---------------------------------------------------------------------------
# Substrate enum
# ---------------------------------------------------------------------------


class Substrate(str, Enum):
    """物理基盤 (substrate) 識別子.

    ``str`` 派生にしてあるので JSON serialization / 比較が自然に動く.
    skeleton 段階では Python / Rust のみ実 adapter, 他は将来.
    """

    PYTHON = "python"
    RUST = "rust"
    CYTHON = "cython"
    NEUROMORPHIC = "neuromorphic"  # 将来 (Loihi 2 / SpiNNaker)
    BCI = "bci"                    # 将来 (neural signal → AbstractGenome)
    TYPESCRIPT = "typescript"      # 将来 (web / SDK side)


# ---------------------------------------------------------------------------
# AbstractGenome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AbstractGenome:
    """物理基盤越境で遺伝可能な抽象表現 (v0.I 案 E §7.2).

    Python individual ↔ Rust individual ↔ neuromorphic chip ↔ BCI 経由人間個体
    で同じ genotype を共有するための frozen dataclass. SubstrateAdapter 経由で
    各 substrate の concrete phenotype に変換される.

    全 field は tuple / str / Substrate のみ — list / dict を含まないため
    frozen / hashable / pickle 安全.
    """

    #: 高次元意図 embedding (固定長, default :data:`DEFAULT_INTENT_DIM`).
    #: LLM embedding を量子化 / 圧縮した結果を想定. tuple[float, ...] で frozen.
    intent: tuple[float, ...]

    #: substrate 非依存能力 list (例: "reason", "plan", "perceive_vision").
    #: 個体が「何ができるか」の抽象記述. tuple[str, ...] で frozen.
    capabilities: tuple[str, ...]

    #: 倫理 + 規律 (frozen_gene と連動可).
    #: 例: "no_self_modify_without_approval", "no_external_network".
    #: tuple[str, ...] で frozen.
    rules: tuple[str, ...]

    #: 来歴 (provenance). SHA-256 hex 文字列 (64 chars). 派生時に親 hash を
    #: 含めて再 hash する想定.
    history_hash: str

    #: 主に動く想定の基盤. SubstrateAdapter dispatch に使う.
    intended_substrate: Substrate

    #: intent の次元数. default は :data:`DEFAULT_INTENT_DIM` (= 16).
    #: 将来 256 / 1024 dim に拡張する余地を残す.
    intent_dim: int = DEFAULT_INTENT_DIM

    # ----- validation -----------------------------------------------------

    def __post_init__(self) -> None:
        # intent_dim sanity
        if self.intent_dim < 1:
            raise ValueError(f"intent_dim {self.intent_dim} must be >= 1")
        # intent 長さ
        if len(self.intent) != self.intent_dim:
            raise ValueError(
                f"intent length {len(self.intent)} != intent_dim {self.intent_dim}"
            )
        # intent 要素は float / int
        for i, v in enumerate(self.intent):
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise ValueError(
                    f"intent[{i}] must be int/float, got {type(v).__name__}"
                )
        # capabilities / rules は str only
        for i, cap in enumerate(self.capabilities):
            if not isinstance(cap, str):
                raise ValueError(
                    f"capabilities[{i}] must be str, got {type(cap).__name__}"
                )
        for i, rule in enumerate(self.rules):
            if not isinstance(rule, str):
                raise ValueError(
                    f"rules[{i}] must be str, got {type(rule).__name__}"
                )
        # history_hash: 64 hex chars (SHA-256)
        if not isinstance(self.history_hash, str):
            raise ValueError(
                f"history_hash must be str, got {type(self.history_hash).__name__}"
            )
        if len(self.history_hash) != 64:
            raise ValueError(
                f"history_hash must be 64 hex chars (SHA-256), "
                f"got len={len(self.history_hash)}"
            )
        try:
            int(self.history_hash, 16)
        except ValueError as e:
            raise ValueError(
                f"history_hash must be hex chars, got '{self.history_hash}'"
            ) from e
        # intended_substrate
        if not isinstance(self.intended_substrate, Substrate):
            raise ValueError(
                f"intended_substrate must be Substrate enum, "
                f"got {type(self.intended_substrate).__name__}"
            )

    # ----- factories ------------------------------------------------------

    @classmethod
    def default(
        cls,
        intended_substrate: Substrate = Substrate.PYTHON,
        intent_dim: int = DEFAULT_INTENT_DIM,
    ) -> AbstractGenome:
        """skeleton の zero-vector default. テスト / cold start 用.

        intent は全 0.0, capabilities / rules は空, history_hash は intent +
        substrate から決定的に計算.
        """
        intent = tuple(0.0 for _ in range(intent_dim))
        seed = f"{intended_substrate.value}:{intent}".encode()
        history_hash = hashlib.sha256(seed).hexdigest()
        return cls(
            intent=intent,
            capabilities=(),
            rules=(),
            history_hash=history_hash,
            intended_substrate=intended_substrate,
            intent_dim=intent_dim,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AbstractGenome:
        """dict → AbstractGenome (serialization 逆方向)."""
        substrate_raw = data["intended_substrate"]
        if isinstance(substrate_raw, Substrate):
            substrate = substrate_raw
        else:
            substrate = Substrate(str(substrate_raw))
        return cls(
            intent=tuple(float(v) for v in data["intent"]),
            capabilities=tuple(str(c) for c in data.get("capabilities", ())),
            rules=tuple(str(r) for r in data.get("rules", ())),
            history_hash=str(data["history_hash"]),
            intended_substrate=substrate,
            intent_dim=int(data.get("intent_dim", DEFAULT_INTENT_DIM)),
        )

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """AbstractGenome → JSON 化可能 dict (serialization 順方向)."""
        return {
            "intent": list(self.intent),
            "capabilities": list(self.capabilities),
            "rules": list(self.rules),
            "history_hash": self.history_hash,
            "intended_substrate": self.intended_substrate.value,
            "intent_dim": self.intent_dim,
        }

    def to_json_bytes(self) -> bytes:
        """JSON 化して bytes 化 (Kolmogorov complexity proxy 用)."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )

    # ----- Kolmogorov complexity proxy ------------------------------------

    def kolmogorov_proxy(self) -> int:
        """gzip 圧縮後 byte 数. Kolmogorov complexity の計算可能近似.

        MetaChromosome / ImplChromosome.kolmogorov_proxy と同型 API. gzip は
        LZ77 系で実用上 K の上界として機能する (Cilibrasi & Vitanyi 2005).
        """
        return len(gzip.compress(self.to_json_bytes()))


# ---------------------------------------------------------------------------
# SubstrateAdapter Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SubstrateAdapter(Protocol):
    """各 substrate ごとに 1 つ実装される protocol (v0.I §7.2).

    ``runtime_checkable`` のため ``isinstance(x, SubstrateAdapter)`` で
    duck-typing 検査可. ただし ``runtime_checkable`` Protocol は method 名
    のみ check するため, structural typing の責任は実装側に残る.

    具体実装は :mod:`llive.perf.evolutionary.substrate_adapters` 参照.
    """

    #: この adapter が担当する substrate. class attribute (instance attr 可).
    substrate: Substrate

    def from_abstract(self, g: AbstractGenome) -> object:
        """abstract → concrete phenotype.

        substrate 固有の表現 (Python dict / Rust struct via FFI /
        neuromorphic chip config / ...) に変換する.
        """
        ...

    def to_abstract(self, phenotype: object) -> AbstractGenome:
        """concrete phenotype → abstract (逆方向 / lift)."""
        ...

    def can_handle(self, intended: Substrate) -> bool:
        """この adapter が ``intended`` substrate を扱えるか.

        通常は ``intended == self.substrate`` だが, 将来 fallback chain
        (Rust adapter が cython も扱う等) で複数 substrate を返す余地を残す.
        """
        ...


__all__ = [
    "DEFAULT_INTENT_DIM",
    "AbstractGenome",
    "Substrate",
    "SubstrateAdapter",
]
