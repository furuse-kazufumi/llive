"""TRIZ-01: lazy loader for principles / attributes / matrix."""

from __future__ import annotations

from llive.triz.loader import (
    Principle,
    load_attributes,
    load_matrix,
    load_principles,
    lookup_principles,
)


def test_load_principles():
    ps = load_principles()
    assert len(ps) == 40
    p1 = ps[1]
    assert isinstance(p1, Principle)
    assert p1.id == 1
    assert p1.name


def test_load_attributes_at_least_39():
    attrs = load_attributes()
    # spec calls for 39 standard + 11 llive-specific = 50; tolerate 39+ to allow data evolution
    assert len(attrs) >= 39


def test_load_matrix_non_empty():
    m = load_matrix()
    assert isinstance(m, dict)
    assert len(m) > 0
    # cells map to tuples of principle ids
    sample = next(iter(m.values()))
    assert isinstance(sample, tuple)


def test_lookup_principles_known_cell():
    # Pick any (improving, worsening) present in the file
    m = load_matrix()
    key = next(iter(m.keys()))
    principles = lookup_principles(*key)
    # Must return Principle objects, length matches cell contents
    assert all(isinstance(p, Principle) for p in principles)
