# SPDX-License-Identifier: Apache-2.0
"""Tests for the Brief schema, validation, and YAML loader (LLIVE-002 Step 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import (
    Brief,
    BriefValidationError,
    brief_to_dict,
    load_brief,
    loads_brief,
)
from llive.fullsense.types import EpistemicType


# ---------------------------------------------------------------------------
# Brief dataclass — defaults and immutability
# ---------------------------------------------------------------------------


def test_brief_minimal_fields_use_defaults() -> None:
    b = Brief(brief_id="b1", goal="Do the thing")
    assert b.constraints == ()
    assert b.source == "manual"
    assert b.priority == pytest.approx(0.5)
    assert b.epistemic_type is EpistemicType.PRAGMATIC
    assert b.backend == ""
    assert b.tools == ()
    assert b.success_criteria == ()
    assert b.approval_required is True
    assert b.ledger_path is None


def test_brief_is_frozen() -> None:
    b = Brief(brief_id="b1", goal="x")
    with pytest.raises(Exception):  # FrozenInstanceError is dataclass-specific
        b.goal = "mutated"  # type: ignore[misc]


def test_brief_is_hashable() -> None:
    b1 = Brief(brief_id="b1", goal="x")
    b2 = Brief(brief_id="b1", goal="x")
    # Equal Briefs share a hash (frozen dataclass + tuple fields).
    assert hash(b1) == hash(b2)
    assert b1 == b2


# ---------------------------------------------------------------------------
# Validation — brief_id, goal, priority, collection shapes
# ---------------------------------------------------------------------------


def test_brief_id_rejects_empty() -> None:
    with pytest.raises(BriefValidationError, match="brief_id"):
        Brief(brief_id="", goal="x")


def test_brief_id_rejects_path_traversal() -> None:
    # ``../`` and slashes would break the ledger-path mapping.
    with pytest.raises(BriefValidationError, match="brief_id"):
        Brief(brief_id="../escape", goal="x")


def test_brief_id_rejects_whitespace() -> None:
    with pytest.raises(BriefValidationError, match="brief_id"):
        Brief(brief_id="has space", goal="x")


def test_brief_id_allows_dash_dot_underscore() -> None:
    b = Brief(brief_id="webpage-portal-refresh_v0.7", goal="x")
    assert b.brief_id == "webpage-portal-refresh_v0.7"


def test_goal_rejects_empty_or_whitespace() -> None:
    with pytest.raises(BriefValidationError, match="goal"):
        Brief(brief_id="b1", goal="")
    with pytest.raises(BriefValidationError, match="goal"):
        Brief(brief_id="b1", goal="   ")


def test_priority_must_be_in_unit_range() -> None:
    Brief(brief_id="b1", goal="x", priority=0.0)
    Brief(brief_id="b1", goal="x", priority=1.0)
    with pytest.raises(BriefValidationError, match="priority"):
        Brief(brief_id="b1", goal="x", priority=-0.01)
    with pytest.raises(BriefValidationError, match="priority"):
        Brief(brief_id="b1", goal="x", priority=1.01)


def test_constraints_must_be_tuple_not_list() -> None:
    # We force tuple at the dataclass level to keep it hashable.
    with pytest.raises(BriefValidationError, match="constraints"):
        Brief(brief_id="b1", goal="x", constraints=["foo"])  # type: ignore[arg-type]


def test_ledger_path_must_be_pathlib() -> None:
    Brief(brief_id="b1", goal="x", ledger_path=Path("/tmp/x.db"))
    with pytest.raises(BriefValidationError, match="ledger_path"):
        Brief(brief_id="b1", goal="x", ledger_path="/tmp/x.db")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# brief_to_dict — JSON/YAML-friendly serialisation
# ---------------------------------------------------------------------------


def test_brief_to_dict_serialises_tuples_and_path() -> None:
    b = Brief(
        brief_id="b1",
        goal="Do x",
        constraints=("no rm -rf",),
        tools=("read_file", "write_file"),
        success_criteria=("tests pass",),
        epistemic_type=EpistemicType.PRAGMATIC,
        ledger_path=Path("/tmp/x.db"),
    )
    d = brief_to_dict(b)
    assert d["brief_id"] == "b1"
    assert d["constraints"] == ["no rm -rf"]
    assert d["tools"] == ["read_file", "write_file"]
    assert d["success_criteria"] == ["tests pass"]
    assert d["epistemic_type"] == "pragmatic"
    assert d["ledger_path"] == "/tmp/x.db"
    # No tuples or Paths in the output — must be JSON-serialisable.
    import json

    json.dumps(d)


# ---------------------------------------------------------------------------
# YAML loader — happy path + round-trip
# ---------------------------------------------------------------------------


_YAML_FULL = """\
brief_id: webpage-portal-refresh-2026-05-16
goal: |
  Refactor docs/index.md to render Mermaid correctly under just-the-docs.
constraints:
  - "no inline HTML inside fenced ```mermaid``` blocks"
  - "preserve all existing external links"
source: portal:fullsense
priority: 0.7
epistemic_type: pragmatic
backend: ollama:qwen2.5:14b
tools:
  - read_file
  - write_file
success_criteria:
  - "rendered HTML at /docs/index.md contains an SVG"
approval_required: true
"""


def test_loads_brief_full_yaml() -> None:
    b = loads_brief(_YAML_FULL)
    assert b.brief_id == "webpage-portal-refresh-2026-05-16"
    assert "Refactor docs/index.md" in b.goal
    assert b.constraints == (
        "no inline HTML inside fenced ```mermaid``` blocks",
        "preserve all existing external links",
    )
    assert b.source == "portal:fullsense"
    assert b.priority == pytest.approx(0.7)
    assert b.epistemic_type is EpistemicType.PRAGMATIC
    assert b.backend == "ollama:qwen2.5:14b"
    assert b.tools == ("read_file", "write_file")
    assert b.approval_required is True


def test_loads_brief_minimal_yaml() -> None:
    b = loads_brief("brief_id: b1\ngoal: just do it\n")
    assert b.brief_id == "b1"
    assert b.goal == "just do it"
    assert b.source == "manual"  # default applied


def test_load_brief_reads_file(tmp_path: Path) -> None:
    p = tmp_path / "brief.yaml"
    p.write_text(_YAML_FULL, encoding="utf-8")
    b = load_brief(p)
    assert b.brief_id == "webpage-portal-refresh-2026-05-16"


def test_load_brief_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(BriefValidationError, match="not found"):
        load_brief(tmp_path / "does-not-exist.yaml")


def test_loads_brief_rejects_unknown_field() -> None:
    with pytest.raises(BriefValidationError, match="unknown Brief field"):
        loads_brief("brief_id: b1\ngoal: x\nflavor: vanilla\n")


def test_loads_brief_rejects_missing_required() -> None:
    with pytest.raises(BriefValidationError, match="brief_id"):
        loads_brief("goal: x\n")
    with pytest.raises(BriefValidationError, match="goal"):
        loads_brief("brief_id: b1\n")


def test_loads_brief_rejects_bare_string_under_list_key() -> None:
    # forgot the dash — classic YAML mistake
    with pytest.raises(BriefValidationError, match="constraints"):
        loads_brief("brief_id: b1\ngoal: x\nconstraints: only-one\n")


def test_loads_brief_rejects_invalid_epistemic_type() -> None:
    with pytest.raises(BriefValidationError, match="epistemic_type"):
        loads_brief("brief_id: b1\ngoal: x\nepistemic_type: bogus\n")


def test_loads_brief_rejects_non_mapping_root() -> None:
    with pytest.raises(BriefValidationError, match="mapping"):
        loads_brief("- not a mapping\n")


def test_loads_brief_invalid_yaml_syntax() -> None:
    with pytest.raises(BriefValidationError, match="invalid YAML"):
        loads_brief("brief_id: [unterminated\n")


def test_loads_brief_round_trip_via_brief_to_dict() -> None:
    import yaml

    original = loads_brief(_YAML_FULL)
    serialised = yaml.safe_dump(brief_to_dict(original))
    recovered = loads_brief(serialised)
    assert recovered == original


def test_loads_brief_expands_user_home_in_ledger_path() -> None:
    b = loads_brief(
        "brief_id: b1\ngoal: x\nledger_path: ~/.llive/briefs/b1.db\n"
    )
    assert b.ledger_path is not None
    assert "~" not in b.ledger_path.as_posix()
