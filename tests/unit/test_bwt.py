"""OBS-04: BWT meter."""

from __future__ import annotations

import json
from pathlib import Path

from llive.evolution.bwt import BWTMeter


def _populate(tasks=("t1", "t2", "t3"), diagonal=0.8, drop=0.005):
    m = BWTMeter()
    for t in tasks:
        m.begin_task(t)
    last_idx = len(tasks) - 1
    for k, t in enumerate(tasks):
        m.record(t, k, diagonal)  # diagonal a[k][k]
        if k != last_idx:
            m.record(t, last_idx, diagonal - drop)  # a[k][K-1]
    return m


def test_summary_basic():
    m = _populate(drop=0.005)
    s = m.summarize()
    assert s.n_tasks == 3
    assert s.bwt < 0  # drop > 0
    assert s.bwt >= -0.01  # threshold satisfied
    assert len(s.per_task_drop) == 2  # last task excluded
    assert s.avg_accuracy > 0


def test_summary_empty():
    m = BWTMeter()
    s = m.summarize()
    assert s.n_tasks == 0
    assert s.bwt == 0.0


def test_positive_bwt_when_later_tasks_help():
    m = BWTMeter()
    m.begin_task("a"); m.begin_task("b")
    m.record("a", 0, 0.7)
    m.record("a", 1, 0.75)  # got better after task b
    m.record("b", 1, 0.8)
    s = m.summarize()
    assert s.bwt > 0


def test_dump_jsonl_writes_row(tmp_path: Path):
    m = _populate()
    out = tmp_path / "bwt.jsonl"
    m.dump_jsonl(out)
    line = out.read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["n_tasks"] == 3
    assert "bwt" in payload and isinstance(payload["bwt"], float)


def test_diagonal_and_final_per_task():
    m = _populate(drop=0.01)
    assert m.diagonal_accuracy("t1") is not None
    assert m.final_accuracy("t1") is not None
    assert m.diagonal_accuracy("ghost") is None


def test_begin_task_is_idempotent():
    m = BWTMeter()
    m.begin_task("a"); m.begin_task("a")
    assert m.task_order == ["a"]
