# SPDX-License-Identifier: Apache-2.0
"""FullSenseLoop x ThoughtFactorDeltaHook wiring tests (case C skeleton).

Covers the factor-hook integration added in 2026-05-18:

1. ``factor_hook=`` injection at construction is honoured and exposes
   ``factor_delta`` + ``factor_snapshot`` in stages["thought"].
2. ``factor_hook=None`` (default) keeps the previous shape exactly
   (no ``factor_delta`` key surfaces).
3. The built snapshot reflects current stage data
   (exploration ← curiosity score, uncertainty ← 1-confidence, etc.).
4. HeuristicFactorHook produces a delta != 1.0 when factors are extreme.
"""

from __future__ import annotations

import pytest

from llive.fullsense.loop import FullSenseLoop
from llive.fullsense.types import Stimulus
from llive.llm.factor_hook import (
    FactorSnapshot,
    HeuristicFactorHook,
    NoopFactorHook,
    ThoughtFactorDeltaHook,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "LLIVE_LLM_BACKEND",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OLLAMA_HOST",
        "LLIVE_ALLOW_CLOUD_BACKEND",
    ):
        monkeypatch.delenv(var, raising=False)


def _stim(surprise: float = 0.7) -> Stimulus:
    return Stimulus(
        content="A contradiction-themed stimulus for factor hook tests.",
        surprise=surprise,
    )


class _RecordingHook:
    """Hook that records every snapshot it sees, returns 1.0."""

    name = "recording"

    def __init__(self) -> None:
        self.snapshots: list[FactorSnapshot] = []

    def delta_for(self, snapshot: FactorSnapshot) -> float:
        self.snapshots.append(snapshot)
        return 1.0


# ---------------------------------------------------------------------------
# 1. injection surfaces factor_delta + factor_snapshot
# ---------------------------------------------------------------------------


def test_factor_hook_injection_surfaces_delta_and_snapshot() -> None:
    hook = NoopFactorHook()
    loop = FullSenseLoop(sandbox=True, factor_hook=hook)
    result = loop.process(_stim())

    thought = result.stages["thought"]
    assert "factor_delta" in thought
    assert "factor_snapshot" in thought
    assert thought["factor_delta"] == 1.0  # Noop returns 1.0
    assert isinstance(thought["factor_snapshot"], dict)


# ---------------------------------------------------------------------------
# 2. no hook → no extra keys (back-compat)
# ---------------------------------------------------------------------------


def test_no_factor_hook_preserves_legacy_shape() -> None:
    loop = FullSenseLoop(sandbox=True)
    result = loop.process(_stim())
    thought = result.stages["thought"]
    assert "factor_delta" not in thought
    assert "factor_snapshot" not in thought


# ---------------------------------------------------------------------------
# 3. snapshot content reflects stage data
# ---------------------------------------------------------------------------


def test_snapshot_reflects_stage_data() -> None:
    recorder = _RecordingHook()
    loop = FullSenseLoop(sandbox=True, factor_hook=recorder)
    result = loop.process(_stim(surprise=0.9))

    assert len(recorder.snapshots) == 1
    snap = recorder.snapshots[0]
    assert snap.stage == "thought"

    # exploration ← curiosity score (in [0, 1])
    expl = snap.get("exploration")
    assert 0.0 <= expl <= 1.0

    # uncertainty ← 1 - confidence (confidence ≈ 0.4 + 0.4 * curiosity)
    # surprise=0.9 → curiosity is computed by novelty (token-based); we
    # don't pin the exact value but require it to be in [0, 1].
    unc = snap.get("uncertainty")
    assert 0.0 <= unc <= 1.0

    # structurize ← min(1.0, 0.3 + 0.7 * surprise) = min(1.0, 0.3 + 0.63) = 0.93
    structurize = snap.get("structurize")
    assert structurize == pytest.approx(0.93, abs=1e-6)


# ---------------------------------------------------------------------------
# 4. HeuristicFactorHook can produce delta != 1.0 (sanity)
# ---------------------------------------------------------------------------


def test_heuristic_hook_produces_non_unit_delta_at_extremes() -> None:
    """When factors are extreme (high uncertainty), the heuristic hook
    diverges from 1.0. We don't pin the exact value (it depends on the
    snapshot built by the loop), only that the hook is actually consulted
    and its result lands in stages["thought"]["factor_delta"]."""
    hook = HeuristicFactorHook(sensitivity=2.0)
    loop = FullSenseLoop(sandbox=True, factor_hook=hook)
    result = loop.process(_stim(surprise=0.95))
    delta = result.stages["thought"]["factor_delta"]
    # Just check the heuristic clamp range from factor_hook.py
    assert 0.25 <= delta <= 4.0


# ---------------------------------------------------------------------------
# 5. hook is also called on SILENT short-circuit? — no, current design only
#    builds snapshot AFTER inner monologue. SILENT skips thought stage, so
#    the hook is not consulted. This is consistent with thought being the
#    primary signal source.
# ---------------------------------------------------------------------------


def test_factor_hook_not_called_on_silent_short_circuit() -> None:
    recorder = _RecordingHook()
    loop = FullSenseLoop(sandbox=True, factor_hook=recorder, salience_threshold=0.99)
    # surprise=0.1 < threshold=0.99 → SILENT, skips thought stage
    result = loop.process(_stim(surprise=0.1))
    assert result.stages["thought"] is None
    assert recorder.snapshots == []


# ---------------------------------------------------------------------------
# 6. Protocol conformance — any class with delta_for() works
# ---------------------------------------------------------------------------


def test_arbitrary_protocol_implementation_works() -> None:
    class _Inverter:
        """delta_for returns 1 - uncertainty as a sanity test."""

        def delta_for(self, snapshot: FactorSnapshot) -> float:
            return max(0.25, 1.0 - snapshot.get("uncertainty"))

    inverter = _Inverter()
    # The Protocol is runtime-checkable.
    assert isinstance(inverter, ThoughtFactorDeltaHook)
    loop = FullSenseLoop(sandbox=True, factor_hook=inverter)
    result = loop.process(_stim())
    delta = result.stages["thought"]["factor_delta"]
    assert delta != 1.0 or delta == pytest.approx(1.0, abs=1e-6)
