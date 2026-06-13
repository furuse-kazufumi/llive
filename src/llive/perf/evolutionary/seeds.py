# SPDX-License-Identifier: Apache-2.0
"""Per-individual sub-seed 派生 (llive v0.B Phase 3.5).

並列 fitness 評価で各個体に **decode 可能な deterministic な sub-seed** を
渡すための utility. Population.seed (世代 seed) と Individual.individual_id
から SHA-256 で安全に派生する.

なぜ必要か:
* `MultiprocessingScheduler` で各 worker は別 process, **Python random は
  共有しない**. 各個体に明示的に seed を渡さないと, fitness 関数内の
  non-determinism (numpy random / Mersenne twister) が再現できない.
* per-individual seed が world-generation seed と無関係だと, 「同じ
  generation seed で同じ集団を再現」が破綻する.

設計:
* `derive_sub_seed(parent_seed, individual_id) -> int` —
  SHA-256(parent_seed.bytes || individual_id.utf8) を 32-bit int に
  truncate. 衝突確率は 2^-32, GA の世代数 (~10^3) で問題なし.
* fitness 関数は **(genome) -> FitnessReport** signature を踏襲しつつ,
  ``FitnessFnSeeded = Callable[[Genome, int], FitnessReport]`` の seeded 版も
  サポート. scheduler が seed を持つかどうかは inspect で自動判定.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Callable

from llive.perf.evolutionary.individual import FitnessReport, Individual

# -- public API -------------------------------------------------------------


def derive_sub_seed(parent_seed: int, individual_id: str) -> int:
    """Deterministic に 32-bit sub-seed を派生.

    Parameters
    ----------
    parent_seed : int
        Population.seed (世代 seed).
    individual_id : str
        Individual.individual_id (uuid4 hex, 12 chars 想定).

    Returns
    -------
    int
        [0, 2**31) の 31-bit signed-positive int. numpy.random.default_rng で
        そのまま使える.
    """
    if parent_seed < 0:
        raise ValueError("parent_seed must be >= 0")
    if not individual_id:
        raise ValueError("individual_id must be non-empty")
    payload = parent_seed.to_bytes(8, byteorder="big", signed=False) + individual_id.encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    # SHA-256 の先頭 4 bytes を big-endian int に. 31-bit に mask して安全.
    value = int.from_bytes(digest[:4], byteorder="big", signed=False)
    return value & 0x7FFFFFFF


def fitness_accepts_seed(fitness_fn: Callable) -> bool:
    """fitness_fn が 2 引数 (genome, seed) shape を受け入れるか調べる.

    inspect.signature で param 数を見て判定. ``(genome) -> FitnessReport`` の
    1 引数 shape との互換性を保つ.
    """
    try:
        sig = inspect.signature(fitness_fn)
    except (TypeError, ValueError):
        return False
    # *args / **kwargs を除いた positional parameter count
    positional_count = 0
    for _name, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            positional_count += 1
        elif param.kind == inspect.Parameter.VAR_POSITIONAL:
            return True  # *args ありなら受け入れる
    return positional_count >= 2


def call_fitness_with_seed(
    fitness_fn: Callable,
    individual: Individual,
    parent_seed: int,
) -> FitnessReport:
    """fitness_fn の shape を inspect して seed を渡すか判定.

    Returns the FitnessReport. populationの再現性を保ったまま, **既存の
    (genome,) shape fitness を壊さない**.
    """
    sub_seed = derive_sub_seed(parent_seed, individual.individual_id)
    if fitness_accepts_seed(fitness_fn):
        return fitness_fn(individual.genome, sub_seed)
    return fitness_fn(individual.genome)


__all__ = [
    "call_fitness_with_seed",
    "derive_sub_seed",
    "fitness_accepts_seed",
]
