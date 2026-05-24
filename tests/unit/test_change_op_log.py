# SPDX-License-Identifier: Apache-2.0
"""Real ChangeOp action-sequence logging (SPEC-MESH-01) — unit tests.

Cover the instance→label mapping (all four Phase-1 ops + the error path), the
JSONL record round-trip, chronological flattening into an action stream, the
``applied_only`` filter, the empty-ops no-op, and cold-start (missing file)
reading.
"""

from __future__ import annotations

import pytest

from llive.evolution.change_op import (
    ChangeOp,
    InsertSubblock,
    RemoveSubblock,
    ReorderSubblocks,
    ReplaceSubblock,
)
from llive.evolution.change_op_log import (
    ChangeOpLogError,
    ChangeOpSequenceLog,
    op_action_label,
    op_action_labels,
)
from llive.schema.models import SubBlockRef


def _ref(type_: str = "ffn_swiglu", name: str | None = None) -> SubBlockRef:
    return SubBlockRef(type=type_, name=name)


def _one_of_each() -> list[ChangeOp]:
    return [
        InsertSubblock(target_container="c", after="head", spec=_ref(name="new")),
        RemoveSubblock(target_container="c", target_subblock="old"),
        ReplaceSubblock(target_container="c", from_="a", to=_ref(name="b")),
        ReorderSubblocks(target_container="c", new_order=["x", "y"]),
    ]


# --- instance -> label mapping ----------------------------------------------


def test_op_action_label_maps_all_four_ops() -> None:
    labels = op_action_labels(_one_of_each())
    assert labels == [
        "insert_subblock",
        "remove_subblock",
        "replace_subblock",
        "reorder_subblocks",
    ]


def test_op_action_label_rejects_unknown_changeop() -> None:
    class _Mystery(ChangeOp):  # not in the Phase-1 mapping
        target_container = "c"

        def apply(self, container):  # pragma: no cover - never applied here
            return container

        def invert(self, container_before):  # pragma: no cover
            return self

    with pytest.raises(ChangeOpLogError):
        op_action_label(_Mystery())


# --- record round-trip ------------------------------------------------------


def test_record_ops_round_trips_through_jsonl(tmp_path) -> None:
    log = ChangeOpSequenceLog(tmp_path / "ops.jsonl")
    rec = log.record_ops(
        _one_of_each(),
        source="unit",
        candidate_id="cand_1",
        container_id="c",
    )
    assert rec is not None
    (back,) = list(log.iter_records())
    assert back.actions == (
        "insert_subblock",
        "remove_subblock",
        "replace_subblock",
        "reorder_subblocks",
    )
    assert back.candidate_id == "cand_1"
    assert back.container_id == "c"
    assert back.applied is True
    assert back.ts  # an ISO timestamp was stamped


def test_record_ops_empty_is_noop(tmp_path) -> None:
    log = ChangeOpSequenceLog(tmp_path / "ops.jsonl")
    assert log.record_ops([], source="unit") is None
    assert not log.path.exists()  # nothing written, no empty burst pollutes the stream


# --- action stream flattening -----------------------------------------------


def test_action_stream_concatenates_records_in_write_order(tmp_path) -> None:
    log = ChangeOpSequenceLog(tmp_path / "ops.jsonl")
    log.record_actions(["insert_subblock", "remove_subblock"], source="unit")
    log.record_actions(["replace_subblock"], source="unit")
    assert log.action_stream() == [
        "insert_subblock",
        "remove_subblock",
        "replace_subblock",
    ]


def test_action_stream_applied_only_filters_failed_bursts(tmp_path) -> None:
    log = ChangeOpSequenceLog(tmp_path / "ops.jsonl")
    log.record_actions(["insert_subblock"], source="unit", applied=True)
    log.record_actions(["remove_subblock"], source="unit", applied=False)
    assert log.action_stream(applied_only=True) == ["insert_subblock"]
    assert log.action_stream(applied_only=False) == [
        "insert_subblock",
        "remove_subblock",
    ]


def test_action_stream_missing_file_is_empty(tmp_path) -> None:
    log = ChangeOpSequenceLog(tmp_path / "does_not_exist.jsonl")
    assert log.action_stream() == []
    assert list(log.iter_records()) == []


def test_iter_records_skips_foreign_rows(tmp_path) -> None:
    path = tmp_path / "mixed.jsonl"
    path.write_text(
        '{"row": "summary", "n": 1}\n'
        '{"row": "change_op_seq", "actions": ["insert_subblock"], "applied": true}\n'
        "\n",  # blank line tolerated
        encoding="utf-8",
    )
    log = ChangeOpSequenceLog(path)
    records = list(log.iter_records())
    assert len(records) == 1
    assert records[0].actions == ("insert_subblock",)
