# SPDX-License-Identifier: Apache-2.0
"""Cross-Substrate Genome (v0.I EV-37/38 skeleton) — unit tests.

llive v0.I 案 E (要件 §7) — 物理基盤越境ゲノム の skeleton 検証.

カバー範囲:

1. Substrate enum (値 + str 派生)
2. AbstractGenome 構築 + バリデーション (intent_dim 違反 / history_hash /
   capabilities / rules / intended_substrate / dim 異常)
3. serialization (to_dict / from_dict round-trip + to_json_bytes)
4. kolmogorov_proxy (gzip ベース)
5. AbstractGenome.default() factory
6. SubstrateAdapter Protocol への isinstance チェック (runtime_checkable)
7. PythonSubstrateAdapter の from_abstract / to_abstract round-trip + can_handle
8. RustSubstrateAdapter の skeleton stub 動作 (dict round-trip + FFI marker)
9. 将来 stub adapter (Cython / Neuromorphic / BCI / TypeScript) の
   NotImplementedError + can_handle

実 FFI bridge / BCI 連動 / neuromorphic dispatch は将来 (EV-39 以降).
"""

from __future__ import annotations

import hashlib
import json

import pytest

from llive.perf.evolutionary.cross_substrate import (
    DEFAULT_INTENT_DIM,
    AbstractGenome,
    Substrate,
    SubstrateAdapter,
)
from llive.perf.evolutionary.substrate_adapters import (
    BciSubstrateAdapter,
    CythonSubstrateAdapter,
    NeuromorphicSubstrateAdapter,
    PythonSubstrateAdapter,
    RustSubstrateAdapter,
    TypescriptSubstrateAdapter,
)

# ===========================================================================
# helpers
# ===========================================================================


def _valid_genome(
    intended: Substrate = Substrate.PYTHON,
    intent_dim: int = DEFAULT_INTENT_DIM,
) -> AbstractGenome:
    intent = tuple(float(i) * 0.1 for i in range(intent_dim))
    seed = f"{intended.value}:{intent}".encode()
    h = hashlib.sha256(seed).hexdigest()
    return AbstractGenome(
        intent=intent,
        capabilities=("reason", "plan"),
        rules=("no_self_modify_without_approval",),
        history_hash=h,
        intended_substrate=intended,
        intent_dim=intent_dim,
    )


# ===========================================================================
# 1. Substrate enum
# ===========================================================================


def test_substrate_enum_values() -> None:
    assert Substrate.PYTHON.value == "python"
    assert Substrate.RUST.value == "rust"
    assert Substrate.CYTHON.value == "cython"
    assert Substrate.NEUROMORPHIC.value == "neuromorphic"
    assert Substrate.BCI.value == "bci"
    assert Substrate.TYPESCRIPT.value == "typescript"


def test_substrate_is_str_subclass() -> None:
    # str 派生にしてあるので JSON serialization が自然
    assert isinstance(Substrate.PYTHON, str)
    assert Substrate.PYTHON == "python"


def test_substrate_from_string() -> None:
    assert Substrate("python") is Substrate.PYTHON
    assert Substrate("rust") is Substrate.RUST


# ===========================================================================
# 2. AbstractGenome validation
# ===========================================================================


def test_default_constructs_valid_genome() -> None:
    g = AbstractGenome.default()
    assert len(g.intent) == DEFAULT_INTENT_DIM
    assert g.intent_dim == DEFAULT_INTENT_DIM
    assert g.capabilities == ()
    assert g.rules == ()
    assert g.intended_substrate == Substrate.PYTHON
    assert len(g.history_hash) == 64


def test_default_with_custom_substrate() -> None:
    g = AbstractGenome.default(intended_substrate=Substrate.RUST, intent_dim=8)
    assert g.intent_dim == 8
    assert len(g.intent) == 8
    assert g.intended_substrate == Substrate.RUST


def test_rejects_intent_dim_mismatch() -> None:
    with pytest.raises(ValueError, match="intent length"):
        AbstractGenome(
            intent=(0.0, 0.0, 0.0),  # 3 != 16
            capabilities=(),
            rules=(),
            history_hash="0" * 64,
            intended_substrate=Substrate.PYTHON,
            intent_dim=DEFAULT_INTENT_DIM,
        )


def test_rejects_zero_intent_dim() -> None:
    with pytest.raises(ValueError, match="intent_dim"):
        AbstractGenome(
            intent=(),
            capabilities=(),
            rules=(),
            history_hash="0" * 64,
            intended_substrate=Substrate.PYTHON,
            intent_dim=0,
        )


def test_rejects_non_numeric_intent() -> None:
    intent: tuple = tuple(["str"] * DEFAULT_INTENT_DIM)
    with pytest.raises(ValueError, match="intent\\["):
        AbstractGenome(
            intent=intent,
            capabilities=(),
            rules=(),
            history_hash="0" * 64,
            intended_substrate=Substrate.PYTHON,
        )


def test_rejects_non_string_capability() -> None:
    with pytest.raises(ValueError, match="capabilities"):
        AbstractGenome(
            intent=tuple(0.0 for _ in range(DEFAULT_INTENT_DIM)),
            capabilities=(123,),  # type: ignore[arg-type]
            rules=(),
            history_hash="0" * 64,
            intended_substrate=Substrate.PYTHON,
        )


def test_rejects_non_string_rule() -> None:
    with pytest.raises(ValueError, match="rules"):
        AbstractGenome(
            intent=tuple(0.0 for _ in range(DEFAULT_INTENT_DIM)),
            capabilities=(),
            rules=(None,),  # type: ignore[arg-type]
            history_hash="0" * 64,
            intended_substrate=Substrate.PYTHON,
        )


def test_rejects_bad_history_hash_length() -> None:
    with pytest.raises(ValueError, match="history_hash"):
        AbstractGenome(
            intent=tuple(0.0 for _ in range(DEFAULT_INTENT_DIM)),
            capabilities=(),
            rules=(),
            history_hash="abc",  # too short
            intended_substrate=Substrate.PYTHON,
        )


def test_rejects_non_hex_history_hash() -> None:
    with pytest.raises(ValueError, match="hex"):
        AbstractGenome(
            intent=tuple(0.0 for _ in range(DEFAULT_INTENT_DIM)),
            capabilities=(),
            rules=(),
            history_hash="z" * 64,  # 64 chars but non-hex
            intended_substrate=Substrate.PYTHON,
        )


def test_rejects_non_substrate_intended() -> None:
    with pytest.raises(ValueError, match="intended_substrate"):
        AbstractGenome(
            intent=tuple(0.0 for _ in range(DEFAULT_INTENT_DIM)),
            capabilities=(),
            rules=(),
            history_hash="0" * 64,
            intended_substrate="python",  # type: ignore[arg-type]
        )


def test_genome_is_frozen() -> None:
    g = AbstractGenome.default()
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError
        g.intent_dim = 32  # type: ignore[misc]


def test_genome_is_hashable() -> None:
    g1 = AbstractGenome.default()
    g2 = AbstractGenome.default()
    # frozen + tuple/str fields → hashable
    assert hash(g1) == hash(g2)
    s = {g1, g2}
    assert len(s) == 1


# ===========================================================================
# 3. serialization round-trip
# ===========================================================================


def test_to_dict_round_trip() -> None:
    g = _valid_genome()
    d = g.to_dict()
    g2 = AbstractGenome.from_dict(d)
    assert g == g2


def test_to_dict_then_json_then_from_dict() -> None:
    g = _valid_genome(intended=Substrate.RUST)
    d = g.to_dict()
    # JSON encodable
    encoded = json.dumps(d)
    decoded = json.loads(encoded)
    g2 = AbstractGenome.from_dict(decoded)
    assert g == g2
    assert g2.intended_substrate == Substrate.RUST


def test_to_json_bytes_returns_bytes() -> None:
    g = _valid_genome()
    b = g.to_json_bytes()
    assert isinstance(b, bytes)
    parsed = json.loads(b.decode("utf-8"))
    assert parsed["history_hash"] == g.history_hash


def test_from_dict_accepts_substrate_enum_or_string() -> None:
    # Accept str substrate
    d = _valid_genome().to_dict()
    g = AbstractGenome.from_dict(d)
    assert isinstance(g.intended_substrate, Substrate)
    # Accept Substrate enum directly
    d2 = dict(d, intended_substrate=Substrate.RUST)
    g2 = AbstractGenome.from_dict(d2)
    assert g2.intended_substrate == Substrate.RUST


# ===========================================================================
# 4. kolmogorov_proxy
# ===========================================================================


def test_kolmogorov_proxy_positive() -> None:
    g = _valid_genome()
    k = g.kolmogorov_proxy()
    assert isinstance(k, int)
    assert k > 0


def test_kolmogorov_proxy_more_complex_is_larger() -> None:
    g_simple = AbstractGenome.default()
    g_complex = AbstractGenome(
        intent=tuple(float(i) * 0.123456789 for i in range(DEFAULT_INTENT_DIM)),
        capabilities=("a", "b", "c", "d", "e", "f", "g", "h"),
        rules=("rule_x", "rule_y", "rule_z"),
        history_hash="a" * 64,
        intended_substrate=Substrate.PYTHON,
    )
    # More content → larger compressed size (heuristic)
    assert g_complex.kolmogorov_proxy() > g_simple.kolmogorov_proxy()


# ===========================================================================
# 5. SubstrateAdapter Protocol (runtime_checkable)
# ===========================================================================


def test_python_adapter_satisfies_protocol() -> None:
    adapter = PythonSubstrateAdapter()
    assert isinstance(adapter, SubstrateAdapter)


def test_rust_adapter_satisfies_protocol() -> None:
    adapter = RustSubstrateAdapter()
    assert isinstance(adapter, SubstrateAdapter)


def test_all_future_stub_adapters_satisfy_protocol() -> None:
    for adapter in (
        CythonSubstrateAdapter(),
        NeuromorphicSubstrateAdapter(),
        BciSubstrateAdapter(),
        TypescriptSubstrateAdapter(),
    ):
        assert isinstance(adapter, SubstrateAdapter)


# ===========================================================================
# 6. PythonSubstrateAdapter — round-trip
# ===========================================================================


def test_python_adapter_substrate_attr() -> None:
    adapter = PythonSubstrateAdapter()
    assert adapter.substrate == Substrate.PYTHON


def test_python_adapter_can_handle() -> None:
    adapter = PythonSubstrateAdapter()
    assert adapter.can_handle(Substrate.PYTHON) is True
    assert adapter.can_handle(Substrate.RUST) is False
    assert adapter.can_handle(Substrate.NEUROMORPHIC) is False


def test_python_adapter_from_abstract_returns_dict() -> None:
    adapter = PythonSubstrateAdapter()
    g = _valid_genome()
    phenotype = adapter.from_abstract(g)
    assert isinstance(phenotype, dict)
    assert phenotype["history_hash"] == g.history_hash
    assert phenotype["intent_dim"] == g.intent_dim
    assert phenotype["intended_substrate"] == Substrate.PYTHON.value


def test_python_adapter_round_trip() -> None:
    adapter = PythonSubstrateAdapter()
    g = _valid_genome()
    phenotype = adapter.from_abstract(g)
    g_back = adapter.to_abstract(phenotype)
    assert g_back == g


def test_python_adapter_to_abstract_fills_history_hash_when_missing() -> None:
    # Skeleton 動作: phenotype に history_hash 無しでも determinstic に補完
    adapter = PythonSubstrateAdapter()
    phenotype = {
        "intent": tuple(0.0 for _ in range(DEFAULT_INTENT_DIM)),
        "capabilities": (),
        "rules": (),
        "intent_dim": DEFAULT_INTENT_DIM,
        "intended_substrate": Substrate.PYTHON.value,
    }
    g = adapter.to_abstract(phenotype)
    assert len(g.history_hash) == 64
    assert g.intended_substrate == Substrate.PYTHON


# ===========================================================================
# 7. RustSubstrateAdapter — skeleton stub
# ===========================================================================


def test_rust_adapter_substrate_attr() -> None:
    adapter = RustSubstrateAdapter()
    assert adapter.substrate == Substrate.RUST


def test_rust_adapter_can_handle() -> None:
    adapter = RustSubstrateAdapter()
    assert adapter.can_handle(Substrate.RUST) is True
    assert adapter.can_handle(Substrate.PYTHON) is False


def test_rust_adapter_from_abstract_has_ffi_marker() -> None:
    adapter = RustSubstrateAdapter()
    g = _valid_genome(intended=Substrate.RUST)
    phenotype = adapter.from_abstract(g)
    assert isinstance(phenotype, dict)
    assert phenotype.get("__rust_ffi_payload__") is True
    assert phenotype["history_hash"] == g.history_hash


def test_rust_adapter_round_trip() -> None:
    adapter = RustSubstrateAdapter()
    g = _valid_genome(intended=Substrate.RUST)
    phenotype = adapter.from_abstract(g)
    g_back = adapter.to_abstract(phenotype)
    assert g_back == g


# ===========================================================================
# 8. Future substrate stubs (NotImplementedError)
# ===========================================================================


@pytest.mark.parametrize(
    ("adapter_cls", "expected_substrate"),
    [
        (CythonSubstrateAdapter, Substrate.CYTHON),
        (NeuromorphicSubstrateAdapter, Substrate.NEUROMORPHIC),
        (BciSubstrateAdapter, Substrate.BCI),
        (TypescriptSubstrateAdapter, Substrate.TYPESCRIPT),
    ],
)
def test_future_stub_substrate_attr(adapter_cls, expected_substrate) -> None:
    adapter = adapter_cls()
    assert adapter.substrate == expected_substrate


@pytest.mark.parametrize(
    ("adapter_cls", "intended"),
    [
        (CythonSubstrateAdapter, Substrate.CYTHON),
        (NeuromorphicSubstrateAdapter, Substrate.NEUROMORPHIC),
        (BciSubstrateAdapter, Substrate.BCI),
        (TypescriptSubstrateAdapter, Substrate.TYPESCRIPT),
    ],
)
def test_future_stub_can_handle(adapter_cls, intended) -> None:
    adapter = adapter_cls()
    assert adapter.can_handle(intended) is True
    # 他 substrate は False
    other = Substrate.PYTHON if intended != Substrate.PYTHON else Substrate.RUST
    assert adapter.can_handle(other) is False


@pytest.mark.parametrize(
    "adapter_cls",
    [
        CythonSubstrateAdapter,
        NeuromorphicSubstrateAdapter,
        BciSubstrateAdapter,
        TypescriptSubstrateAdapter,
    ],
)
def test_future_stub_from_abstract_raises(adapter_cls) -> None:
    adapter = adapter_cls()
    g = _valid_genome()
    with pytest.raises(NotImplementedError):
        adapter.from_abstract(g)


@pytest.mark.parametrize(
    "adapter_cls",
    [
        CythonSubstrateAdapter,
        NeuromorphicSubstrateAdapter,
        BciSubstrateAdapter,
        TypescriptSubstrateAdapter,
    ],
)
def test_future_stub_to_abstract_raises(adapter_cls) -> None:
    adapter = adapter_cls()
    with pytest.raises(NotImplementedError):
        adapter.to_abstract({})
