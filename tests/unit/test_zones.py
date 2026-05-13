"""SEC-01 Quarantined Memory Zone tests."""

from __future__ import annotations

import pytest

from llive.memory.provenance import Provenance
from llive.memory.structural import StructuralMemory
from llive.security.zones import (
    QuarantinedMemoryView,
    ZoneAccessDenied,
    ZonePolicy,
    clear_zones,
    get_zone,
    register_zone,
)


@pytest.fixture(autouse=True)
def _clear_zones_before_after():
    clear_zones()
    yield
    clear_zones()


@pytest.fixture
def sm(tmp_path):
    storage = tmp_path / "kuzu"
    s = StructuralMemory(db_path=storage)
    yield s
    s.close()


def _prov(signed_by: str = "") -> Provenance:
    return Provenance(source_type="test", source_id="t", signed_by=signed_by)


def test_zone_policy_can_read_self():
    p = ZonePolicy(zone="public")
    assert p.can_read("public")
    assert not p.can_read("private")


def test_wildcard_allow_reads():
    p = ZonePolicy(zone="public", allowed_reads={"*"})
    assert p.can_read("anything")


def test_allowed_reads_explicit():
    p = ZonePolicy(zone="public", allowed_reads={"shared"})
    assert p.can_read("shared")
    assert not p.can_read("secret")


def test_signature_required_blocks_unsigned():
    p = ZonePolicy(zone="trusted", allowed_reads={"shared"}, signature_required=True)
    assert not p.can_read("shared")
    assert p.can_read("shared", signed_by="alice")


def test_can_write_default_self_only():
    p = ZonePolicy(zone="public")
    assert p.can_write("public")
    assert not p.can_write("private")


def test_can_write_wildcard():
    p = ZonePolicy(zone="admin", allowed_writes={"*"})
    assert p.can_write("anywhere")


def test_register_and_lookup_zone():
    p = ZonePolicy(zone="a")
    register_zone(p)
    assert get_zone("a") is p


def test_quarantined_view_blocks_cross_zone_write(sm):
    register_zone(ZonePolicy(zone="public"))
    view = QuarantinedMemoryView(sm, viewer_zone="public")
    with pytest.raises(ZoneAccessDenied):
        view.add_node("concept", {"k": "v"}, zone="private", provenance=_prov())


def test_quarantined_view_allows_same_zone_write(sm):
    register_zone(ZonePolicy(zone="public"))
    view = QuarantinedMemoryView(sm, viewer_zone="public")
    nid = view.add_node("concept", {"k": "v"}, zone="public", provenance=_prov())
    assert isinstance(nid, str)


def test_quarantined_view_blocks_cross_zone_read(sm):
    register_zone(ZonePolicy(zone="public"))
    register_zone(ZonePolicy(zone="private", allowed_writes={"*"}))
    private_view = QuarantinedMemoryView(sm, viewer_zone="private")
    private_view.add_node("concept", {}, zone="public", provenance=_prov())
    private_view.add_node("concept", {}, zone="private", provenance=_prov())
    public_view = QuarantinedMemoryView(sm, viewer_zone="public")
    listed = public_view.list_nodes()
    zones = {n.zone for n in listed}
    assert "private" not in zones


def test_signature_required_lets_signed_through(sm):
    register_zone(
        ZonePolicy(zone="trusted", allowed_reads={"sensor"}, signature_required=True)
    )
    register_zone(ZonePolicy(zone="sensor", allowed_writes={"*"}))
    sensor_view = QuarantinedMemoryView(sm, viewer_zone="sensor")
    sensor_view.add_node(
        "concept", {}, zone="sensor", provenance=_prov(signed_by="alice"), node_id="signed"
    )
    sensor_view.add_node(
        "concept", {}, zone="sensor", provenance=_prov(), node_id="unsigned"
    )
    trusted_view = QuarantinedMemoryView(sm, viewer_zone="trusted")
    listed = trusted_view.list_nodes()
    ids = {n.id for n in listed}
    assert "signed" in ids
    assert "unsigned" not in ids


def test_unregistered_viewer_defaults_to_wildcard(sm):
    view = QuarantinedMemoryView(sm, viewer_zone="undeclared")
    assert view.policy.can_read("any")
    assert view.policy.can_write("any")


def test_get_node_returns_none_when_missing(sm):
    register_zone(ZonePolicy(zone="public", allowed_reads={"*"}))
    view = QuarantinedMemoryView(sm, viewer_zone="public")
    assert view.get_node("ghost") is None


def test_get_node_respects_policy(sm):
    register_zone(ZonePolicy(zone="public"))
    register_zone(ZonePolicy(zone="private", allowed_writes={"*"}))
    private_view = QuarantinedMemoryView(sm, viewer_zone="private")
    private_view.add_node(
        "concept", {}, zone="private", provenance=_prov(), node_id="hidden"
    )
    public_view = QuarantinedMemoryView(sm, viewer_zone="public")
    with pytest.raises(ZoneAccessDenied):
        public_view.get_node("hidden")


def test_filter_helper(sm):
    register_zone(ZonePolicy(zone="public", allowed_reads={"shared"}))
    register_zone(ZonePolicy(zone="shared", allowed_writes={"*"}))
    register_zone(ZonePolicy(zone="secret", allowed_writes={"*"}))
    shared_view = QuarantinedMemoryView(sm, viewer_zone="shared")
    shared_view.add_node("concept", {}, zone="shared", provenance=_prov(), node_id="s1")
    shared_view.add_node("concept", {}, zone="secret", provenance=_prov(), node_id="x1")
    public = QuarantinedMemoryView(sm, viewer_zone="public")
    all_nodes = sm.list_nodes()
    filtered = public.filter(all_nodes)
    assert {n.id for n in filtered} == {"s1"}
