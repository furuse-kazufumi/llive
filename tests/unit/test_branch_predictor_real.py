# SPDX-License-Identifier: Apache-2.0
"""Real-sequence hit_rate measurement (SPEC-MESH-01) — unit tests.

Cover the measurement over a real stream (markov beats frequency on first-order
structure), the honest insufficient-data guard (the heart of this module), and
reading straight from a ChangeOpSequenceLog JSONL ledger.
"""

from __future__ import annotations

from llive.evolution.branch_predictor_real import (
    MIN_PREDICTIONS,
    format_markdown,
    measure_log,
    measure_stream,
)
from llive.evolution.change_op_log import ChangeOpSequenceLog


def test_measure_stream_markov_beats_frequency_on_structure() -> None:
    # A perfectly alternating real-ish stream long enough to clear the guard.
    stream = ["insert_subblock", "remove_subblock"] * (MIN_PREDICTIONS)
    report = measure_stream(stream)
    assert not report.insufficient_data
    k1 = next(r for r in report.rows if r.k == 1)
    assert k1.markov_hit_rate > k1.frequency_hit_rate
    assert k1.uplift > 0.0


def test_insufficient_data_below_threshold() -> None:
    report = measure_stream(["insert_subblock", "remove_subblock"])
    assert report.n_steps == 2
    assert report.insufficient_data
    rendered = format_markdown(report)
    assert "実測データ不足" in rendered
    # The guard must NOT leak a fabricated hit_rate number into the output.
    assert "markov" not in rendered


def test_format_markdown_renders_table_when_sufficient() -> None:
    stream = ["insert_subblock", "remove_subblock"] * MIN_PREDICTIONS
    rendered = format_markdown(measure_stream(stream))
    assert "| k | frequency | markov-1 | uplift |" in rendered
    assert "実測 scored steps" in rendered


def test_measure_log_reads_action_stream(tmp_path) -> None:
    log = ChangeOpSequenceLog(tmp_path / "ops.jsonl")
    # Accumulate enough cyclic bursts to exceed MIN_PREDICTIONS scored steps.
    for _ in range(MIN_PREDICTIONS):
        log.record_actions(["insert_subblock", "remove_subblock"], source="unit")
    report = measure_log(log.path)
    assert report.n_steps == 2 * MIN_PREDICTIONS
    assert not report.insufficient_data


def test_measure_log_empty_is_insufficient(tmp_path) -> None:
    report = measure_log(tmp_path / "missing.jsonl")
    assert report.n_steps == 0
    assert report.insufficient_data
