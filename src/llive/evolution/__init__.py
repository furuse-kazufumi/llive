# SPDX-License-Identifier: Apache-2.0
"""L6: Evolution Manager (ChangeOp + BenchHarness + BranchPredictor)."""

from llive.evolution.antifragile import (
    DEFAULT_CONFLICT_PAIRS,
    AntifragileConfig,
    AntifragileController,
    AntifragileEpisode,
    ConflictPair,
    PanicState,
)
from llive.evolution.bench import BenchHarness, BenchResult
from llive.evolution.branch_predictor import (
    CHANGE_OP_ACTIONS,
    BranchPredictor,
    FrequencyPredictor,
    HitRateResult,
    MarkovPredictor,
    evaluate_hit_rate,
    predicted_manifest_branches,
    to_manifest_branch,
)
from llive.evolution.change_op import (
    ChangeOp,
    InsertSubblock,
    RemoveSubblock,
    ReorderSubblocks,
    ReplaceSubblock,
    apply_diff,
    build_change_op,
)

__all__ = [
    "CHANGE_OP_ACTIONS",
    "DEFAULT_CONFLICT_PAIRS",
    "AntifragileConfig",
    "AntifragileController",
    "AntifragileEpisode",
    "BenchHarness",
    "BenchResult",
    "BranchPredictor",
    "ChangeOp",
    "ConflictPair",
    "FrequencyPredictor",
    "HitRateResult",
    "InsertSubblock",
    "MarkovPredictor",
    "PanicState",
    "RemoveSubblock",
    "ReorderSubblocks",
    "ReplaceSubblock",
    "apply_diff",
    "build_change_op",
    "evaluate_hit_rate",
    "predicted_manifest_branches",
    "to_manifest_branch",
]
