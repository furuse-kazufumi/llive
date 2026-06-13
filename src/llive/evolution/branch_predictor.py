# SPDX-License-Identifier: Apache-2.0
"""Branch predictor for Speculative Mesh Execution (SPEC-MESH-01, Phase 1).

The Speculative Mesh (llmesh ``speculative/``) ships *predicted* future branches
to idle peers so the expensive work is already done when the origin needs it. The
whole ROI hinges on **prediction accuracy** (``hit_rate``): a low hit_rate wastes
peer compute (energy) without buying latency. So before wiring any transport, the
requirement (``requirements_speculative_mesh.md`` §5) is to *measure the
predictor's hit_rate in isolation*.

This module is that minimal predictor. It operates on **ChangeOp action labels**
(the four Phase-1 actions from :mod:`llive.evolution.change_op`) rather than full
``ChangeOp`` objects, so it stays stdlib-only and carries no heavy schema import —
which is all the hit_rate measurement needs. The predicted actions are emitted as
opaque ``branch`` dicts that drop straight into
``llmesh.speculative.manifest.SpeculativeManifest.new(branch=...)``.

Two predictors, deliberately:

- :class:`FrequencyPredictor` — the **baseline**. Predicts the globally most
  frequent actions, ignoring context. Per the honest-disclosure rule
  ([[feedback_benchmark_honest_disclosure]]) a baseline is measured first so any
  context-model win is provable, not assumed.
- :class:`MarkovPredictor` — an order-1 model: predicts from the transition
  distribution of the *last observed* action. Only beats the baseline when the
  action stream actually carries first-order structure.

Both are *fail-safe*: with no usable history they fall back to a deterministic
default vocabulary, so :func:`evaluate_hit_rate` never crashes on a cold start.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# The four Phase-1 ChangeOp actions (mirrors llive.evolution.change_op). Used as
# the default cold-start vocabulary so a predictor can emit candidates before it
# has observed anything. Kept as plain strings on purpose (no schema import).
CHANGE_OP_ACTIONS: tuple[str, ...] = (
    "insert_subblock",
    "remove_subblock",
    "replace_subblock",
    "reorder_subblocks",
)


# ---------------------------------------------------------------------------
# Predictor interface
# ---------------------------------------------------------------------------


class BranchPredictor(ABC):
    """Predicts the next likely action(s) from the actions observed so far.

    Usage is online: call :meth:`predict_top_k` to read the current prediction,
    then :meth:`observe` once the real next action is known. The two never share
    state within a step, so a prediction is always made *before* its outcome is
    revealed (no look-ahead leakage into the hit_rate measurement).
    """

    @abstractmethod
    def observe(self, action: str) -> None:
        """Record that ``action`` actually occurred (advances the history)."""

    @abstractmethod
    def predict_top_k(self, k: int) -> list[str]:
        """Return up to ``k`` predicted next actions, best-first.

        ``k <= 0`` yields an empty list. The result is deterministic: ties break
        by first-seen order so repeated runs are reproducible.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in measurement reports."""


def _ranked(counts: Counter[str], first_seen: dict[str, int]) -> list[str]:
    """Actions in ``counts`` sorted by descending count, ties by first-seen order."""
    return sorted(counts, key=lambda a: (-counts[a], first_seen.get(a, 1 << 30)))


# ---------------------------------------------------------------------------
# Baseline: global frequency
# ---------------------------------------------------------------------------


class FrequencyPredictor(BranchPredictor):
    """Context-free baseline: predict the most frequent actions seen so far.

    This is the bar a context model must clear. On a structureless (i.i.d.)
    stream it is already optimal, so any uplift from :class:`MarkovPredictor`
    on such a stream would be noise — a useful sanity check.
    """

    def __init__(self, vocab: Sequence[str] = CHANGE_OP_ACTIONS) -> None:
        self._counts: Counter[str] = Counter()
        self._first_seen: dict[str, int] = {}
        self._vocab: tuple[str, ...] = tuple(vocab)

    @property
    def name(self) -> str:
        return "frequency"

    def observe(self, action: str) -> None:
        if action not in self._first_seen:
            self._first_seen[action] = len(self._first_seen)
        self._counts[action] += 1

    def predict_top_k(self, k: int) -> list[str]:
        if k <= 0:
            return []
        if not self._counts:
            return list(self._vocab[:k])
        return _ranked(self._counts, self._first_seen)[:k]


# ---------------------------------------------------------------------------
# Order-1 Markov
# ---------------------------------------------------------------------------


class MarkovPredictor(BranchPredictor):
    """Order-1 model: predict from the transition counts of the last action.

    For the current context (last observed action) it ranks successors by how
    often each followed it. When that context is unseen or has fewer than ``k``
    distinct successors, it pads with the global frequency ranking, then with the
    default vocabulary — so it degrades gracefully to the baseline rather than
    returning nothing.
    """

    def __init__(self, vocab: Sequence[str] = CHANGE_OP_ACTIONS) -> None:
        self._trans: dict[str, Counter[str]] = defaultdict(Counter)
        self._global: Counter[str] = Counter()
        self._first_seen: dict[str, int] = {}
        self._prev: str | None = None
        self._vocab: tuple[str, ...] = tuple(vocab)

    @property
    def name(self) -> str:
        return "markov-1"

    def observe(self, action: str) -> None:
        if action not in self._first_seen:
            self._first_seen[action] = len(self._first_seen)
        self._global[action] += 1
        if self._prev is not None:
            self._trans[self._prev][action] += 1
        self._prev = action

    def predict_top_k(self, k: int) -> list[str]:
        if k <= 0:
            return []

        ranked: list[str] = []
        # 1. context-specific successors of the last observed action
        if self._prev is not None and self._trans[self._prev]:
            ranked = _ranked(self._trans[self._prev], self._first_seen)
        # 2. pad with global frequency (covers unseen context / few successors)
        if len(ranked) < k and self._global:
            for action in _ranked(self._global, self._first_seen):
                if action not in ranked:
                    ranked.append(action)
        # 3. pad with the default vocabulary (cold start)
        if len(ranked) < k:
            for action in self._vocab:
                if action not in ranked:
                    ranked.append(action)
        return ranked[:k]


# ---------------------------------------------------------------------------
# Manifest branch emission (the contract llmesh.speculative consumes)
# ---------------------------------------------------------------------------


def to_manifest_branch(action: str, *, target_container: str = "?", **extra: object) -> dict:
    """Wrap a predicted action as an opaque ``branch`` dict for a manifest.

    The shape mirrors a serialized ``ChangeOp`` (``action`` + ``target_container``
    plus any action-specific fields). The mesh coordinator never interprets it; it
    is forwarded to the executing peer verbatim, so extra hints can ride along.
    """
    branch: dict[str, object] = {"action": action, "target_container": target_container}
    branch.update(extra)
    return branch


def predicted_manifest_branches(
    predictor: BranchPredictor, k: int, *, target_container: str = "?"
) -> list[dict]:
    """Top-``k`` predictions as manifest ``branch`` dicts (best-first)."""
    return [
        to_manifest_branch(action, target_container=target_container)
        for action in predictor.predict_top_k(k)
    ]


# ---------------------------------------------------------------------------
# hit_rate measurement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HitRateResult:
    """Outcome of an online next-step prediction sweep over one action sequence."""

    predictor: str
    k: int
    n_predictions: int
    hits: int

    @property
    def hit_rate(self) -> float:
        """Fraction of steps whose actual next action was in the top-k prediction."""
        return self.hits / self.n_predictions if self.n_predictions else 0.0


def evaluate_hit_rate(predictor: BranchPredictor, sequence: Iterable[str], k: int) -> HitRateResult:
    """Measure top-``k`` next-step ``hit_rate`` of ``predictor`` over ``sequence``.

    Every step counts (including the cold-start step, scored against the default
    vocabulary) — this is the honest figure: an origin really would emit a
    speculative manifest from step one. At each step the prediction is read
    *before* the actual action is observed, so there is no leakage.

    Raises:
        ValueError: if ``k <= 0`` (a non-positive k can never score a hit).
    """
    if k <= 0:
        raise ValueError("k must be positive")

    hits = 0
    n = 0
    for actual in sequence:
        top_k = predictor.predict_top_k(k)
        n += 1
        if actual in top_k:
            hits += 1
        predictor.observe(actual)
    return HitRateResult(predictor=predictor.name, k=k, n_predictions=n, hits=hits)


__all__ = [
    "CHANGE_OP_ACTIONS",
    "BranchPredictor",
    "FrequencyPredictor",
    "MarkovPredictor",
    "HitRateResult",
    "evaluate_hit_rate",
    "to_manifest_branch",
    "predicted_manifest_branches",
]
