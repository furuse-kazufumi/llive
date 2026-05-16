# SPDX-License-Identifier: Apache-2.0
"""APO (Autonomous Performance Optimization) — § A°3 self-correction の基盤.

副作用ゼロの metric 収集層。``Profiler`` で latency / counter / gauge を観測し、
``Diagnostics`` で性能劣化を検出する。``Optimizer`` (Level 3 で実装) と
``Verifier`` (Level 3 で実装、§E3 formal pre-check) はこの基盤に乗る。
"""

from llive.perf.diagnostics import (
    Diagnostics,
    Issue,
    RegressionRule,
    Severity,
    Threshold,
)
from llive.perf.governance import (
    Applier,
    ApplyOutcome,
    ApplyResult,
    ApplyStatus,
    apply_with_approval,
)
from llive.perf.optimizer import (
    Modification,
    ModificationBound,
    OptimizationStrategy,
    Optimizer,
    raise_threshold_strategy,
    reduce_load_strategy,
)
from llive.perf.profiler import Profiler, Sample
from llive.perf.registry import ThresholdRegistry
from llive.perf.verifier import (
    InvariantCheck,
    RejectedModification,
    VerificationResult,
    Verifier,
    bounded_step,
    default_invariants,
    load_reduction_only,
    non_negative,
    relaxation_only,
)

__all__ = [
    "Applier",
    "ApplyOutcome",
    "ApplyResult",
    "ApplyStatus",
    "Diagnostics",
    "InvariantCheck",
    "Issue",
    "Modification",
    "ModificationBound",
    "OptimizationStrategy",
    "Optimizer",
    "Profiler",
    "RegressionRule",
    "RejectedModification",
    "Sample",
    "Severity",
    "Threshold",
    "ThresholdRegistry",
    "VerificationResult",
    "Verifier",
    "apply_with_approval",
    "bounded_step",
    "default_invariants",
    "load_reduction_only",
    "non_negative",
    "raise_threshold_strategy",
    "reduce_load_strategy",
    "relaxation_only",
]
