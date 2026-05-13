"""Extra coverage for evolution/bench.py dataset variants + edge paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llive.evolution.bench import BenchHarness, _load_dataset, _percentile


def test_percentile_empty_returns_zero():
    assert _percentile([], 50) == 0.0


def test_percentile_single():
    assert _percentile([7.5], 50) == 7.5


def test_percentile_pair_p50():
    assert _percentile([1.0, 3.0], 50) == 2.0


def test_load_dataset_txt(tmp_path: Path):
    f = tmp_path / "p.txt"
    f.write_text("p1\np2\n\np3\n", encoding="utf-8")
    out = _load_dataset(f)
    assert out == ["p1", "p2", "p3"]


def test_load_dataset_jsonl(tmp_path: Path):
    f = tmp_path / "p.jsonl"
    f.write_text(json.dumps({"prompt": "alpha"}) + "\n" + json.dumps({"prompt": "beta"}) + "\n",
                 encoding="utf-8")
    out = _load_dataset(f)
    assert out == ["alpha", "beta"]


def test_load_dataset_directory(tmp_path: Path):
    d = tmp_path / "ds"
    d.mkdir()
    (d / "a.txt").write_text("a1\na2\n", encoding="utf-8")
    (d / "b.txt").write_text("b1\n", encoding="utf-8")
    out = _load_dataset(d)
    assert set(out) == {"a1", "a2", "b1"}


def test_load_dataset_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        _load_dataset(tmp_path / "nope.txt")


def test_load_dataset_unsupported(tmp_path: Path):
    f = tmp_path / "x.csv"
    f.write_text("a,b,c\n", encoding="utf-8")
    with pytest.raises(ValueError):
        _load_dataset(f)


def test_bench_missing_container_raises(project_root: Path, tmp_path: Path):
    harness = BenchHarness(
        containers_dir=project_root / "specs/containers",
        router_spec=project_root / "specs/routes/default.yaml",
    )
    with pytest.raises(FileNotFoundError):
        harness.run(
            baseline_container="does_not_exist",
            candidate_path=project_root / "specs/candidates/example_001.yaml",
            dataset_path=project_root / "tests/data/mvr_bench/prompts.txt",
            out_dir=tmp_path,
        )


def test_bench_empty_dataset_raises(project_root: Path, tmp_path: Path):
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    harness = BenchHarness(
        containers_dir=project_root / "specs/containers",
        router_spec=project_root / "specs/routes/default.yaml",
    )
    with pytest.raises(ValueError):
        harness.run(
            baseline_container="fast_path_v1",
            candidate_path=project_root / "specs/candidates/example_001.yaml",
            dataset_path=empty,
            out_dir=tmp_path / "out",
        )
