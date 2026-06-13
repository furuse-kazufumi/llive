# SPDX-License-Identifier: Apache-2.0
"""Real-sequence hit_rate measurement for the branch predictor (SPEC-MESH-01).

:mod:`llive.evolution.branch_predictor_bench` measures ``hit_rate`` on **synthetic**
streams. This module measures it on the **real** ChangeOp action stream persisted
by :class:`llive.evolution.change_op_log.ChangeOpSequenceLog` — the path that
overwrites the synthetic figures with measured ones once operational runs
accumulate.

HONEST DISCLOSURE ([[feedback_benchmark_honest_disclosure]]): a real measurement
is only meaningful with enough data. Below :data:`MIN_PREDICTIONS` scored steps the
report is flagged :attr:`RealHitRateReport.insufficient_data` and the rendered
output refuses to quote a number — the synthetic ceiling still stands. A
``hit_rate`` computed over a handful of steps is noise, and reporting it as the
production figure would be exactly the "変に高速 (= 良い) 結果" trap the rule warns
against. The frequency baseline is reported beside the markov figure on every row
so any context win is provable, not assumed.

    py -3.11 -m llive.evolution.branch_predictor_real <log.jsonl>
"""
from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .branch_predictor import FrequencyPredictor, MarkovPredictor, evaluate_hit_rate
from .change_op_log import ChangeOpSequenceLog

# Below this many scored steps a hit_rate is statistical noise, not a measurement.
MIN_PREDICTIONS: int = 30
KS: tuple[int, ...] = (1, 2)


@dataclass(frozen=True)
class RealHitRateRow:
    """One k-row: baseline vs context model on the real stream."""

    k: int
    frequency_hit_rate: float
    markov_hit_rate: float

    @property
    def uplift(self) -> float:
        """markov − frequency. Positive only when real context structure helps."""
        return self.markov_hit_rate - self.frequency_hit_rate


@dataclass(frozen=True)
class RealHitRateReport:
    """Outcome of a real-stream sweep, with the honesty guard built in."""

    n_steps: int
    rows: tuple[RealHitRateRow, ...]

    @property
    def insufficient_data(self) -> bool:
        """True when too few steps were scored to quote a hit_rate honestly."""
        return self.n_steps < MIN_PREDICTIONS


def measure_stream(stream: Sequence[str], ks: Sequence[int] = KS) -> RealHitRateReport:
    """Measure frequency vs markov-1 ``hit_rate`` over a real action stream."""
    rows: list[RealHitRateRow] = []
    for k in ks:
        freq = evaluate_hit_rate(FrequencyPredictor(), stream, k)
        markov = evaluate_hit_rate(MarkovPredictor(), stream, k)
        rows.append(
            RealHitRateRow(
                k=k,
                frequency_hit_rate=freq.hit_rate,
                markov_hit_rate=markov.hit_rate,
            )
        )
    return RealHitRateReport(n_steps=len(stream), rows=tuple(rows))


def measure_log(
    path: Path | str, *, applied_only: bool = True, ks: Sequence[int] = KS
) -> RealHitRateReport:
    """Measure ``hit_rate`` over the action stream persisted in a JSONL log."""
    stream = ChangeOpSequenceLog(path).action_stream(applied_only=applied_only)
    return measure_stream(stream, ks)


def format_markdown(report: RealHitRateReport) -> str:
    """Render a report — refusing to quote numbers when data is insufficient."""
    if report.insufficient_data:
        return (
            f"実測データ不足: scored steps = {report.n_steps} < {MIN_PREDICTIONS}。\n"
            "合成系列の上限を実測で上書きできない。稼働進化ループ (self-reflection 等) を\n"
            "ChangeOpSequenceLog 付きで回し、ログを蓄積してから再測定すること。"
        )
    lines = [
        f"実測 scored steps = {report.n_steps}",
        "",
        "| k | frequency | markov-1 | uplift |",
        "|---|---|---|---|",
    ]
    for r in report.rows:
        lines.append(
            f"| {r.k} | {r.frequency_hit_rate:.3f} | {r.markov_hit_rate:.3f} | {r.uplift:+.3f} |"
        )
    return "\n".join(lines)


def _ensure_utf8_stdout() -> None:
    """Windows cp932 console で em-dash / 日本語を出力するための UTF-8 reconfigure."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


def main(argv: Sequence[str] | None = None) -> int:
    _ensure_utf8_stdout()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: py -3.11 -m llive.evolution.branch_predictor_real <log.jsonl>")
        return 2
    report = measure_log(args[0])
    print("# Branch predictor hit_rate — 実 ChangeOp 系列 (SPEC-MESH-01)\n")
    print("> hit_rate は ROI ではない。baseline=frequency。実測データ不足時は数値を出さない。\n")
    print(format_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
