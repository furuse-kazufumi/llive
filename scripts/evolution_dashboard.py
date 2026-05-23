# SPDX-License-Identifier: Apache-2.0
"""Evolution Dashboard — N island の「進化ポートフォリオ」可視化.

``scripts/demo_island_evolution.py`` が書き出す:

* ``<out_dir>/island_NN/generations.jsonl`` — 各 island の世代ごと統計
* ``<out_dir>/migrations.jsonl`` — migration 履歴
* ``<out_dir>/summary.json`` — 終了時サマリ

を読んで, 各 island の best/mean/diversity 推移を sparkline + table で
表示する. ``rich`` が入っていればカラー & live 更新, 無ければ plain text.

使い方::

    # one-shot snapshot
    py -3.11 scripts/evolution_dashboard.py out/island_evolution

    # watch mode (2 秒ごとに更新, 実行中の run を横目に見る)
    py -3.11 scripts/evolution_dashboard.py out/island_evolution --watch 2

    # plain text 強制 (CI / log 取り)
    py -3.11 scripts/evolution_dashboard.py out/island_evolution --plain
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table

    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


_SPARK_GLYPHS = "▁▂▃▄▅▆▇█"
_DIVERSITY_WARN_RATIO = 10.0  # diversity_floor (1e-6) × 10 を warning 閾値に
_PROGRESS_BAR_WIDTH = 32


def _ascii_progress_bar(ratio: float, width: int = _PROGRESS_BAR_WIDTH) -> str:
    ratio = max(0.0, min(1.0, ratio))
    filled = int(width * ratio)
    return "█" * filled + "░" * (width - filled)


def _ensure_utf8_stdout() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _sparkline(values: list[float], width: int = 24) -> str:
    if not values:
        return ""
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = values
    lo = min(sampled)
    hi = max(sampled)
    rng = hi - lo if hi > lo else 1.0
    return "".join(
        _SPARK_GLYPHS[
            min(
                len(_SPARK_GLYPHS) - 1,
                int((v - lo) / rng * (len(_SPARK_GLYPHS) - 1)),
            )
        ]
        for v in sampled
    )


def _load_island_jsonl(out_dir: Path) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = {}
    for island_dir in sorted(out_dir.glob("island_*")):
        try:
            idx = int(island_dir.name.split("_")[-1])
        except ValueError:
            continue
        path = island_dir / "generations.jsonl"
        if not path.exists():
            continue
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        result[idx] = rows
    return result


def _load_migrations(out_dir: Path) -> list[dict[str, Any]]:
    path = out_dir / "migrations.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _load_summary(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / "summary.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _load_manifest(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / "manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _compute_progress(
    islands_data: dict[int, list[dict[str, Any]]],
    manifest: dict[str, Any] | None,
    summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """current_gen / max_gen / progress_ratio / status を算出.

    * ``current_gen`` = 全 island の wall_gen の最大 + 1 (= これまで完了した世代数)
    * ``max_gen`` = manifest.max_generations が真. 無ければ summary, それも無ければ
      current_gen を仮の最大として表示.
    * ``status`` = "running" / "completed" / "idle".
    """
    max_wall_gen = -1
    for rows in islands_data.values():
        for r in rows:
            wg = int(r.get("wall_gen", -1))
            if wg > max_wall_gen:
                max_wall_gen = wg
    current_gen = max_wall_gen + 1 if max_wall_gen >= 0 else 0

    max_gen: int | None = None
    if manifest is not None:
        max_gen = int(manifest.get("max_generations", 0))
    if max_gen is None and summary is not None:
        max_gen = int(summary.get("max_generations", 0))

    if summary is not None:
        status = "completed"
    elif current_gen > 0:
        status = "running"
    else:
        status = "idle"

    if max_gen is None or max_gen <= 0:
        max_gen = max(current_gen, 1)
        ratio = 1.0 if status == "completed" else 0.0
    else:
        ratio = min(1.0, current_gen / max_gen)

    elapsed = float(summary.get("elapsed_seconds", 0.0)) if summary else 0.0
    if status == "running" and manifest is not None:
        started = float(manifest.get("started_at_epoch", 0.0))
        if started > 0:
            elapsed = max(0.0, time.time() - started)

    eta_seconds: float | None = None
    if status == "running" and current_gen > 0 and max_gen > current_gen and elapsed > 0:
        per_gen = elapsed / current_gen
        eta_seconds = per_gen * (max_gen - current_gen)

    return {
        "current_gen": current_gen,
        "max_gen": max_gen,
        "progress_ratio": ratio,
        "status": status,
        "elapsed_seconds": elapsed,
        "eta_seconds": eta_seconds,
    }


def _format_duration(seconds: float) -> str:
    if seconds < 0:
        return "?"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60.0
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60.0
    return f"{hours:.1f}h"


def _build_island_table(
    islands_data: dict[int, list[dict[str, Any]]],
    summary: dict[str, Any] | None,
):
    table = Table(
        title="Island Portfolio", show_header=True, header_style="bold cyan"
    )
    table.add_column("Isl", justify="right")
    table.add_column("Gen", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Best", justify="right")
    table.add_column("Mean", justify="right")
    table.add_column("Std", justify="right")
    table.add_column("Diversity", justify="right")
    table.add_column("Best trend", justify="left", no_wrap=True)
    table.add_column("Div trend", justify="left", no_wrap=True)

    floor_warn = 1e-6 * _DIVERSITY_WARN_RATIO

    for idx in sorted(islands_data.keys()):
        rows = islands_data[idx]
        if not rows:
            continue
        last = rows[-1]
        best_series = [float(r.get("best_score", float("nan"))) for r in rows]
        div_series = [float(r.get("diversity_l2", 0.0)) for r in rows]
        best = float(last.get("best_score", float("nan")))
        mean = float(last.get("mean_score", float("nan")))
        std = float(last.get("std_score", float("nan")))
        div = float(last.get("diversity_l2", float("nan")))
        div_warning = div < floor_warn
        div_style = "red" if div_warning else "green"
        table.add_row(
            str(idx),
            str(last.get("generation", "?")),
            str(last.get("n_individuals", "?")),
            f"{best:.4f}",
            f"{mean:.4f}",
            f"{std:.4f}",
            f"[{div_style}]{div:.4e}[/{div_style}]",
            _sparkline(best_series),
            _sparkline(div_series),
        )
    if summary is not None:
        table.caption = (
            f"problem={summary.get('problem', '?')} "
            f"effective_pop={summary.get('effective_pop', '?')} "
            f"global_best={summary.get('global_best_score', float('nan')):.4f} "
            f"elapsed={summary.get('elapsed_seconds', 0.0):.1f}s "
            f"migrations={summary.get('n_migration_events', 0)}"
        )
    return table


def _build_migration_panel(migrations: list[dict[str, Any]], limit: int = 10):
    if not migrations:
        return Panel(
            "(no migrations recorded yet)",
            title="Migration log",
            border_style="dim",
        )
    last = migrations[-limit:]
    lines = []
    for mig in last:
        sizes = ",".join(str(s) for s in mig.get("island_sizes", []))
        lines.append(
            f"gen={mig.get('wall_gen', '?'):>3} "
            f"migrants={mig.get('total_migrants', 0):>3} "
            f"affected={mig.get('islands_affected', 0):>2} "
            f"sizes=[{sizes}]"
        )
    return Panel(
        "\n".join(lines),
        title=f"Migration log (last {len(last)} / total {len(migrations)})",
        border_style="cyan",
    )


_STATUS_STYLES = {
    "running": "bold yellow",
    "completed": "bold green",
    "idle": "dim",
}


def _build_progress_panel(progress: dict[str, Any]):
    status = progress["status"]
    style = _STATUS_STYLES.get(status, "white")
    bar = _ascii_progress_bar(progress["progress_ratio"])
    pct = progress["progress_ratio"] * 100.0
    eta = progress["eta_seconds"]
    eta_str = f"ETA {_format_duration(eta)}" if eta is not None else "ETA --"
    elapsed_str = _format_duration(progress["elapsed_seconds"])
    line1 = (
        f"[{style}]{status.upper():>9}[/{style}]  "
        f"Generation [bold]{progress['current_gen']}[/bold]"
        f" / {progress['max_gen']}  "
        f"[cyan]{bar}[/cyan] {pct:5.1f}%"
    )
    line2 = f"elapsed {elapsed_str}  |  {eta_str}"
    return Panel(
        f"{line1}\n{line2}",
        title="Evolution Progress",
        border_style=style if status != "idle" else "dim",
    )


def _render_rich(out_dir: Path) -> Layout:
    islands_data = _load_island_jsonl(out_dir)
    migrations = _load_migrations(out_dir)
    summary = _load_summary(out_dir)
    manifest = _load_manifest(out_dir)
    progress = _compute_progress(islands_data, manifest, summary)
    layout = Layout()
    layout.split_column(
        Layout(_build_progress_panel(progress), name="progress", size=5),
        Layout(_build_island_table(islands_data, summary), name="middle"),
        Layout(_build_migration_panel(migrations), name="bottom", size=12),
    )
    return layout


def _render_plain(out_dir: Path) -> str:
    islands_data = _load_island_jsonl(out_dir)
    migrations = _load_migrations(out_dir)
    summary = _load_summary(out_dir)
    parts: list[str] = []
    parts.append("=== Island Portfolio ===")
    floor_warn = 1e-6 * _DIVERSITY_WARN_RATIO
    for idx in sorted(islands_data.keys()):
        rows = islands_data[idx]
        if not rows:
            continue
        last = rows[-1]
        best_series = [float(r.get("best_score", float("nan"))) for r in rows]
        div_now = float(last.get("diversity_l2", float("nan")))
        warn = "!" if div_now < floor_warn else " "
        parts.append(
            f"{warn} island {idx:>2}: gen={last.get('generation', '?'):>3} "
            f"size={last.get('n_individuals', '?'):>3} "
            f"best={float(last.get('best_score', float('nan'))):.4f} "
            f"mean={float(last.get('mean_score', float('nan'))):.4f} "
            f"diversity={div_now:.4e} "
            f"trend={_sparkline(best_series)}"
        )
    if summary:
        parts.append(
            f"--- problem={summary.get('problem')} "
            f"effective_pop={summary.get('effective_pop')} "
            f"global_best={summary.get('global_best_score', float('nan')):.4f} "
            f"elapsed={summary.get('elapsed_seconds', 0):.1f}s "
            f"n_migrations={summary.get('n_migration_events', 0)}"
        )
    if migrations:
        parts.append(f"--- migrations recorded: {len(migrations)} (last 5):")
        for mig in migrations[-5:]:
            parts.append(
                f"  gen={mig.get('wall_gen')} "
                f"migrants={mig.get('total_migrants')} "
                f"sizes={mig.get('island_sizes')}"
            )
    return "\n".join(parts)


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir", type=Path)
    parser.add_argument(
        "--watch",
        type=float,
        default=0.0,
        help="seconds between refreshes (0 = one-shot, default)",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="force plain text output (no rich)",
    )
    args = parser.parse_args()

    if not args.out_dir.exists():
        print(f"out_dir not found: {args.out_dir}", file=sys.stderr)
        return 1

    use_rich = _HAS_RICH and not args.plain

    if not use_rich or args.watch <= 0:
        if use_rich:
            console = Console()
            console.print(_render_rich(args.out_dir))
        else:
            print(_render_plain(args.out_dir))
        return 0

    console = Console()
    try:
        with Live(
            _render_rich(args.out_dir),
            console=console,
            refresh_per_second=1,
        ) as live:
            while True:
                time.sleep(args.watch)
                live.update(_render_rich(args.out_dir))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
