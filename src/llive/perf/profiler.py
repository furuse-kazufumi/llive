# SPDX-License-Identifier: Apache-2.0
"""APO Profiler — metric 収集 (副作用ゼロ).

ResidentRunner / FullSenseLoop の latency / count / gauge を rolling
window で観測する。spec §A°3 self-correction の measurement infrastructure。

使い方::

    p = Profiler(window=200)
    p.record("loop.tick.ms", 12.4)
    p.incr("triz.hits")
    p.set_gauge("phase", 1)  # AWAKE=0 / REST=1 / DREAM=2

    snap = p.snapshot()
    snap["loop.tick.ms"]["p50"]  # 中央値
    snap["triz.hits"]["count"]   # 累計
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class Sample:
    """latency / value sample 1 件."""

    name: str
    value: float
    at: float = field(default_factory=time.monotonic)


@dataclass
class Profiler:
    """rolling-window metric collector. thread-safe ではない (ResidentRunner は単一 loop)."""

    window: int = 200
    _samples: dict[str, deque] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)
    _gauges: dict[str, float] = field(default_factory=dict)

    def record(self, name: str, value: float) -> None:
        """latency / score 等の連続値を rolling buffer に追加."""
        buf = self._samples.setdefault(name, deque(maxlen=self.window))
        buf.append(float(value))

    def incr(self, name: str, by: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + int(by)

    def set_gauge(self, name: str, value: float) -> None:
        self._gauges[name] = float(value)

    def snapshot(self) -> dict[str, dict[str, float]]:
        """全 metric の集計を返す.

        record: count / mean / p50 / p95 / max
        counter: count
        gauge: value
        """
        out: dict[str, dict[str, float]] = {}
        for name, buf in self._samples.items():
            xs = sorted(buf)
            n = len(xs)
            if n == 0:
                continue
            mean = sum(xs) / n
            p50 = xs[n // 2]
            p95 = xs[min(n - 1, math.ceil(n * 0.95) - 1)]
            out[name] = {
                "count": n,
                "mean": mean,
                "p50": p50,
                "p95": p95,
                "max": xs[-1],
            }
        for name, c in self._counters.items():
            out[name] = {"count": c}
        for name, g in self._gauges.items():
            out[name] = {"value": g}
        return out

    def reset(self) -> None:
        self._samples.clear()
        self._counters.clear()
        self._gauges.clear()


def diagnose_latency(
    profiler: Profiler,
    metric: str = "loop.tick.ms",
    *,
    budget_ms: float = 200.0,
) -> dict[str, object]:
    """spec §APO の degraded diagnostics: human-speech budget 違反検査.

    Returns:
        ``{"healthy": bool, "p95_ms": float, "budget_ms": float, "verdict": str}``
    """
    snap = profiler.snapshot().get(metric)
    if snap is None or "p95" not in snap:
        return {"healthy": True, "verdict": "no_data", "budget_ms": budget_ms}
    p95 = snap["p95"]
    return {
        "healthy": p95 <= budget_ms,
        "p95_ms": p95,
        "budget_ms": budget_ms,
        "verdict": "ok" if p95 <= budget_ms else "exceeds_human_speech_budget",
    }


__all__ = ["Profiler", "Sample", "diagnose_latency"]
