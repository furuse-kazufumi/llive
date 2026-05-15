# SPDX-License-Identifier: Apache-2.0
"""BC-04: adapter / lora_switch sub-blocks."""

from __future__ import annotations

import pytest

from llive.container import BlockContainerExecutor, BlockState
from llive.container.subblocks.adapter_block import (
    AdapterBlock,
    LoraSwitchBlock,
    get_adapter_store,
    set_adapter_store,
)
from llive.memory.parameter import AdapterProfile, AdapterStore
from llive.schema.models import ContainerSpec, SubBlockRef


@pytest.fixture
def store(tmp_path):
    s = AdapterStore(data_dir=tmp_path / "p", index_path=tmp_path / "i.duckdb")
    set_adapter_store(s)
    yield s
    set_adapter_store(None)
    s.close()


def _adapter(store, tmp_path, name, tags=()) -> AdapterProfile:
    w = tmp_path / f"{name}.safetensors"
    w.write_bytes(b"AAAA" * 100)
    return store.register(w, AdapterProfile(name=name, base_model="Qwen", format="lora", tags=list(tags)))


def test_get_adapter_store_default(monkeypatch, tmp_path):
    set_adapter_store(None)
    monkeypatch.setenv("LLIVE_DATA_DIR", str(tmp_path))
    s = get_adapter_store()
    assert s is not None
    set_adapter_store(None)


def test_adapter_block_activates_known_id(store, tmp_path):
    p = _adapter(store, tmp_path, "lora_a")
    block = AdapterBlock.factory({"adapter_id": p.id})
    state = block(BlockState(prompt="x"))
    trace = state.meta["adapter_trace"][0]
    assert trace["active"] == p.id


def test_adapter_block_fallback_when_missing(store):
    block = AdapterBlock.factory({"adapter_id": "ghost", "fallback_to_base": True})
    state = block(BlockState(prompt="x"))
    assert state.meta["adapter_trace"][0]["active"] == "base"


def test_adapter_block_strict_missing_raises(store):
    block = AdapterBlock.factory({"adapter_id": "ghost", "fallback_to_base": False})
    with pytest.raises(KeyError):
        block(BlockState(prompt="x"))


def test_lora_switch_task_conditioned(store, tmp_path):
    a = _adapter(store, tmp_path, "math_lora", tags=["math"])
    b = _adapter(store, tmp_path, "code_lora", tags=["code"])
    block = LoraSwitchBlock.factory({"adapters": [a.id, b.id], "selector": "task_conditioned"})
    state = block(BlockState(prompt="q", meta={"task_tag": "code"}))
    assert state.meta["lora_switch_trace"][0]["active"] == b.id


def test_lora_switch_round_robin(store, tmp_path):
    a = _adapter(store, tmp_path, "lora_a")
    b = _adapter(store, tmp_path, "lora_b")
    block = LoraSwitchBlock.factory({"adapters": [a.id, b.id], "selector": "round_robin"})
    s1 = block(BlockState(prompt="x"))
    s2 = block(BlockState(prompt="x"))
    s3 = block(BlockState(prompt="x"))
    actives = [
        s1.meta["lora_switch_trace"][0]["active"],
        s2.meta["lora_switch_trace"][0]["active"],
        s3.meta["lora_switch_trace"][0]["active"],
    ]
    assert actives == [a.id, b.id, a.id]


def test_lora_switch_no_adapters_returns_base(store):
    block = LoraSwitchBlock.factory({"adapters": [], "selector": "task_conditioned"})
    state = block(BlockState(prompt="x"))
    assert state.meta["lora_switch_trace"][0]["active"] == "base"


def test_adapter_block_integrates_with_executor(store, tmp_path):
    p = _adapter(store, tmp_path, "demo")
    spec = ContainerSpec(
        schema_version=1,
        container_id="ad_v1",
        subblocks=[SubBlockRef(type="adapter", name="ad", config={"adapter_id": p.id})],
    )
    exe = BlockContainerExecutor(spec)
    state = exe.execute(BlockState(prompt="hello"))
    assert any(t.type == "adapter" for t in state.trace)


def test_lora_switch_fallback_to_first_when_task_unknown(store, tmp_path):
    a = _adapter(store, tmp_path, "lora_a", tags=["math"])
    b = _adapter(store, tmp_path, "lora_b", tags=["code"])
    block = LoraSwitchBlock.factory({"adapters": [a.id, b.id], "selector": "task_conditioned"})
    state = block(BlockState(prompt="q", meta={"task_tag": "other"}))
    # falls back to first adapter when no tag match
    assert state.meta["lora_switch_trace"][0]["active"] == a.id
