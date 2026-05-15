# SPDX-License-Identifier: Apache-2.0
"""MEM-06: AdapterStore."""

from __future__ import annotations

import pytest

from llive.memory.parameter import AdapterProfile, AdapterStore


@pytest.fixture
def store(tmp_path):
    s = AdapterStore(data_dir=tmp_path / "params", index_path=tmp_path / "idx.duckdb")
    yield s
    s.close()


def _weight(tmp_path, name="w.safetensors", payload=b"AAAA" * 100):
    p = tmp_path / name
    p.write_bytes(payload)
    return p


def _profile(**kw):
    base = {
        "name": "test_lora",
        "base_model": "Qwen/Qwen2.5-0.5B",
        "format": "lora",
        "target_modules": ["q_proj", "v_proj"],
        "alpha": 16.0,
    }
    base.update(kw)
    return AdapterProfile(**base)


def test_register_and_list(store, tmp_path):
    w = _weight(tmp_path)
    p = store.register(w, _profile())
    records = store.list()
    assert len(records) == 1
    assert records[0].profile.id == p.id
    assert records[0].profile.sha256
    assert records[0].profile.adapter_size_mb > 0


def test_register_copies_into_store(store, tmp_path):
    w = _weight(tmp_path)
    p = store.register(w, _profile(name="lora_a"), copy_into_store=True)
    rec = store.get(p.id)
    assert rec is not None
    assert rec.weight_path.parent == store.data_dir
    assert rec.weight_path.exists()


def test_register_in_place(store, tmp_path):
    w = _weight(tmp_path, name="in_place.safetensors")
    p = store.register(w, _profile(name="in_place"), copy_into_store=False)
    rec = store.get(p.id)
    assert rec is not None
    assert rec.weight_path == w


def test_register_missing_weight(store, tmp_path):
    with pytest.raises(FileNotFoundError):
        store.register(tmp_path / "nope.safetensors", _profile())


def test_verify_sha256_pass(store, tmp_path):
    w = _weight(tmp_path)
    p = store.register(w, _profile())
    assert store.verify_sha256(p.id) is True


def test_verify_sha256_fail_when_tampered(store, tmp_path):
    w = _weight(tmp_path)
    p = store.register(w, _profile())
    rec = store.get(p.id)
    assert rec is not None
    rec.weight_path.write_bytes(b"tampered")
    assert store.verify_sha256(p.id) is False


def test_verify_sha256_missing(store):
    assert store.verify_sha256("nope") is False


def test_activate_deactivate(store, tmp_path):
    w = _weight(tmp_path)
    p = store.register(w, _profile())
    rec = store.activate(p.id)
    assert rec.active
    assert p.id in store.active_ids
    store.deactivate(p.id)
    assert p.id not in store.active_ids


def test_activate_unknown(store):
    with pytest.raises(KeyError):
        store.activate("ghost")


def test_activate_tampered(store, tmp_path):
    w = _weight(tmp_path)
    p = store.register(w, _profile())
    rec = store.get(p.id)
    assert rec is not None
    rec.weight_path.write_bytes(b"changed")
    with pytest.raises(RuntimeError):
        store.activate(p.id)


def test_remove(store, tmp_path):
    w = _weight(tmp_path)
    p = store.register(w, _profile())
    store.remove(p.id)
    assert store.get(p.id) is None
    # second call is a no-op
    store.remove(p.id)


def test_remove_deletes_weights(store, tmp_path):
    w = _weight(tmp_path)
    p = store.register(w, _profile())
    rec = store.get(p.id)
    assert rec is not None
    path = rec.weight_path
    store.remove(p.id, delete_weights=True)
    assert not path.exists()
