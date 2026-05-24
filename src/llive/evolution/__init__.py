# SPDX-License-Identifier: Apache-2.0
"""L6: Evolution Manager (ChangeOp + BenchHarness)."""

from llive.evolution.antifragile import (
    DEFAULT_CONFLICT_PAIRS,
    AntifragileConfig,
    AntifragileController,
    AntifragileEpisode,
    ConflictPair,
    PanicState,
)
from llive.evolution.bench import BenchHarness, BenchResult
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
    "DEFAULT_CONFLICT_PAIRS",
    "AntifragileConfig",
    "AntifragileController",
    "AntifragileEpisode",
    "BenchHarness",
    "BenchResult",
    "ChangeOp",
    "ConflictPair",
    "InsertSubblock",
    "PanicState",
    "RemoveSubblock",
    "ReorderSubblocks",
    "ReplaceSubblock",
    "apply_diff",
    "build_change_op",
]
