# SPDX-License-Identifier: Apache-2.0
"""APO applier reference implementation (C-11).

The C-7〜C-10 lane is intentionally generic: it stops at producing an
*approved* ``Modification`` and hands off to a caller-supplied
``Applier`` for the actual mutation. ``ThresholdRegistry`` is a small,
self-contained reference Applier that mutates Diagnostics thresholds in
place — the most common APO action ("relax the warning level that just
fired").

Layout::

    profiler.threshold.<metric>.<stat>   →  max_value (float)

The registry exposes:

* ``register(threshold)`` — install a Threshold object whose
  ``max_value`` can later be mutated.
* ``apply(mod)`` — the Applier callable. Updates the in-place
  threshold whose target matches ``mod.target``.
* ``snapshot()`` — current ``{target: max_value}`` view, for audit.

The registry can be paired with ``Diagnostics.thresholds`` directly:
``diagnostics.thresholds = tuple(registry.live_thresholds)``. After
each apply round the diagnostics's threshold tuple is regenerated, so
the next ``check()`` sees the new value.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass, replace

from llive.perf.diagnostics import Threshold
from llive.perf.optimizer import Modification


@dataclass
class ThresholdRegistry:
    """Mutable backing store for ``Diagnostics`` thresholds.

    Thresholds are stored keyed by their *canonical target* —
    ``f"profiler.threshold.{metric}.{stat}"`` — which matches the
    target string produced by ``raise_threshold_strategy``.
    """

    _by_target: dict[str, Threshold]
    _lock: threading.RLock

    def __init__(self, initial: Iterable[Threshold] = ()) -> None:
        self._by_target = {}
        self._lock = threading.RLock()
        for t in initial:
            self.register(t)

    @staticmethod
    def canonical_target(metric: str, stat: str) -> str:
        return f"profiler.threshold.{metric}.{stat}"

    def register(self, threshold: Threshold) -> None:
        key = self.canonical_target(threshold.metric, threshold.stat)
        with self._lock:
            self._by_target[key] = threshold

    def get(self, target: str) -> Threshold | None:
        with self._lock:
            return self._by_target.get(target)

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {k: v.max_value for k, v in self._by_target.items()}

    @property
    def live_thresholds(self) -> tuple[Threshold, ...]:
        """Latest tuple suitable for ``Diagnostics(thresholds=...)``."""
        with self._lock:
            return tuple(self._by_target.values())

    def apply(self, mod: Modification) -> None:
        """Applier for ``apply_with_approval``.

        Looks up the target, replaces the ``max_value`` with the
        modification's ``proposed``. Raises ``KeyError`` if the target
        is unknown — by design: refusing to mutate state for an
        identifier we never registered keeps blast radius small.
        """
        with self._lock:
            cur = self._by_target.get(mod.target)
            if cur is None:
                raise KeyError(
                    f"ThresholdRegistry has no threshold for target {mod.target!r}"
                )
            self._by_target[mod.target] = replace(cur, max_value=float(mod.proposed))


__all__ = ["ThresholdRegistry"]
