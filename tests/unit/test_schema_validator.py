# SPDX-License-Identifier: Apache-2.0
"""BC-03: schema validation positive/negative cases."""

from __future__ import annotations

import pytest

from llive.schema.validator import (
    SchemaValidationError,
    validate_candidate_diff,
    validate_container_spec,
    validate_subblock_spec,
)

# ---------------------------------------------------------------------------
# container-spec
# ---------------------------------------------------------------------------


def test_container_spec_positive():
    spec = {
        "schema_version": 1,
        "container_id": "fast_path_v1",
        "subblocks": [{"type": "pre_norm"}, {"type": "ffn_swiglu"}],
    }
    m = validate_container_spec(spec)
    assert m.container_id == "fast_path_v1"
    assert len(m.subblocks) == 2


@pytest.mark.parametrize(
    "spec,err_keyword",
    [
        ({"schema_version": 1, "container_id": "BAD", "subblocks": []}, "subblocks"),
        ({"schema_version": 1, "container_id": "valid_v1"}, "subblocks"),
        ({"schema_version": 2, "container_id": "valid_v1", "subblocks": [{"type": "x"}]}, "schema_version"),
        (
            {
                "schema_version": 1,
                "container_id": "ok_v1",
                "subblocks": [{"type": "x"}],
                "unknown": True,
            },
            "unknown",
        ),
    ],
)
def test_container_spec_negative(spec, err_keyword):
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_container_spec(spec)
    msg = str(exc_info.value).lower()
    assert err_keyword in msg or any(err_keyword in e.lower() for e in exc_info.value.errors)


# ---------------------------------------------------------------------------
# candidate-diff
# ---------------------------------------------------------------------------


def test_candidate_diff_positive():
    diff = {
        "schema_version": 1,
        "candidate_id": "cand_20260513_001",
        "base_candidate": "fast_path_v1",
        "changes": [
            {
                "action": "insert_subblock",
                "target_container": "fast_path_v1",
                "after": "pre_norm",
                "spec": {"type": "memory_read"},
            },
            {
                "action": "remove_subblock",
                "target_container": "fast_path_v1",
                "target_subblock": "ffn_swiglu",
            },
        ],
    }
    m = validate_candidate_diff(diff)
    assert m.candidate_id == "cand_20260513_001"
    assert len(m.changes) == 2


def test_candidate_diff_negative_empty_changes():
    diff = {
        "schema_version": 1,
        "candidate_id": "cand_20260513_001",
        "base_candidate": "fast_path_v1",
        "changes": [],
    }
    with pytest.raises(SchemaValidationError):
        validate_candidate_diff(diff)


def test_candidate_diff_negative_bad_id():
    diff = {
        "schema_version": 1,
        "candidate_id": "wrong_format",
        "base_candidate": "fast_path_v1",
        "changes": [
            {
                "action": "insert_subblock",
                "target_container": "fast_path_v1",
                "after": "head",
                "spec": {"type": "memory_read"},
            }
        ],
    }
    with pytest.raises(SchemaValidationError):
        validate_candidate_diff(diff)


# ---------------------------------------------------------------------------
# subblock-spec
# ---------------------------------------------------------------------------


def test_subblock_spec_positive():
    spec = {
        "schema_version": 1,
        "name": "pre_norm",
        "version": "1.0.0",
        "io_contract": {
            "input": {"hidden_dim": 768, "seq_dim": True, "extras": []},
            "output": {"hidden_dim": 768, "seq_dim": True, "extras": []},
        },
        "plugin_module": "llive.container.subblocks.builtin",
    }
    m = validate_subblock_spec(spec)
    assert m.name == "pre_norm"
    assert m.version == "1.0.0"
