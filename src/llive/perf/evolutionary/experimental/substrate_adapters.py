# SPDX-License-Identifier: Apache-2.0
"""Cross-Substrate Genome — 具体 SubstrateAdapter 実装 (llive v0.I EV-38 案 E §7.2).

:mod:`llive.perf.evolutionary.cross_substrate` で定義された
:class:`SubstrateAdapter` Protocol の具体実装. Python / Rust は skeleton stub,
Cython / Neuromorphic / BCI / TypeScript は ``NotImplementedError`` raising
placeholder.

Substrates (v0.I §7.2):

* :class:`PythonSubstrateAdapter` — llive Python individual (現状の Genome3D-like
  dict 表現)
* :class:`RustSubstrateAdapter` — Rust individual (RUST-FX hot path; FFI bridge
  は将来 RUST-15 以降)
* :class:`CythonSubstrateAdapter` — Cython 実装 (将来 / RUST-FX matrix 評価)
* :class:`NeuromorphicSubstrateAdapter` — Loihi 2 / SpiNNaker chip (長期 R&D
  anchor / [[project_llmesh_neuro_long_term]] 連動)
* :class:`BciSubstrateAdapter` — 神経信号 → AbstractGenome (長期 R&D anchor)
* :class:`TypescriptSubstrateAdapter` — web / SDK side individual (将来)

References:

- llive ``docs/requirements_v0.I_meta_evolution_and_cross_substrate.md`` §7.
- llive [[project_llmesh_neuro_long_term]] — neuromorphic / BCI anchor.
- Davies, M. et al. (2018). *Loihi: A Neuromorphic Manycore Processor.* IEEE Micro.
- Furber, S. B. et al. (2014). *The SpiNNaker Project.* Proc. IEEE.

Status (2026-05-22 着地): skeleton. Python / Rust は dict round-trip stub.
他は NotImplementedError. 実 FFI bridge / BCI 連動 / neuromorphic dispatch は
将来 (EV-39 以降).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from llive.perf.evolutionary.cross_substrate import (
    AbstractGenome,
    Substrate,
)

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
    "BciSubstrateAdapter",
    "CythonSubstrateAdapter",
    "NeuromorphicSubstrateAdapter",
    "PythonSubstrateAdapter",
    "RustSubstrateAdapter",
    "TypescriptSubstrateAdapter",
]
