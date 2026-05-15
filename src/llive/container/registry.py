# SPDX-License-Identifier: Apache-2.0
"""SubBlock plugin registry (BC-02)."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SubBlock(Protocol):
    """Protocol every sub-block instance must satisfy."""

    name: str
    type: str

    def __call__(self, state: BlockState) -> BlockState: ...  # noqa: F821 (forward ref)


SubBlockFactory = Callable[[dict[str, Any]], SubBlock]


class SubBlockRegistry:
    """Thread-safe registry of sub-block factories.

    Phase 1 では built-in 5 種を `register_builtins(registry)` で登録する。
    Phase 2+ で entry-points (`llive.subblocks` group) discovery を追加。
    """

    def __init__(self) -> None:
        self._factories: dict[str, SubBlockFactory] = {}
        self._lock = threading.Lock()

    def register(self, type_name: str, factory: SubBlockFactory) -> None:
        with self._lock:
            if type_name in self._factories:
                raise ValueError(f"sub-block type already registered: {type_name!r}")
            self._factories[type_name] = factory

    def create(self, type_name: str, config: dict[str, Any] | None = None) -> SubBlock:
        with self._lock:
            try:
                factory = self._factories[type_name]
            except KeyError as exc:
                raise KeyError(f"unknown sub-block type: {type_name!r}") from exc
        return factory(config or {})

    def names(self) -> Iterable[str]:
        with self._lock:
            return tuple(self._factories.keys())

    def has(self, type_name: str) -> bool:
        with self._lock:
            return type_name in self._factories


_DEFAULT_REGISTRY: SubBlockRegistry | None = None


def get_registry() -> SubBlockRegistry:
    """Return process-wide default registry (lazy-loaded with built-ins)."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry = SubBlockRegistry()
        from llive.container.subblocks.builtin import register_builtins

        register_builtins(registry)
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY
