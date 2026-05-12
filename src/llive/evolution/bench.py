"""BenchHarness (EVO-01) — baseline vs candidate A/B evaluator.

Phase 1: lightweight, dependency-free evaluation using internal containers
+ a toy dataset of prompts. Metrics computed:

- ``mean_latency_ms``   (per prompt)
- ``p50_latency_ms`` / ``p95_latency_ms``
- ``memory_read_rate``  (avg memory read ops per prompt)
- ``memory_write_rate`` (avg memory writes per prompt)
- ``route_entropy``     (Shannon entropy over chosen containers)
- ``dead_subblock_rate`` (fraction of sub-blocks marked ``skipped_condition``)

実際の LLM 推論 (HFAdapter) を介さないため Phase 1 のスモークとして十分軽量。
Phase 2+ では lm-evaluation-harness 連携で perplexity / accuracy も計測する。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from llive.container.executor import BlockContainerExecutor, BlockState
from llive.container.subblocks import builtin as _builtin
from llive.evolution.change_op import apply_diff
from llive.observability.metrics import compute_route_entropy
from llive.router.engine import RouterEngine
from llive.schema.models import CandidateDiff, ContainerSpec
from llive.schema.validator import validate_candidate_diff, validate_container_spec


@dataclass
class ArmResult:
    name: str
    container_id: str
    n_prompts: int
    mean_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    memory_read_rate: float
    memory_write_rate: float
    route_entropy: float
    dead_subblock_rate: float
    routes_taken: dict[str, int] = field(default_factory=dict)


@dataclass
class BenchResult:
    timestamp: datetime
    baseline_container: str
    candidate_id: str
    dataset: str
    n_prompts: int
    baseline: ArmResult
    candidate: ArmResult

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_v) - 1)
    if f == c:
        return float(sorted_v[f])
    return float(sorted_v[f] + (sorted_v[c] - sorted_v[f]) * (k - f))


def _load_dataset(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"dataset not found: {path}")
    if path.is_file() and path.suffix == ".txt":
        return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if path.is_dir():
        prompts: list[str] = []
        for sub in sorted(path.glob("*.txt")):
            prompts.extend(
                ln.strip() for ln in sub.read_text(encoding="utf-8").splitlines() if ln.strip()
            )
        return prompts
    if path.suffix in (".jsonl",):
        prompts = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            prompts.append(obj["prompt"] if isinstance(obj, dict) else str(obj))
        return prompts
    raise ValueError(f"unsupported dataset format: {path}")


def _default_out_dir() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "bench"


class BenchHarness:
    """Run a baseline container vs. a candidate diff on a prompt dataset."""

    def __init__(
        self,
        containers_dir: Path | str = "specs/containers",
        router_spec: Path | str = "specs/routes/default.yaml",
    ) -> None:
        self.containers_dir = Path(containers_dir)
        self.router = RouterEngine(router_spec)

    # -- helpers -----------------------------------------------------------

    def _load_container(self, container_id: str) -> ContainerSpec:
        path = self.containers_dir / f"{container_id}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"container spec not found: {path}")
        return validate_container_spec(path)

    def _load_candidate(self, path: Path) -> CandidateDiff:
        return validate_candidate_diff(path)

    # -- main api ----------------------------------------------------------

    def run(
        self,
        *,
        baseline_container: str,
        candidate_path: Path | str,
        dataset_path: Path | str,
        out_dir: Path | str | None = None,
    ) -> BenchResult:
        baseline_spec = self._load_container(baseline_container)
        candidate_diff = self._load_candidate(Path(candidate_path))
        candidate_spec, _ops = apply_diff(baseline_spec, candidate_diff)

        prompts = _load_dataset(Path(dataset_path))
        if not prompts:
            raise ValueError("dataset is empty")

        baseline_arm = self._run_arm("baseline", baseline_spec, prompts)
        # reset memory backends between arms so candidate starts from a clean slate
        _builtin.set_memory_backends(None)
        candidate_arm = self._run_arm("candidate", candidate_spec, prompts)

        result = BenchResult(
            timestamp=datetime.now(timezone.utc),
            baseline_container=baseline_container,
            candidate_id=candidate_diff.candidate_id,
            dataset=str(dataset_path),
            n_prompts=len(prompts),
            baseline=baseline_arm,
            candidate=candidate_arm,
        )

        target_dir = Path(out_dir) if out_dir else _default_out_dir() / result.timestamp.strftime(
            "%Y%m%dT%H%M%S"
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "results.json").write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        # also persist the candidate container for debuggability
        (target_dir / "candidate_container.yaml").write_text(
            yaml.safe_dump(candidate_spec.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
        result.out_dir = target_dir  # type: ignore[attr-defined]
        return result

    def _run_arm(self, name: str, spec: ContainerSpec, prompts: list[str]) -> ArmResult:
        # build executor for the arm-specific container
        executor = BlockContainerExecutor(spec)
        latencies_ms: list[float] = []
        memory_reads = 0
        memory_writes = 0
        skipped_steps = 0
        total_steps = 0
        routes_taken: dict[str, int] = {}

        for prompt in prompts:
            start = time.perf_counter()
            decision = self.router.select(prompt)
            # in Phase 1 the bench focuses on a single container per arm;
            # decision is logged but does not switch the executor.
            routes_taken[decision.container] = routes_taken.get(decision.container, 0) + 1

            state = BlockState(prompt=prompt, output=f"[mock-output for: {prompt[:32]}]")
            state = executor.execute(state)
            latencies_ms.append((time.perf_counter() - start) * 1000.0)

            total_steps += len(state.trace)
            skipped_steps += sum(1 for t in state.trace if t.note == "skipped_condition")
            for access in state.memory_accesses:
                if access.get("op") == "read":
                    memory_reads += 1
                if access.get("op") == "write":
                    memory_writes += 1

        n = len(prompts)
        return ArmResult(
            name=name,
            container_id=spec.container_id,
            n_prompts=n,
            mean_latency_ms=sum(latencies_ms) / n,
            p50_latency_ms=_percentile(latencies_ms, 50),
            p95_latency_ms=_percentile(latencies_ms, 95),
            memory_read_rate=memory_reads / n,
            memory_write_rate=memory_writes / n,
            route_entropy=compute_route_entropy(routes_taken),
            dead_subblock_rate=skipped_steps / max(1, total_steps),
            routes_taken=routes_taken,
        )
