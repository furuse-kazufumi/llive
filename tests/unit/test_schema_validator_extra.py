"""Extra coverage for schema/validator.py edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.schema import validator as _validator
from llive.schema.validator import (
    SchemaValidationError,
    get_schema,
    known_schemas,
    validate_candidate_diff,
    validate_container_spec,
    validate_subblock_spec,
)


def test_known_schemas_lists_all():
    out = known_schemas()
    assert {"container-spec.v1", "subblock-spec.v1", "candidate-diff.v1"} <= set(out)


def test_get_schema_returns_dict():
    schema = get_schema("container-spec.v1")
    assert isinstance(schema, dict)
    assert "$id" in schema


def test_get_schema_unknown_raises():
    with pytest.raises(KeyError):
        get_schema("not-a-schema.v1")


def test_validate_from_path(tmp_path: Path):
    yaml_path = tmp_path / "spec.yaml"
    yaml_path.write_text(
        """\
schema_version: 1
container_id: from_path_v1
subblocks:
  - type: pre_norm
""",
        encoding="utf-8",
    )
    spec = validate_container_spec(yaml_path)
    assert spec.container_id == "from_path_v1"


def test_validate_subblock_spec_round_trip():
    data = {
        "schema_version": 1,
        "name": "x_block",
        "version": "1.0.0",
        "io_contract": {
            "input": {"hidden_dim": 64, "seq_dim": True, "extras": []},
            "output": {"hidden_dim": 64, "seq_dim": True, "extras": []},
        },
        "plugin_module": "some.module",
    }
    m = validate_subblock_spec(data)
    assert m.name == "x_block"


def test_validate_candidate_diff_negative_action():
    bad = {
        "schema_version": 1,
        "candidate_id": "cand_20260513_999",
        "base_candidate": "x_v1",
        "changes": [{"action": "unknown_action"}],
    }
    with pytest.raises(SchemaValidationError):
        validate_candidate_diff(bad)


def test_packaged_schema_path_used_when_available():
    """The packaged _specs path should be discovered first."""
    path = _validator._packaged_schema_path("container-spec.v1.json")
    assert path is None or path.exists()
