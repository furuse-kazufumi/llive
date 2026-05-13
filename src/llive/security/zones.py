"""Quarantined Memory Zone (SEC-01 / FR-17).

Each :class:`MemoryNode` already carries a ``zone`` field. SEC-01 makes that
field load-bearing by attaching a :class:`ZonePolicy` to the runtime: every
read or write through a :class:`QuarantinedMemoryView` is checked against
the policy. Cross-zone reads require an explicit allow-list entry.

A small declarative DSL is exposed:

* :func:`register_zone` defines a zone and its outbound allow-list.
* :class:`QuarantinedMemoryView` wraps a :class:`StructuralMemory` and
  enforces the policy on ``add_node`` / ``query_neighbors`` /
  ``list_nodes``.
* :class:`ZoneAccessDenied` is raised on policy violation.

The view does not mutate StructuralMemory's public API; it is *additive*
so existing callers keep working when no zones are registered.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from llive.memory.provenance import Provenance

if TYPE_CHECKING:
    from llive.memory.structural import GraphNode, StructuralMemory


class ZoneAccessDenied(PermissionError):
    """Raised when a cross-zone access violates the active policy."""


@dataclass
class ZonePolicy:
    """A single zone's read/write rules.

    * ``zone``: the zone slug this policy applies to.
    * ``allowed_reads``: zones whose nodes this zone may read.
        ``"*"`` permits all (back-compat for non-quarantined zones).
    * ``allowed_writes``: zones this zone may write *into*. Defaults to
        ``{zone}`` (writes only into self).
    * ``signature_required``: when True, cross-zone reads require a non-empty
        ``provenance.signed_by`` on the source node.
    """

    zone: str
    allowed_reads: set[str] = field(default_factory=set)
    allowed_writes: set[str] = field(default_factory=set)
    signature_required: bool = False

    def can_read(self, other_zone: str, *, signed_by: str | None = None) -> bool:
        if other_zone == self.zone:
            return True
        if "*" in self.allowed_reads:
            return True
        if other_zone not in self.allowed_reads:
            return False
        if self.signature_required and not signed_by:
            return False
        return True

    def can_write(self, target_zone: str) -> bool:
        if not self.allowed_writes:
            return target_zone == self.zone
        if "*" in self.allowed_writes:
            return True
        return target_zone in self.allowed_writes


_ZONE_REGISTRY: dict[str, ZonePolicy] = {}
_REGISTRY_LOCK = threading.Lock()


def register_zone(policy: ZonePolicy) -> ZonePolicy:
    """Register or update a global zone policy."""
    with _REGISTRY_LOCK:
        _ZONE_REGISTRY[policy.zone] = policy
    return policy


def get_zone(zone: str) -> ZonePolicy | None:
    with _REGISTRY_LOCK:
        return _ZONE_REGISTRY.get(zone)


def clear_zones() -> None:
    """Test helper: drop every registered zone."""
    with _REGISTRY_LOCK:
        _ZONE_REGISTRY.clear()


class QuarantinedMemoryView:
    """Wraps a :class:`StructuralMemory` and enforces a :class:`ZonePolicy`."""

    def __init__(self, structural: StructuralMemory, viewer_zone: str) -> None:
        self.structural = structural
        self.viewer_zone = viewer_zone
        policy = get_zone(viewer_zone)
        if policy is None:
            policy = ZonePolicy(zone=viewer_zone, allowed_reads={"*"}, allowed_writes={"*"})
        self.policy = policy

    # -- writes ------------------------------------------------------------

    def add_node(self, node: MemoryNode) -> str:
        target = getattr(node, "zone", "") or ""
        if not self.policy.can_write(target):
            raise ZoneAccessDenied(
                f"zone {self.viewer_zone!r} cannot write into {target!r}"
            )
        return self.structural.add_node(node)

    # -- reads -------------------------------------------------------------

    def get_node(self, node_id: str) -> MemoryNode | None:
        result = self._get_node_via_neighbors(node_id)
        if result is None:
            return None
        node = result
        node_zone = getattr(node, "zone", "") or ""
        signed_by = None
        if node.provenance is not None:
            signed_by = getattr(node.provenance, "signed_by", "") or None
        if not self.policy.can_read(node_zone, signed_by=signed_by):
            raise ZoneAccessDenied(
                f"zone {self.viewer_zone!r} cannot read node in zone {node_zone!r}"
            )
        return node

    def list_nodes(self, *, memory_type: str | None = None) -> list[MemoryNode]:
        nodes = self.structural.list_nodes(memory_type=memory_type)
        return [n for n in nodes if self._readable(n)]

    def query_neighbors(self, node_id: str, *, rel_type: str | None = None) -> list[MemoryNode]:
        nodes = self.structural.query_neighbors(node_id, rel_type=rel_type)
        return [n for n in nodes if self._readable(n)]

    # -- internals ---------------------------------------------------------

    def _readable(self, node: MemoryNode) -> bool:
        node_zone = getattr(node, "zone", "") or ""
        signed_by = None
        if node.provenance is not None:
            signed_by = getattr(node.provenance, "signed_by", "") or None
        return self.policy.can_read(node_zone, signed_by=signed_by)

    def _get_node_via_neighbors(self, node_id: str) -> MemoryNode | None:
        # StructuralMemory.list_nodes returns every node; scan for the one we need.
        # Phase 4 MVR — Phase 5 will route this through a Rust-side fast lookup.
        for node in self.structural.list_nodes():
            if getattr(node, "id", None) == node_id:
                return node
        return None

    def filter(self, nodes: Iterable[MemoryNode]) -> list[MemoryNode]:
        """Out-of-band helper: filter an already-fetched node list."""
        return [n for n in nodes if self._readable(n)]


__all__ = [
    "QuarantinedMemoryView",
    "ZoneAccessDenied",
    "ZonePolicy",
    "clear_zones",
    "get_zone",
    "register_zone",
]
