"""Scenario base class + CLI runner.

Each scenario implements ``Scenario.run(ctx)`` and is registered in the
ordered list returned by :func:`list_scenarios`. The CLI runner threads
a fresh ``ScenarioContext`` (with its own ``tmp_path``) through each
scenario so they cannot accidentally see each other's state.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from llive.demo.i18n import current_lang


@contextlib.contextmanager
def _scoped_lang(lang: str) -> Iterator[None]:
    """Temporarily set ``LLIVE_DEMO_LANG`` for the duration of a scenario."""
    prev = os.environ.get("LLIVE_DEMO_LANG")
    os.environ["LLIVE_DEMO_LANG"] = lang
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("LLIVE_DEMO_LANG", None)
        else:
            os.environ["LLIVE_DEMO_LANG"] = prev

# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class ScenarioContext:
    """Per-scenario runtime context.

    Each scenario gets a fresh ``tmp_path`` so they cannot leak state into
    each other. The runner cleans it up after the scenario completes (unless
    ``keep_artifacts=True``).
    """

    tmp_path: Path
    lang: str = "ja"
    quiet: bool = False
    started_at: float = field(default_factory=time.monotonic)

    # Convenience writers --------------------------------------------------

    def say(self, text: str) -> None:
        if not self.quiet:
            print(text, flush=True)

    def step(self, n: int, total: int, text: str) -> None:
        if not self.quiet:
            print(f"\n  [{n}/{total}] {text}", flush=True)

    def hr(self) -> None:
        if not self.quiet:
            print("  " + "-" * 64, flush=True)


# ---------------------------------------------------------------------------
# Scenario base
# ---------------------------------------------------------------------------


class Scenario:
    """Base for demo scenarios.

    Subclasses override ``id``, ``title`` (per-language), and ``run(ctx)``.
    """

    id: str = "base"
    titles: ClassVar[dict[str, str]] = {"ja": "scenario", "en": "scenario"}

    def title(self, lang: str | None = None) -> str:
        lang = lang or current_lang()
        return self.titles.get(lang) or self.titles.get("ja", self.id)

    def run(self, ctx: ScenarioContext) -> dict[str, object]:  # pragma: no cover - interface
        """Execute the scenario. Returns a JSON-serialisable summary."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def list_scenarios() -> list[Scenario]:
    """Return all registered demo scenarios in display order."""
    # Local imports so the registry is the single source of truth and so
    # importing :mod:`llive.demo` does not cascade into every scenario.
    from llive.demo.scenario_1_quick_tour import QuickTourScenario
    from llive.demo.scenario_2_append_roundtrip import AppendRoundTripScenario
    from llive.demo.scenario_3_code_review import CodeReviewScenario
    from llive.demo.scenario_4_mcp_roundtrip import MCPRoundTripScenario
    from llive.demo.scenario_5_openai_http import OpenAIHTTPScenario

    return [
        QuickTourScenario(),
        AppendRoundTripScenario(),
        CodeReviewScenario(),
        MCPRoundTripScenario(),
        OpenAIHTTPScenario(),
    ]


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def _make_context(*, lang: str, quiet: bool) -> tuple[ScenarioContext, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="llive-demo-"))
    return ScenarioContext(tmp_path=tmp, lang=lang, quiet=quiet), tmp


def _cleanup(path: Path, keep: bool) -> None:
    if keep or not path.exists():
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def run_one(
    index_or_id: int | str,
    *,
    lang: str | None = None,
    quiet: bool = False,
    keep_artifacts: bool = False,
) -> dict[str, object]:
    """Run a single scenario by 1-based index or by ``id``."""
    scenarios = list_scenarios()
    chosen: Scenario | None = None
    if isinstance(index_or_id, int):
        if 1 <= index_or_id <= len(scenarios):
            chosen = scenarios[index_or_id - 1]
    else:
        for s in scenarios:
            if s.id == index_or_id:
                chosen = s
                break
    if chosen is None:
        raise SystemExit(
            f"unknown scenario: {index_or_id!r} (available: "
            f"{[(i + 1, s.id) for i, s in enumerate(scenarios)]})"
        )
    effective_lang = lang or current_lang()
    with _scoped_lang(effective_lang):
        ctx, tmp = _make_context(lang=effective_lang, quiet=quiet)
        try:
            if not quiet:
                print(f"\n==[ {chosen.id} :: {chosen.title(ctx.lang)} ]==", flush=True)
            summary = chosen.run(ctx)
            return {"id": chosen.id, "ok": True, "summary": summary}
        finally:
            _cleanup(tmp, keep_artifacts)


def run_all(
    *,
    lang: str | None = None,
    quiet: bool = False,
    keep_artifacts: bool = False,
) -> list[dict[str, object]]:
    """Run every registered scenario in order."""
    results: list[dict[str, object]] = []
    scenarios = list_scenarios()
    effective_lang = lang or current_lang()
    with _scoped_lang(effective_lang):
        for i, sc in enumerate(scenarios, start=1):
            ctx, tmp = _make_context(lang=effective_lang, quiet=quiet)
            if not quiet:
                print(f"\n==[ {i}/{len(scenarios)} {sc.id} :: {sc.title(ctx.lang)} ]==", flush=True)
            try:
                summary = sc.run(ctx)
                results.append({"id": sc.id, "ok": True, "summary": summary})
            except Exception as exc:  # demo は止めない: 失敗を記録して次へ
                results.append({"id": sc.id, "ok": False, "error": str(exc)})
                if not quiet:
                    print(f"  [!] scenario failed: {exc}", flush=True)
            finally:
                _cleanup(tmp, keep_artifacts)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="llive.demo",
        description="llive RAD knowledge-base demo scenarios.",
    )
    p.add_argument("--only", help="run a single scenario by 1-based index or id")
    p.add_argument("--list", action="store_true", help="list available scenarios and exit")
    p.add_argument("--lang", choices=["ja", "en"], help="narration language (default: $LLIVE_DEMO_LANG | ja)")
    p.add_argument("--quiet", action="store_true", help="suppress narration (summary only)")
    p.add_argument("--keep-artifacts", action="store_true", help="keep tmp dirs after each scenario")
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _build_parser().parse_args(argv)

    if args.list:
        for i, s in enumerate(list_scenarios(), start=1):
            print(f"  {i}. {s.id:30s} {s.title(args.lang or current_lang())}")
        return 0

    if args.only is not None:
        target: int | str
        try:
            target = int(args.only)
        except ValueError:
            target = args.only
        out = run_one(
            target,
            lang=args.lang,
            quiet=args.quiet,
            keep_artifacts=args.keep_artifacts,
        )
        return 0 if out.get("ok") else 1

    results = run_all(lang=args.lang, quiet=args.quiet, keep_artifacts=args.keep_artifacts)
    fails = [r for r in results if not r.get("ok")]
    if not args.quiet:
        print(f"\n=== summary: {len(results) - len(fails)}/{len(results)} ok ===", flush=True)
        for r in results:
            print(f"  {'OK ' if r.get('ok') else 'ERR'}  {r['id']}", flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
