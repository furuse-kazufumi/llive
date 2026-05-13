"""Concurrent pipeline + branch exploration (CONC-02, CONC-03).

Memory backends are already protected by per-instance locks (CONC-01), so the
public Pipeline API is safe to call from multiple threads. This module adds two
lightweight wrappers on top:

* :class:`ConcurrentPipeline` — fan out multiple *different* prompts across a
  ``ThreadPoolExecutor``. While the GIL means CPU-bound LLM inference is still
  effectively serial, memory I/O / router decisions / Wiki ingest run in
  parallel and the wrapper gives a clean ``submit`` / ``run_parallel`` API.

* :class:`BranchExplorer` — for a *single* prompt, run a list of container ids
  in parallel. Each branch reports its own ``PipelineResult`` and latency so
  callers can compare / aggregate (Phase 3 will feed this into FR-23 / EVO).

Phase 4 will tighten this with snapshot-based reads, write-contention metrics,
and cooperative cancellation (CONC-04〜08). For Phase 2 we only need the bones.
"""

from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from llive.orchestration.pipeline import Pipeline, PipelineResult


@dataclass
class BranchResult:
    container_id: str
    result: PipelineResult
    latency_ms: float


class ConcurrentPipeline:
    """Thin wrapper that fans out :class:`Pipeline.run` calls across a thread pool."""

    def __init__(self, pipeline: Pipeline, max_workers: int = 4) -> None:
        self.pipeline = pipeline
        self.max_workers = int(max_workers)
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._closed = False

    def __enter__(self) -> ConcurrentPipeline:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def submit(self, prompt: str, **kwargs: Any) -> Future[PipelineResult]:
        if self._closed:
            raise RuntimeError("ConcurrentPipeline is closed")
        return self._executor.submit(self.pipeline.run, prompt, **kwargs)

    def run_parallel(self, prompts: list[str], **kwargs: Any) -> list[PipelineResult]:
        if self._closed:
            raise RuntimeError("ConcurrentPipeline is closed")
        futures = [self.submit(p, **kwargs) for p in prompts]
        # preserve input order to keep determinism
        return [f.result() for f in futures]

    def close(self) -> None:
        if not self._closed:
            self._executor.shutdown(wait=True)
            self._closed = True


class BranchExplorer:
    """Execute the same prompt against multiple containers concurrently."""

    def __init__(
        self,
        pipeline: Pipeline,
        container_ids: list[str],
        max_workers: int = 4,
    ) -> None:
        if not container_ids:
            raise ValueError("container_ids must be non-empty")
        self.pipeline = pipeline
        self.container_ids = list(container_ids)
        self.max_workers = int(max_workers)
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._closed = False

    def __enter__(self) -> BranchExplorer:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def explore(self, prompt: str, **kwargs: Any) -> list[BranchResult]:
        if self._closed:
            raise RuntimeError("BranchExplorer is closed")
        futures: dict[Future[PipelineResult], tuple[str, float]] = {}
        for cid in self.container_ids:
            started = time.perf_counter()
            fut = self._executor.submit(self.pipeline.run_with_container, prompt, cid, **kwargs)
            futures[fut] = (cid, started)
        results: list[BranchResult] = []
        for fut in as_completed(futures):
            cid, started = futures[fut]
            elapsed = (time.perf_counter() - started) * 1000.0
            results.append(BranchResult(container_id=cid, result=fut.result(), latency_ms=elapsed))
        # stable order: match input container_ids order
        order = {cid: i for i, cid in enumerate(self.container_ids)}
        results.sort(key=lambda r: order[r.container_id])
        return results

    def close(self) -> None:
        if not self._closed:
            self._executor.shutdown(wait=True)
            self._closed = True
