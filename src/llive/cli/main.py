# SPDX-License-Identifier: Apache-2.0
"""llive CLI — typer-based entry point (D-27).

Subcommand layout::

    llive run     --template <path> --prompt "<text>"
    llive bench   --baseline <container_id> --candidate <diff.yaml> --dataset <path>
    llive memory  query|stats|clear
    llive schema  validate|show|list
    llive route   explain|dry-run
    llive triz    principle|matrix|stats
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

# Force UTF-8 stdout/stderr so em-dashes and other non-ASCII glyphs render
# correctly on Japanese Windows (cp932) terminals. No-op on UTF-8 platforms.
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

console = Console()
app = typer.Typer(no_args_is_help=True, help="llive — self-evolving modular memory LLM framework")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@app.command()
def run(
    template: Path = typer.Option(..., "--template", "-t", help="Path to model template YAML"),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt text"),
    max_new_tokens: int = typer.Option(32, "--max-new-tokens", "-n"),
    mock: bool = typer.Option(False, "--mock", help="Skip HFAdapter (no torch required)"),
    task_tag: str | None = typer.Option(None, "--task-tag"),
):
    """Run a single inference through the llive pipeline."""
    from llive.core.adapter import AdapterConfig, HFAdapter
    from llive.orchestration.pipeline import Pipeline, load_template

    template_data = load_template(template)
    adapter = None
    if not mock:
        model_section = template_data.get("model") or {}
        try:
            adapter = HFAdapter(
                AdapterConfig(
                    model_name=model_section["name"],
                    tokenizer_name=model_section.get("tokenizer"),
                    context_length=model_section.get("context_length"),
                    dtype=str(model_section.get("dtype", "auto")),
                    device_map=model_section.get("device_map"),
                    trust_remote_code=bool(model_section.get("trust_remote_code", False)),
                )
            )
        except KeyError:
            console.print("[yellow]template missing model.name — falling back to mock[/yellow]")

    pipeline = Pipeline(adapter=adapter)
    result = pipeline.run(prompt, max_new_tokens=max_new_tokens, task_tag=task_tag)

    from rich.text import Text

    console.print(Text.assemble(("container: ", "bold"), result.container))
    console.print(Text.assemble(("request_id: ", "bold"), result.request_id))
    console.print(Text.assemble(("output: ", "bold"), result.text))
    console.print(Text.assemble(("subblocks: ", "bold"), repr([t.type for t in result.state.trace])))
    console.print(Text.assemble(("surprise: ", "bold"), repr(result.state.surprise)))
    console.print(Text.assemble(("memory: ", "bold"), f"{len(result.state.memory_accesses)} access(es)"))


# ---------------------------------------------------------------------------
# bench
# ---------------------------------------------------------------------------


@app.command()
def bench(
    baseline: str = typer.Option(..., "--baseline", "-b", help="Baseline container_id"),
    candidate: Path = typer.Option(..., "--candidate", "-c", help="CandidateDiff YAML path"),
    dataset: Path = typer.Option(..., "--dataset", "-d", help="Prompt dataset path"),
    containers_dir: Path = typer.Option(Path("specs/containers"), "--containers-dir"),
    router_spec: Path = typer.Option(Path("specs/routes/default.yaml"), "--router"),
    out_dir: Path | None = typer.Option(None, "--out"),
):
    """Run an A/B bench between a baseline container and a candidate diff."""
    from llive.evolution.bench import BenchHarness

    harness = BenchHarness(containers_dir=containers_dir, router_spec=router_spec)
    result = harness.run(
        baseline_container=baseline,
        candidate_path=candidate,
        dataset_path=dataset,
        out_dir=out_dir,
    )

    table = Table(title=f"A/B bench: {baseline} vs {result.candidate_id}")
    table.add_column("metric")
    table.add_column("baseline", justify="right")
    table.add_column("candidate", justify="right")
    for field in (
        "n_prompts",
        "mean_latency_ms",
        "p50_latency_ms",
        "p95_latency_ms",
        "memory_read_rate",
        "memory_write_rate",
        "route_entropy",
        "dead_subblock_rate",
    ):
        bv = getattr(result.baseline, field)
        cv = getattr(result.candidate, field)
        table.add_row(field, str(round(bv, 4) if isinstance(bv, float) else bv), str(round(cv, 4) if isinstance(cv, float) else cv))
    console.print(table)
    if getattr(result, "out_dir", None):
        console.print(f"results: {result.out_dir / 'results.json'}")


# ---------------------------------------------------------------------------
# memory
# ---------------------------------------------------------------------------


memory_app = typer.Typer(no_args_is_help=True, help="Inspect / manage memory")
app.add_typer(memory_app, name="memory")


@memory_app.command("query")
def memory_query(
    text: str = typer.Argument(..., help="Query text"),
    top_k: int = typer.Option(5, "--top-k"),
):
    """Top-k semantic memory query."""
    from llive.container.subblocks.builtin import get_memory_backends

    backends = get_memory_backends()
    sem = backends.ensure_semantic()
    emb = backends.encoder.encode(text)
    hits = sem.query(emb, top_k=top_k)
    if not hits:
        console.print("[yellow]no entries in semantic memory[/yellow]")
        return
    for h in hits:
        console.print(f"- [{h.score:.3f}] {h.content}  (source={h.provenance.source_type}/{h.provenance.source_id})")


@memory_app.command("stats")
def memory_stats():
    """Print row counts for each memory layer."""
    from llive.container.subblocks.builtin import get_memory_backends

    backends = get_memory_backends()
    sem = backends.ensure_semantic()
    ep = backends.ensure_episodic()
    table = Table(title="Memory stats")
    table.add_column("layer")
    table.add_column("count", justify="right")
    table.add_row("semantic", str(len(sem)))
    table.add_row("episodic", str(ep.count()))
    console.print(table)


@memory_app.command("clear")
def memory_clear(
    layer: str = typer.Option("all", "--layer", help="semantic|episodic|all"),
):
    """Reset a memory layer (Phase 1: in-memory state)."""
    from llive.container.subblocks.builtin import get_memory_backends

    backends = get_memory_backends()
    if layer in ("semantic", "all"):
        backends.ensure_semantic().clear()
    if layer in ("episodic", "all"):
        backends.ensure_episodic().clear()
    console.print(f"[green]cleared {layer}[/green]")


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------


schema_app = typer.Typer(no_args_is_help=True, help="Schema validation / inspection")
app.add_typer(schema_app, name="schema")


@schema_app.command("list")
def schema_list():
    from llive.schema.validator import known_schemas

    for n in known_schemas():
        console.print(f"- {n}")


@schema_app.command("show")
def schema_show(name: str = typer.Argument(...)):
    from llive.schema.validator import get_schema

    console.print_json(json.dumps(get_schema(name)))


@schema_app.command("validate")
def schema_validate(
    target: Path = typer.Argument(..., help="YAML file to validate"),
    kind: str | None = typer.Option(None, "--kind", help="container|subblock|candidate (auto-detect by filename if omitted)"),
):
    from llive.schema.validator import (
        SchemaValidationError,
        validate_candidate_diff,
        validate_container_spec,
        validate_subblock_spec,
    )

    if kind is None:
        name = target.name.lower()
        if "candidate" in name or "diff" in name:
            kind = "candidate"
        elif "subblock" in name:
            kind = "subblock"
        else:
            kind = "container"

    try:
        if kind == "container":
            model = validate_container_spec(target)
            console.print(f"[green]OK[/green] container {model.container_id} ({len(model.subblocks)} sub-blocks)")
        elif kind == "subblock":
            model = validate_subblock_spec(target)
            console.print(f"[green]OK[/green] subblock {model.name} v{model.version}")
        else:
            model = validate_candidate_diff(target)
            console.print(f"[green]OK[/green] candidate {model.candidate_id} ({len(model.changes)} changes)")
    except SchemaValidationError as exc:
        console.print(f"[red]FAIL[/red] {exc}")
        raise typer.Exit(code=2) from exc


# ---------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------


route_app = typer.Typer(no_args_is_help=True, help="Router inspection / dry-run")
app.add_typer(route_app, name="route")


@route_app.command("explain")
def route_explain(
    prompt: str = typer.Option(..., "--prompt", "-p"),
    router_spec: Path = typer.Option(Path("specs/routes/default.yaml"), "--router"),
):
    from llive.router.engine import RouterEngine

    eng = RouterEngine(router_spec)
    decision = eng.select(prompt)
    console.print_json(decision.explanation.model_dump_json())


@route_app.command("dry-run")
def route_dry_run(
    prompt: str = typer.Option(..., "--prompt", "-p"),
    router_spec: Path = typer.Option(Path("specs/routes/default.yaml"), "--router"),
):
    from llive.router.engine import RouterEngine

    eng = RouterEngine(router_spec)
    decision = eng.select(prompt)
    console.print(decision.container)


# ---------------------------------------------------------------------------
# triz
# ---------------------------------------------------------------------------


triz_app = typer.Typer(no_args_is_help=True, help="TRIZ resource lookup (read-only in Phase 1)")
app.add_typer(triz_app, name="triz")


@triz_app.command("stats")
def triz_stats():
    from llive.triz.loader import load_attributes, load_matrix, load_principles

    table = Table(title="TRIZ resources")
    table.add_column("resource")
    table.add_column("count", justify="right")
    table.add_row("principles", str(len(load_principles())))
    table.add_row("attributes", str(len(load_attributes())))
    table.add_row("matrix_cells", str(len(load_matrix())))
    console.print(table)


@triz_app.command("principle")
def triz_principle(principle_id: int = typer.Argument(...)):
    from llive.triz.loader import load_principles

    p = load_principles().get(int(principle_id))
    if p is None:
        console.print(f"[red]principle {principle_id} not found[/red]")
        raise typer.Exit(code=2)
    console.print(f"[bold]{p.id}.[/bold] {p.name}")
    if p.description:
        console.print(p.description)
    if p.examples:
        for ex in p.examples:
            console.print(f"  - {ex}")


@triz_app.command("matrix")
def triz_matrix(
    improving: int = typer.Argument(..., help="Improving attribute id"),
    worsening: int = typer.Argument(..., help="Worsening attribute id"),
):
    from llive.triz.loader import lookup_principles

    ps = lookup_principles(improving, worsening)
    if not ps:
        console.print(
            f"[yellow]no recommendation for ({improving}, {worsening}) — compact matrix may not cover this cell[/yellow]"
        )
        return
    for p in ps:
        console.print(f"- {p.id}. {p.name}")


# ---------------------------------------------------------------------------


if __name__ == "__main__":
    app()
