# SPDX-License-Identifier: Apache-2.0
"""Cross-Substrate Genome — 物理基盤越境ゲノム (llive v0.I EV-37/38 案 E).

llive v0.F / v0.I で着地した 3 階建てゲノム
(:class:`ImplChromosome` / :class:`PromptChromosome` / :class:`MetaChromosome`,
:class:`Genome3D`) は **Python ランタイム上の個体** を前提とした表現だった.
本 module は v0.I 案 E (要件 §7) — Genome を **物理基盤 (substrate) に依存しない
抽象表現** で保持し, Python individual ↔ Rust individual ↔ neuromorphic chip ↔
BCI 経由人間個体 で同じ genotype を共有する skeleton — を提供する.

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

Substrates (本 skeleton では Python / Rust のみ実 stub, 他は NotImplementedError):

* :attr:`Substrate.PYTHON` — llive Python individual (現状の Genome3D-like dict)
* :attr:`Substrate.RUST` — Rust individual (RUST-FX hot path; FFI bridge は将来)
* :attr:`Substrate.CYTHON` — Cython 実装 (将来)
* :attr:`Substrate.NEUROMORPHIC` — Loihi 2 / SpiNNaker chip (将来 / R&D anchor)
* :attr:`Substrate.BCI` — 神経信号 → AbstractGenome 変換 (将来 / 長期 R&D)
* :attr:`Substrate.TYPESCRIPT` — web / SDK side individual (将来)

設計方針:

- ``AbstractGenome`` は **完全に state-less / frozen / hashable**. EvolutionLoop /
  selector / fitness 評価は touch しない. tuple のみで構成し dict / list を
  含まないため pickle / json round-trip が容易.
- ``kolmogorov_proxy()`` は gzip ベース (Schmidhuber 2003 Gödel Machine /
  Cilibrasi & Vitanyi 2005 系の計算可能近似). 既存 MetaChromosome /
  ImplChromosome と同じ API.
- ``SubstrateAdapter`` は ``runtime_checkable`` Protocol. 各 substrate ごとに
  1 つ実装する. Python / Rust は本 skeleton で stub. 他は将来.

References:

- llive ``docs/requirements_v0.I_meta_evolution_and_cross_substrate.md`` §7.
- Schmidhuber, J. (2003). *Gödel Machines: Self-Referential Universal Problem
  Solvers Making Provably Optimal Self-Improvements.*
- Cilibrasi, R. & Vitányi, P. (2005). *Clustering by Compression.* IEEE TIT.
- Davies, M. et al. (2018). *Loihi: A Neuromorphic Manycore Processor.* IEEE Micro.
- Furber, S. B. et al. (2014). *The SpiNNaker Project.* Proc. IEEE.

Status (2026-05-22 着地): skeleton. AbstractGenome + Substrate enum +
SubstrateAdapter Protocol + Python / Rust stub adapter のみ. 実 FFI bridge /
BCI 連動 / neuromorphic dispatch は将来 (EV-39 / EV-40 以降).
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
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
        # intent 長さ
        if len(self.intent) != self.intent_dim:
            raise ValueError(
                f"intent length {len(self.intent)} != intent_dim {self.intent_dim}"
            )
        # intent 要素は float
        for i, v in enumerate(self.intent):
            if not isinstance(v, (int, float)):
                raise ValueError(
                    f"intent[{i}] must be int/float, got {type(v).__name__}"
                )
        if self.intent_dim < 1:
            raise ValueError(f"intent_dim {self.intent_dim} must be >= 1")
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
        # history_hash: 64 hex chars (SHA-256) — skeleton 段階では length のみ
        if not isinstance(self.history_hash, str):
            raise ValueError(
                f"history_hash must be str, got {type(self.history_hash).__name__}"
            )
        if len(self.history_hash) != 64:
            raise ValueError(
                f"history_hash must be 64 hex chars (SHA-256), got len={len(self.history_hash)}"
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
        # determinstic history_hash from intent + substrate (skeleton seed)
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
    だけ check するため, structural typing の責任は実装側に残る.
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


# ---------------------------------------------------------------------------
# Python substrate adapter (skeleton)
# ---------------------------------------------------------------------------


@dataclass
class PythonSubstrateAdapter:
    """Python individual の skeleton adapter (v0.I §7.2 PythonSubstrate).

    abstract genome を Python dict (現状の Genome3D-like 表現) に変換 / 逆変換
    する. 実 EvolutionLoop / Population への注入は将来 (EV-39 以降).
    """

    substrate: Substrate = field(default=Substrate.PYTHON)

    def from_abstract(self, g: AbstractGenome) -> dict[str, Any]:
        """abstract → Python dict (Genome3D-like 表現の skeleton)."""
        return {
            "intent": tuple(g.intent),
            "capabilities": tuple(g.capabilities),
            "rules": tuple(g.rules),
            "history_hash": g.history_hash,
            "intent_dim": g.intent_dim,
            "intended_substrate": g.intended_substrate.value,
        }

    def to_abstract(self, phenotype: dict[str, Any]) -> AbstractGenome:
        """Python dict → AbstractGenome (skeleton, intent_dim 補完あり)."""
        intent = tuple(float(v) for v in phenotype["intent"])
        intent_dim = int(phenotype.get("intent_dim", len(intent)))
        substrate_raw = phenotype.get("intended_substrate", Substrate.PYTHON)
        if isinstance(substrate_raw, Substrate):
            substrate = substrate_raw
        else:
            substrate = Substrate(str(substrate_raw))
        history_hash = phenotype.get("history_hash")
        if history_hash is None:
            # skeleton: deterministic hash from intent
            seed = f"{substrate.value}:{intent}".encode()
            history_hash = hashlib.sha256(seed).hexdigest()
        return AbstractGenome(
            intent=intent,
            capabilities=tuple(str(c) for c in phenotype.get("capabilities", ())),
            rules=tuple(str(r) for r in phenotype.get("rules", ())),
            history_hash=str(history_hash),
            intended_substrate=substrate,
            intent_dim=intent_dim,
        )

    def can_handle(self, intended: Substrate) -> bool:
        return intended == Substrate.PYTHON


# ---------------------------------------------------------------------------
# Rust substrate adapter (skeleton stub)
# ---------------------------------------------------------------------------


@dataclass
class RustSubstrateAdapter:
    """Rust individual の skeleton stub (v0.I §7.2 RustSubstrate).

    FFI bridge (PyO3 / llive RUST-FX hot path 経由) は将来 (RUST-15 以降).
    本 skeleton では ``from_abstract`` は dict (FFI 引き渡し直前の表現) を
    返し, ``to_abstract`` は同 dict を AbstractGenome に lift する.
    """

    substrate: Substrate = field(default=Substrate.RUST)

    def from_abstract(self, g: AbstractGenome) -> dict[str, Any]:
        """abstract → Rust FFI 引き渡し直前の dict (skeleton).

        将来 PyO3 経由 ``llive_rs.Individual`` に変換する.
        """
        return {
            "__rust_ffi_payload__": True,
            "intent": tuple(g.intent),
            "capabilities": tuple(g.capabilities),
            "rules": tuple(g.rules),
            "history_hash": g.history_hash,
            "intent_dim": g.intent_dim,
            "intended_substrate": g.intended_substrate.value,
        }

    def to_abstract(self, phenotype: dict[str, Any]) -> AbstractGenome:
        """Rust FFI payload dict → AbstractGenome (skeleton lift)."""
        intent = tuple(float(v) for v in phenotype["intent"])
        intent_dim = int(phenotype.get("intent_dim", len(intent)))
        substrate_raw = phenotype.get("intended_substrate", Substrate.RUST)
        if isinstance(substrate_raw, Substrate):
            substrate = substrate_raw
        else:
            substrate = Substrate(str(substrate_raw))
        history_hash = phenotype.get("history_hash")
        if history_hash is None:
            seed = f"{substrate.value}:{intent}".encode()
            history_hash = hashlib.sha256(seed).hexdigest()
        return AbstractGenome(
            intent=intent,
            capabilities=tuple(str(c) for c in phenotype.get("capabilities", ())),
            rules=tuple(str(r) for r in phenotype.get("rules", ())),
            history_hash=str(history_hash),
            intended_substrate=substrate,
            intent_dim=intent_dim,
        )

    def can_handle(self, intended: Substrate) -> bool:
        return intended == Substrate.RUST


# ---------------------------------------------------------------------------
# Future-substrate stub adapters (raise NotImplementedError)
# ---------------------------------------------------------------------------


@dataclass
class CythonSubstrateAdapter:
    """Cython individual の placeholder stub (v0.I 将来).

    Cython 実装の FFI bridge は v0.7 RUST-FX matrix で要評価. skeleton 段階
    では ``from_abstract`` / ``to_abstract`` は ``NotImplementedError``.
    """

    substrate: Substrate = field(default=Substrate.CYTHON)

    def from_abstract(self, g: AbstractGenome) -> object:
        raise NotImplementedError(
            "CythonSubstrateAdapter is a v0.I future stub — see RUST-FX matrix"
        )

    def to_abstract(self, phenotype: object) -> AbstractGenome:
        raise NotImplementedError(
            "CythonSubstrateAdapter is a v0.I future stub — see RUST-FX matrix"
        )

    def can_handle(self, intended: Substrate) -> bool:
        return intended == Substrate.CYTHON


@dataclass
class NeuromorphicSubstrateAdapter:
    """Loihi 2 / SpiNNaker chip placeholder stub (v0.I 長期 R&D anchor).

    [[project_llmesh_neuro_long_term]] の neuromorphic 連動 anchor. skeleton
    では NotImplementedError. 将来 Intel NxSDK / SpiNNaker Python API 経由で
    spike train ↔ AbstractGenome 変換を実装.
    """

    substrate: Substrate = field(default=Substrate.NEUROMORPHIC)

    def from_abstract(self, g: AbstractGenome) -> object:
        raise NotImplementedError(
            "NeuromorphicSubstrateAdapter is a v0.I long-term R&D anchor — "
            "see project_llmesh_neuro_long_term"
        )

    def to_abstract(self, phenotype: object) -> AbstractGenome:
        raise NotImplementedError(
            "NeuromorphicSubstrateAdapter is a v0.I long-term R&D anchor — "
            "see project_llmesh_neuro_long_term"
        )

    def can_handle(self, intended: Substrate) -> bool:
        return intended == Substrate.NEUROMORPHIC


@dataclass
class BciSubstrateAdapter:
    """神経信号 → AbstractGenome placeholder stub (v0.I 長期 R&D anchor).

    [[project_llmesh_neuro_long_term]] の BCI 連動 anchor. skeleton では
    NotImplementedError. 将来 OpenBCI / Emotiv / 侵襲型 BCI 経由で
    neural signal ↔ AbstractGenome 変換を実装.
    """

    substrate: Substrate = field(default=Substrate.BCI)

    def from_abstract(self, g: AbstractGenome) -> object:
        raise NotImplementedError(
            "BciSubstrateAdapter is a v0.I long-term R&D anchor — "
            "see project_llmesh_neuro_long_term"
        )

    def to_abstract(self, phenotype: object) -> AbstractGenome:
        raise NotImplementedError(
            "BciSubstrateAdapter is a v0.I long-term R&D anchor — "
            "see project_llmesh_neuro_long_term"
        )

    def can_handle(self, intended: Substrate) -> bool:
        return intended == Substrate.BCI


@dataclass
class TypescriptSubstrateAdapter:
    """TypeScript / web SDK individual placeholder stub (v0.I 将来).

    SDK / web 側 individual を扱う想定. skeleton では NotImplementedError.
    """

    substrate: Substrate = field(default=Substrate.TYPESCRIPT)

    def from_abstract(self, g: AbstractGenome) -> object:
        raise NotImplementedError(
            "TypescriptSubstrateAdapter is a v0.I future stub — see SDK roadmap"
        )

    def to_abstract(self, phenotype: object) -> AbstractGenome:
        raise NotImplementedError(
            "TypescriptSubstrateAdapter is a v0.I future stub — see SDK roadmap"
        )

    def can_handle(self, intended: Substrate) -> bool:
        return intended == Substrate.TYPESCRIPT


__all__ = [
    "DEFAULT_INTENT_DIM",
    "AbstractGenome",
    "BciSubstrateAdapter",
    "CythonSubstrateAdapter",
    "NeuromorphicSubstrateAdapter",
    "PythonSubstrateAdapter",
    "RustSubstrateAdapter",
    "Substrate",
    "SubstrateAdapter",
    "TypescriptSubstrateAdapter",
]
