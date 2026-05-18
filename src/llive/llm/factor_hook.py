# SPDX-License-Identifier: Apache-2.0
"""Thought-factor → Δ bridge hook protocol — non-transformer ROADMAP case C.

The strongest paper-grade differentiator for FullSense / llive: tie the
internal cognitive state (llive's 10 thought factors) to the *dynamic
discretisation step Δ* of a Selective SSM (Mamba). Concretely, when llive
detects high uncertainty or low integration confidence, the SSM should
make smaller, more deliberate steps; when factors signal consolidation,
larger steps integrate more context per token.

This module is the **interface side** only. The actual Mamba SSM kernel
that consumes the hook lives in :class:`MambaBackend` transport
``mamba_ssm`` (deferred to Phase 5). The hook surface is exposed now so:

1. Researchers can design downstream pipelines against the protocol.
2. Tests can assert that backends without SSM support gracefully ignore
   any hook (the NoopFactorHook is always safe).
3. The 6-stage loop can pass factor snapshots through every stage without
   yet caring whether the backend uses them.

References:
* memory `project_llive_cog_fx_factors` — the 10 factors definition.
* memory `project_llive_oka` — OKA-FX / MathVerifier integration plan.
* docs/non-transformer/ROADMAP.md case C — full design rationale.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

# Canonical names of the 10 llive thought factors (lower-case, snake-case).
# Source: project_llive_cog_fx_factors memory + COG-01/02/03/04 spec.
FACTOR_NAMES: tuple[str, ...] = (
    "structurize",      # 構造化
    "reconstruct",      # 再構成
    "closed_loop",      # 閉ループ
    "self_extension",   # 自己拡張
    "uncertainty",      # 不確実性
    "exploration",      # 探索
    "integrate",        # 整合
    "provenance",       # 来歴
    "perspective",      # 多視点
    "reality_contact",  # 現実接続
)


@dataclass(frozen=True)
class FactorSnapshot:
    """Point-in-time values for each of the 10 factors.

    Values are dimensionless in [0, 1] by convention (0 = absent, 1 = saturated).
    Unknown / missing factors default to 0.5 (neutral) so partial updates
    from llive's 6 stages don't bias the bridge in either direction.
    """

    values: Mapping[str, float] = field(default_factory=dict)
    stage: str | None = None  # which 6-stage step produced this snapshot

    def get(self, name: str, default: float = 0.5) -> float:
        v = self.values.get(name, default)
        # Clamp to [0, 1] to keep downstream maths well-behaved.
        return max(0.0, min(1.0, float(v)))

    def vector(self) -> tuple[float, ...]:
        """Return values in canonical FACTOR_NAMES order."""
        return tuple(self.get(n) for n in FACTOR_NAMES)


@runtime_checkable
class ThoughtFactorDeltaHook(Protocol):
    """Maps a :class:`FactorSnapshot` to an SSM discretisation step Δ.

    Implementations live alongside the SSM transport that consumes them.
    For backends without SSM support (Transformer / OpenAI / etc.) the
    snapshot is simply ignored; passing a hook is always safe.

    Return value is a positive float representing the multiplicative
    adjustment to the *baseline* Δ. ``1.0`` = no change, ``<1.0`` =
    smaller (more deliberate) step, ``>1.0`` = larger step.
    """

    def delta_for(self, snapshot: FactorSnapshot) -> float: ...


class NoopFactorHook:
    """Default hook — always returns 1.0. Safe for backends that ignore it."""

    name = "noop"

    def delta_for(self, snapshot: FactorSnapshot) -> float:  # noqa: ARG002
        return 1.0


class HeuristicFactorHook:
    """Reference hook — Phase 5 demo / sanity check.

    Behaviour (intentionally simple, not the final paper formula):

    * High ``uncertainty`` → smaller Δ (decelerate, integrate more carefully).
    * High ``integrate`` + ``structurize`` → larger Δ (consolidate aggressively).
    * High ``exploration`` → slightly larger Δ (sample boldly).
    * Default ≈ 1.0 when factors are balanced.

    The exact mapping will be replaced by a learnt function in the Phase 5
    PoC; this class exists so the wiring (loop → snapshot → backend) can be
    tested end-to-end before training data is available.
    """

    name = "heuristic"

    def __init__(self, sensitivity: float = 1.0) -> None:
        self.sensitivity = float(sensitivity)

    def delta_for(self, snapshot: FactorSnapshot) -> float:
        unc = snapshot.get("uncertainty")
        integ = snapshot.get("integrate")
        struct = snapshot.get("structurize")
        explore = snapshot.get("exploration")
        # Raw signal in roughly [-1, 1]
        signal = (integ + struct + 0.5 * explore - 1.5 * unc) / 2.0
        # Map to a multiplicative factor in roughly (1/e, e) via exp
        delta = math.exp(signal * self.sensitivity)
        # Hard clamp so a runaway snapshot can't blow up the SSM step
        return max(0.25, min(4.0, delta))


# Module-level singleton — Noop by default, swap in production via setter.
_DEFAULT_HOOK: ThoughtFactorDeltaHook = NoopFactorHook()


def get_default_hook() -> ThoughtFactorDeltaHook:
    return _DEFAULT_HOOK


def set_default_hook(hook: ThoughtFactorDeltaHook) -> None:
    """Install a process-wide default hook (e.g. HeuristicFactorHook())."""
    global _DEFAULT_HOOK
    _DEFAULT_HOOK = hook


def reset_default_hook() -> None:
    """For tests: restore the Noop default."""
    global _DEFAULT_HOOK
    _DEFAULT_HOOK = NoopFactorHook()
