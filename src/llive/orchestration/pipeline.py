"""Inference pipeline glue (L2): prompt → router → container → trace.

Phase 1 では HFAdapter は optional。`adapter=None` 渡しまたは torch 未インストール
時は ``"[mock-output]"`` を生成し、trace + memory hook はそのまま動作する。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from llive.container.executor import BlockContainerExecutor, BlockState
from llive.container.subblocks import builtin as _builtin
from llive.core.adapter import BaseModelAdapter, GenerationResult
from llive.observability.trace import RouteTrace, trace_from_state, write_trace
from llive.router.engine import RouterEngine
from llive.schema.validator import validate_container_spec


@dataclass
class PipelineResult:
    request_id: str
    container: str
    text: str
    state: BlockState
    trace: RouteTrace
    generation: GenerationResult | None
    extras: dict[str, Any]


def _default_containers_dir() -> Path:
    """Prefer the packaged `_specs/containers/` if present, else dev tree."""
    here = Path(__file__).resolve()
    packaged = here.parent.parent / "_specs" / "containers"
    if packaged.is_dir():
        return packaged
    return Path("specs/containers")


def _default_router_spec() -> Path:
    here = Path(__file__).resolve()
    packaged = here.parent.parent / "_specs" / "routes" / "default.yaml"
    if packaged.exists():
        return packaged
    return Path("specs/routes/default.yaml")


class Pipeline:
    """Bind a router, a container directory, and (optionally) an HFAdapter."""

    def __init__(
        self,
        *,
        containers_dir: Path | str | None = None,
        router_spec: Path | str | None = None,
        adapter: BaseModelAdapter | None = None,
        backends: _builtin.MemoryBackends | None = None,
        write_trace_to_disk: bool = True,
    ) -> None:
        self.containers_dir = Path(containers_dir) if containers_dir is not None else _default_containers_dir()
        self.router = RouterEngine(router_spec if router_spec is not None else _default_router_spec())
        self.adapter = adapter
        self.write_trace_to_disk = bool(write_trace_to_disk)
        if backends is not None:
            _builtin.set_memory_backends(backends)
        self._executors: dict[str, BlockContainerExecutor] = {}

    def _get_executor(self, container_id: str) -> BlockContainerExecutor:
        if container_id not in self._executors:
            path = self.containers_dir / f"{container_id}.yaml"
            if not path.exists():
                raise FileNotFoundError(f"container not found: {path}")
            spec = validate_container_spec(path)
            self._executors[container_id] = BlockContainerExecutor(spec)
        return self._executors[container_id]

    def run(
        self,
        prompt: str,
        *,
        max_new_tokens: int = 32,
        task_tag: str | None = None,
        return_hidden_states: bool = False,
    ) -> PipelineResult:
        request_id = uuid.uuid4().hex
        decision = self.router.select(prompt, request_id=request_id)
        return self._run_inner(
            prompt=prompt,
            request_id=request_id,
            container=decision.container,
            extras={"router_explanation": decision.explanation.model_dump()},
            max_new_tokens=max_new_tokens,
            task_tag=task_tag,
            return_hidden_states=return_hidden_states,
        )

    def run_with_container(
        self,
        prompt: str,
        container_id: str,
        *,
        max_new_tokens: int = 32,
        task_tag: str | None = None,
        return_hidden_states: bool = False,
    ) -> PipelineResult:
        """Bypass the router; force a specific container (CONC-03 BranchExplorer)."""
        request_id = uuid.uuid4().hex
        return self._run_inner(
            prompt=prompt,
            request_id=request_id,
            container=container_id,
            extras={"router_bypass": True},
            max_new_tokens=max_new_tokens,
            task_tag=task_tag,
            return_hidden_states=return_hidden_states,
        )

    def _run_inner(
        self,
        *,
        prompt: str,
        request_id: str,
        container: str,
        extras: dict,
        max_new_tokens: int,
        task_tag: str | None,
        return_hidden_states: bool,
    ) -> PipelineResult:
        executor = self._get_executor(container)
        state = BlockState(prompt=prompt, meta={"request_id": request_id, "task_tag": task_tag})

        generation: GenerationResult | None = None
        if self.adapter is not None:
            try:
                generation = self.adapter.generate(
                    prompt, max_new_tokens=max_new_tokens, return_hidden_states=return_hidden_states
                )
                state.output = generation.text
                if generation.hidden_states is not None:
                    state.hidden = generation.hidden_states
            except ModuleNotFoundError:
                state.output = f"[mock-output: torch missing; prompt={prompt[:40]}]"
        else:
            state.output = f"[mock-output: prompt={prompt[:40]}]"

        state = executor.execute(state)
        trace = trace_from_state(
            decision.container,
            state,
            latency_ms=sum(t.duration_ms for t in state.trace),
            subblock_count=len(state.trace),
        )
        trace.request_id = request_id
        if self.write_trace_to_disk:
            write_trace(trace)

        return PipelineResult(
            request_id=request_id,
            container=decision.container,
            text=state.output or "",
            state=state,
            trace=trace,
            generation=generation,
            extras={"router_explanation": decision.explanation.model_dump()},
        )


def load_template(template_path: Path | str) -> dict[str, Any]:
    """Read a model template (e.g. specs/templates/qwen2_5_0_5b.yaml)."""
    path = Path(template_path)
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
