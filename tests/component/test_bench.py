"""EVO-01 component test: A/B bench runs end-to-end."""

from __future__ import annotations

from pathlib import Path

from llive.evolution.bench import BenchHarness


def test_bench_runs_baseline_vs_candidate(project_root: Path, tmp_path: Path):
    out_dir = tmp_path / "bench_out"
    harness = BenchHarness(
        containers_dir=project_root / "specs/containers",
        router_spec=project_root / "specs/routes/default.yaml",
    )
    result = harness.run(
        baseline_container="fast_path_v1",
        candidate_path=project_root / "specs/candidates/example_001.yaml",
        dataset_path=project_root / "tests/data/mvr_bench/prompts.txt",
        out_dir=out_dir,
    )

    assert result.n_prompts >= 5
    assert result.baseline.n_prompts == result.n_prompts
    assert result.candidate.n_prompts == result.n_prompts

    # Candidate adds memory_read + memory_write, so its rates must dominate baseline.
    assert result.candidate.memory_read_rate > result.baseline.memory_read_rate
    assert result.candidate.memory_write_rate >= result.baseline.memory_write_rate

    # results.json + candidate_container.yaml were written
    assert (out_dir / "results.json").exists()
    assert (out_dir / "candidate_container.yaml").exists()
