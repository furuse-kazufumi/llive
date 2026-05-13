"""Extended CLI tests covering Phase 1 + Phase 2 subcommands.

Complements ``tests/component/test_cli.py`` (Phase 1 baseline) by hitting
every subcommand at least once. CliRunner + ``mix_stderr=False`` so we
can inspect outputs without rich markup eating brackets.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from llive.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# triz
# ---------------------------------------------------------------------------


def test_cli_triz_principle_known():
    res = runner.invoke(app, ["triz", "principle", "1"])
    assert res.exit_code == 0
    assert "1." in res.stdout


def test_cli_triz_principle_unknown():
    res = runner.invoke(app, ["triz", "principle", "9999"])
    assert res.exit_code == 2


def test_cli_triz_matrix_no_hit():
    # An (improving, worsening) pair not in the compact matrix should report no recommendation
    res = runner.invoke(app, ["triz", "matrix", "99", "99"])
    assert res.exit_code == 0
    assert "no recommendation" in res.stdout.lower()


def test_cli_triz_matrix_with_hit():
    res = runner.invoke(app, ["triz", "matrix", "9", "13"])
    assert res.exit_code == 0


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------


def test_cli_schema_show_container_spec():
    res = runner.invoke(app, ["schema", "show", "container-spec.v1"])
    assert res.exit_code == 0
    assert "container_id" in res.stdout


def test_cli_schema_validate_kind_autodetect_container(project_root: Path):
    """Filename without 'candidate' / 'diff' / 'subblock' falls back to container."""
    target = project_root / "specs" / "containers" / "fast_path_v1.yaml"
    res = runner.invoke(app, ["schema", "validate", str(target)])
    assert res.exit_code == 0


def test_cli_schema_validate_kind_autodetect_candidate(tmp_path):
    f = tmp_path / "candidate_demo.yaml"
    f.write_text(
        """\
schema_version: 1
candidate_id: cand_20260513_111
base_candidate: fast_path_v1
changes:
  - action: insert_subblock
    target_container: fast_path_v1
    after: head
    spec: {type: memory_read}
""",
        encoding="utf-8",
    )
    res = runner.invoke(app, ["schema", "validate", str(f)])
    assert res.exit_code == 0


def test_cli_schema_validate_failure(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "schema_version: 1\ncontainer_id: BadId\nsubblocks: []\n",
        encoding="utf-8",
    )
    res = runner.invoke(app, ["schema", "validate", str(bad), "--kind", "container"])
    assert res.exit_code == 2


def test_cli_schema_validate_subblock(tmp_path):
    target = tmp_path / "sub_spec.yaml"
    target.write_text(
        """\
schema_version: 1
name: pre_norm
version: 1.0.0
io_contract:
  input: {hidden_dim: 64, seq_dim: true, extras: []}
  output: {hidden_dim: 64, seq_dim: true, extras: []}
plugin_module: llive.container.subblocks.builtin
""",
        encoding="utf-8",
    )
    res = runner.invoke(app, ["schema", "validate", str(target), "--kind", "subblock"])
    assert res.exit_code == 0


# ---------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------


def test_cli_route_explain_outputs_json():
    res = runner.invoke(app, ["route", "explain", "--prompt", "hello"])
    assert res.exit_code == 0
    assert "selected_container" in res.stdout


# ---------------------------------------------------------------------------
# memory
# ---------------------------------------------------------------------------


def test_cli_memory_query_empty():
    res = runner.invoke(app, ["memory", "query", "x"])
    assert res.exit_code == 0
    assert "no entries" in res.stdout.lower()


def test_cli_memory_stats():
    res = runner.invoke(app, ["memory", "stats"])
    assert res.exit_code == 0
    assert "semantic" in res.stdout


def test_cli_memory_clear_all():
    res = runner.invoke(app, ["memory", "clear", "--layer", "all"])
    assert res.exit_code == 0


# ---------------------------------------------------------------------------
# run --mock + template falling back
# ---------------------------------------------------------------------------


def test_cli_run_template_missing_model_name(tmp_path):
    """Template missing model.name should fall back to mock and still succeed."""
    bad_template = tmp_path / "tpl.yaml"
    bad_template.write_text("schema_version: 1\nnotes: ['malformed']\n", encoding="utf-8")
    res = runner.invoke(app, ["run", "--template", str(bad_template), "--prompt", "hi"])
    assert res.exit_code == 0
    assert "mock-output" in res.stdout


def test_cli_run_with_task_tag(project_root: Path):
    template = project_root / "specs/templates/qwen2_5_0_5b.yaml"
    res = runner.invoke(
        app,
        ["run", "--template", str(template), "--prompt", "x", "--mock", "--task-tag", "math"],
    )
    assert res.exit_code == 0


# ---------------------------------------------------------------------------
# bench
# ---------------------------------------------------------------------------


def test_cli_bench_smoke(project_root: Path, tmp_path):
    res = runner.invoke(
        app,
        [
            "bench",
            "--baseline",
            "fast_path_v1",
            "--candidate",
            str(project_root / "specs/candidates/example_001.yaml"),
            "--dataset",
            str(project_root / "tests/data/mvr_bench/prompts.txt"),
            "--out",
            str(tmp_path / "bench_out"),
        ],
    )
    assert res.exit_code == 0
    assert (tmp_path / "bench_out" / "results.json").exists()


# ---------------------------------------------------------------------------
# triz stats covered by Phase 1 test_cli; ensure llive --help mentions it
# ---------------------------------------------------------------------------


def test_cli_root_help_lists_subcommands():
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    for sub in ("run", "bench", "memory", "schema", "route", "triz"):
        assert sub in res.stdout
