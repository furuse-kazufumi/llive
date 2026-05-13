"""Extra coverage for triz/loader.py edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.triz import loader as _loader
from llive.triz.loader import (
    Attribute,
    Principle,
    load_attributes,
    load_matrix,
    load_principles,
    lookup_principles,
)


def test_load_principles_returns_principle_instances():
    p = load_principles()
    assert all(isinstance(v, Principle) for v in p.values())


def test_load_attributes_returns_attribute_instances():
    a = load_attributes()
    assert all(isinstance(v, Attribute) for v in a.values())


def test_lookup_principles_unknown_pair_returns_empty():
    # IDs that almost certainly aren't in the compact matrix
    assert lookup_principles(38, 38) == []


def test_lookup_principles_known_pair():
    # (9, 13) is documented in the compact matrix
    ps = lookup_principles(9, 13)
    assert len(ps) >= 1
    assert all(isinstance(p, Principle) for p in ps)


def test_resource_path_missing_raises(monkeypatch):
    with pytest.raises(FileNotFoundError):
        _loader._resource_path("does_not_exist.yaml")


def test_project_root_locator_finds_dev_tree():
    root = _loader._project_root()
    assert (root / "specs" / "resources").is_dir()


def test_unwrap_list_handles_dict_wrapper():
    payload = {"items": [{"id": 1, "name": "x"}]}
    out = _loader._unwrap_list(payload)
    assert out == [{"id": 1, "name": "x"}]


def test_unwrap_list_handles_list_directly():
    out = _loader._unwrap_list([{"id": 2, "name": "y"}])
    assert out == [{"id": 2, "name": "y"}]


def test_unwrap_list_filters_non_dicts():
    out = _loader._unwrap_list([{"id": 3}, "not-a-dict", 42, None])
    assert out == [{"id": 3}]


def test_unwrap_list_empty_or_none():
    assert _loader._unwrap_list(None) == []
    assert _loader._unwrap_list({}) == []


def test_coerce_principle_uses_brief_when_no_description():
    p = _loader._coerce_principle({"id": 5, "name": "X", "brief": "short"})
    assert p.description == "short"


def test_coerce_principle_uses_examples_or_apps():
    p = _loader._coerce_principle(
        {"id": 6, "name": "X", "llive_applications": ["a", "b"]}
    )
    assert p.examples == ("a", "b")


def test_coerce_attribute_uses_jp_when_no_description():
    a = _loader._coerce_attribute({"id": 7, "name": "X", "jp": "Japanese desc"})
    assert a.description == "Japanese desc"
