"""Adapter / lora_switch sub-blocks (BC-04).

Phase 2 implementation is a *thin metadata wrapper*: the sub-block records
which adapter it would activate but does not actually merge LoRA weights
unless ``peft`` is installed (``[torch]`` extra). This mirrors how the
Phase 1 ``pre_norm`` / ``causal_attention`` markers behave — they exist as
container slots and emit trace events, while the actual numerical work is
done by the underlying HF model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from llive.container.registry import SubBlockRegistry
from llive.memory.parameter import AdapterStore


@dataclass
class _AdapterContext:
    """Lazy singleton for the AdapterStore so sub-blocks can share one."""

    store: AdapterStore | None = None

    def ensure(self) -> AdapterStore:
        if self.store is None:
            self.store = AdapterStore()
        return self.store


_CTX = _AdapterContext()


def set_adapter_store(store: AdapterStore | None) -> None:
    """Override the process-wide AdapterStore (tests, orchestration)."""
    _CTX.store = store


def get_adapter_store() -> AdapterStore:
    return _CTX.ensure()


@dataclass
class AdapterBlock:
    name: str = "adapter"
    type: str = "adapter"
    adapter_id: str | None = None
    target_layer: str = "current"
    fallback_to_base: bool = True

    @classmethod
    def factory(cls, config: dict[str, Any]):
        return cls(
            adapter_id=config.get("adapter_id"),
            target_layer=str(config.get("target_layer", "current")),
            fallback_to_base=bool(config.get("fallback_to_base", True)),
        )

    def __call__(self, state):
        active = "base"
        if self.adapter_id is not None:
            try:
                store = get_adapter_store()
                rec = store.get(self.adapter_id)
                if rec is None:
                    if not self.fallback_to_base:
                        raise KeyError(f"adapter {self.adapter_id!r} not registered")
                else:
                    if store.verify_sha256(self.adapter_id):
                        store.activate(self.adapter_id)
                        active = self.adapter_id
                    elif not self.fallback_to_base:
                        raise RuntimeError(f"adapter {self.adapter_id!r} integrity check failed")
            except Exception:
                if not self.fallback_to_base:
                    raise
        state.meta.setdefault("adapter_trace", []).append({"name": self.name, "active": active, "target_layer": self.target_layer})
        return state


@dataclass
class LoraSwitchBlock:
    name: str = "lora_switch"
    type: str = "lora_switch"
    adapters: tuple[str, ...] = ()
    selector: str = "task_conditioned"  # "task_conditioned" | "round_robin"
    fallback_to_base: bool = True
    _counter: int = field(default=0, init=False, repr=False)

    @classmethod
    def factory(cls, config: dict[str, Any]):
        adapters_cfg = config.get("adapters") or []
        return cls(
            adapters=tuple(str(a) for a in adapters_cfg),
            selector=str(config.get("selector", "task_conditioned")),
            fallback_to_base=bool(config.get("fallback_to_base", True)),
        )

    def _choose(self, state) -> str | None:
        if not self.adapters:
            return None
        if self.selector == "round_robin":
            choice = self.adapters[self._counter % len(self.adapters)]
            self._counter += 1
            return choice
        # task_conditioned: match by adapter tag intersection
        task_tag = state.meta.get("task_tag")
        if task_tag is None:
            return self.adapters[0]
        try:
            store = get_adapter_store()
        except Exception:
            return self.adapters[0]
        # look for adapter whose tags include task_tag
        for ad_id in self.adapters:
            rec = store.get(ad_id)
            if rec is not None and task_tag in rec.profile.tags:
                return ad_id
        return self.adapters[0]

    def __call__(self, state):
        chosen = self._choose(state)
        active = "base"
        if chosen is not None:
            try:
                store = get_adapter_store()
                rec = store.get(chosen)
                if rec is None and not self.fallback_to_base:
                    raise KeyError(f"adapter {chosen!r} not registered")
                if rec is not None:
                    if store.verify_sha256(chosen):
                        store.activate(chosen)
                        active = chosen
                    elif not self.fallback_to_base:
                        raise RuntimeError(f"adapter {chosen!r} integrity check failed")
            except Exception:
                if not self.fallback_to_base:
                    raise
        state.meta.setdefault("lora_switch_trace", []).append({"name": self.name, "active": active, "selector": self.selector})
        return state


def register_phase2_subblocks(registry: SubBlockRegistry) -> None:
    if not registry.has("adapter"):
        registry.register("adapter", AdapterBlock.factory)
    if not registry.has("lora_switch"):
        registry.register("lora_switch", LoraSwitchBlock.factory)


# Auto-register on import so containers can use these immediately.
# This import lives at the bottom because we need the factory classes defined
# above to be visible when register_phase2_subblocks runs.
from llive.container.registry import get_registry as _get_registry  # noqa: E402

register_phase2_subblocks(_get_registry())
