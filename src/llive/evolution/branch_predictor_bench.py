# SPDX-License-Identifier: Apache-2.0
"""hit_rate measurement bench for the branch predictor (SPEC-MESH-01).

Per ``requirements_speculative_mesh.md`` §5, the first step toward the Speculative
Mesh is to *measure the predictor's hit_rate in isolation* — before any transport
is wired, because a low hit_rate wastes peer compute without buying latency.

This bench runs :class:`FrequencyPredictor` (the context-free baseline) against
:class:`MarkovPredictor` (order-1 context) over synthetic action streams of
varying structure, so we can see **whether the context model captures structure
the baseline misses**, and by how much.

HONEST DISCLOSURE (read before quoting any number):

- These are **synthetic** ChangeOp-action streams. The real operational hit_rate
  depends on the actual ChangeOp/Brief stream a running llive emits, which is not
  yet logged. This bench measures *capability* (can an order-1 model beat a
  frequency baseline when structure exists?), not the production hit_rate.
- A hit_rate here is **not** a speedup. The ROI (end-to-end latency) is governed
  by the latency model in ``llmesh.speculative.bench`` and must be re-measured on
  real transport (SPEC-MESH-07). hit_rate is the *input* to that ROI, nothing more.
- The baseline is reported alongside every figure on purpose
  ([[feedback_benchmark_honest_disclosure]]): a Markov win on a structureless
  stream would be noise, so the i.i.d. row is a sanity check that it doesn't.

    py -3.11 -m llive.evolution.branch_predictor_bench
"""
from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from .branch_predictor import (
    CHANGE_OP_ACTIONS,
    FrequencyPredictor,
    MarkovPredictor,
    evaluate_hit_rate,
)

_ACTIONS = list(CHANGE_OP_ACTIONS)


# ---------------------------------------------------------------------------
# Synthetic stream generators
# ---------------------------------------------------------------------------


def gen_iid(n: int, seed: int) -> list[str]:
    """Structureless: each action drawn uniformly at random (the null model)."""
    rng = random.Random(seed)
    return [rng.choice(_ACTIONS) for _ in range(n)]


def gen_skewed(n: int, seed: int, dominant_p: float = 0.7) -> list[str]:
    """Frequency-skewed but context-free: one action dominates, no transitions.

    Rewards the frequency baseline; the Markov model should merely match it.
    """
    rng = random.Random(seed)
    rest = _ACTIONS[1:]
    out: list[str] = []
    for _ in range(n):
        out.append(_ACTIONS[0] if rng.random() < dominant_p else rng.choice(rest))
    return out


def gen_cyclic(n: int) -> list[str]:
    """Deterministic period-4 cycle: pure first-order structure, no noise."""
    return [_ACTIONS[i % len(_ACTIONS)] for i in range(n)]


def gen_markov(n: int, seed: int, dominant_p: float = 0.85) -> list[str]:
    """Noisy order-1 chain: each action usually steps to its cyclic successor.

    With probability ``1 - dominant_p`` it jumps uniformly at random, so the
    structure is real but not perfectly predictable — the realistic middle case.
    """
    rng = random.Random(seed)
    successor = {a: _ACTIONS[(i + 1) % len(_ACTIONS)] for i, a in enumerate(_ACTIONS)}
    current = _ACTIONS[0]
    out = [current]
    for _ in range(n - 1):
        current = successor[current] if rng.random() < dominant_p else rng.choice(_ACTIONS)
        out.append(current)
    return out


# ---------------------------------------------------------------------------
# Bench
# ---------------------------------------------------------------------------

KS: tuple[int, ...] = (1, 2)


@dataclass(frozen=True)
class BenchRow:
    scenario: str
    k: int
    frequency_hit_rate: float
    markov_hit_rate: float

    @property
    def uplift(self) -> float:
        """markov − frequency. Positive only when context helps."""
        return self.markov_hit_rate - self.frequency_hit_rate


def _scenarios(n: int, seed: int) -> dict[str, list[str]]:
    return {
        "iid (no structure)": gen_iid(n, seed),
        "skewed frequency (.70)": gen_skewed(n, seed),
        "markov-1 noisy (.85)": gen_markov(n, seed),
        "cyclic (period 4)": gen_cyclic(n),
    }


def run(*, n: int = 2000, seed: int = 0) -> list[BenchRow]:
    rows: list[BenchRow] = []
    for name, seq in _scenarios(n, seed).items():
        for k in KS:
            freq = evaluate_hit_rate(FrequencyPredictor(), seq, k)
            markov = evaluate_hit_rate(MarkovPredictor(), seq, k)
            rows.append(BenchRow(name, k, freq.hit_rate, markov.hit_rate))
    return rows


def _note(row: BenchRow) -> str:
    if row.uplift > 0.10:
        return "context captures structure"
    if abs(row.uplift) < 0.05:
        return "no structure (sanity: baseline holds)"
    return ""


def format_markdown(rows: list[BenchRow]) -> str:
    lines = [
        "| scenario | k | frequency | markov-1 | uplift | note |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.scenario} | {r.k} | {r.frequency_hit_rate:.3f} | "
            f"{r.markov_hit_rate:.3f} | {r.uplift:+.3f} | {_note(r)} |"
        )
    return "\n".join(lines)


def _ensure_utf8_stdout() -> None:
    """Windows cp932 console で em-dash / 日本語を出力するための UTF-8 reconfigure."""
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


def main() -> None:
    _ensure_utf8_stdout()
    rows = run()
    print("# Branch predictor hit_rate — synthetic streams (SPEC-MESH-01)\n")
    print("> hit_rate は ROI ではない。実運用値は ChangeOp 実ログ待ち。baseline=frequency。\n")
    print(format_markdown(rows))


if __name__ == "__main__":
    main()
