# SPDX-License-Identifier: Apache-2.0
"""APO (Autonomous Performance Optimization) — § A°3 self-correction の基盤.

副作用ゼロの metric 収集層。``Profiler`` で latency / counter / gauge を観測し、
``Diagnostics`` で性能劣化を検出する。``Optimizer`` (Level 3 で実装) と
``Verifier`` (Level 3 で実装、§E3 formal pre-check) はこの基盤に乗る。
"""

from llive.perf.profiler import Profiler, Sample

__all__ = ["Profiler", "Sample"]
