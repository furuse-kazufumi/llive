# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for ``llive.backend.mamba_backend.MambaPyBackend`` (skeleton).

Goals (タスク指示):
* import が落ちないこと (mamba_ssm 不在 + CUDA 不在の Windows 環境でも OK).
* ``is_available()`` が bool を返す.
* ``load()`` で mamba_ssm 不在時に明確 RuntimeError + "mamba_ssm" 文字列.
* ``generate()`` で load 前 RuntimeError.
* RwkvPyBackend と interface 一致 (method 名 set diff = 空) を assert で根拠.
* kwargs 受け取りで例外無し.

実 weight load は WSL2/CUDA 環境で別 PR. ここでは skeleton 互換のみ確認.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# 1) Top-level import must succeed even without mamba_ssm / CUDA.
# ---------------------------------------------------------------------------


def test_module_import_does_not_require_mamba_ssm() -> None:
    """mamba_ssm が未インストール + CUDA 無しでも import できるべき (最重要)."""
    # If mamba_ssm was somehow installed, this still passes — contract is
    # "no exception at import time", independent of installation state.
    from llive.backend import MambaPyBackend  # noqa: F401
    from llive.backend.mamba_backend import default_weights_dir  # noqa: F401

    # Construction must not touch mamba_ssm either.
    backend = MambaPyBackend()
    assert backend.name == "mamba_py"


# ---------------------------------------------------------------------------
# 2) is_available() returns bool
# ---------------------------------------------------------------------------


def test_is_available_returns_bool() -> None:
    from llive.backend import MambaPyBackend

    result = MambaPyBackend.is_available()
    assert isinstance(result, bool)
    # On a CI / Windows-native box, mamba_ssm is almost certainly missing,
    # so we expect False. Either is acceptable — only the type matters.


def test_is_available_false_when_mamba_ssm_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """``sys.modules['mamba_ssm'] = None`` で False になる."""
    from llive.backend import MambaPyBackend

    monkeypatch.setitem(sys.modules, "mamba_ssm", None)
    assert MambaPyBackend.is_available() is False


# ---------------------------------------------------------------------------
# 3) load() raises clear RuntimeError when mamba_ssm is missing
# ---------------------------------------------------------------------------


def _hide_mamba_ssm(monkeypatch: pytest.MonkeyPatch) -> None:
    """``import mamba_ssm`` を必ず ImportError にする."""
    for mod in ("mamba_ssm", "mamba_ssm.models", "mamba_ssm.models.mixer_seq_simple"):
        monkeypatch.setitem(sys.modules, mod, None)


def test_load_raises_runtime_error_when_mamba_ssm_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """mamba_ssm package が無いと load() は明確 RuntimeError."""
    from llive.backend import MambaPyBackend

    _hide_mamba_ssm(monkeypatch)
    backend = MambaPyBackend(weights_dir=tmp_path)
    with pytest.raises(RuntimeError) as excinfo:
        backend.load()
    msg = str(excinfo.value)
    # メッセージに troubleshooting hint が入っていること.
    assert "mamba_ssm" in msg
    assert "pip install" in msg or "Install" in msg


# ---------------------------------------------------------------------------
# 4) generate() raises RuntimeError before load (mamba_ssm missing 経由でも OK)
# ---------------------------------------------------------------------------


def test_generate_raises_runtime_error_when_not_loaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """load 未済 + mamba_ssm 不在で generate() は RuntimeError."""
    from llive.backend import MambaPyBackend
    from llive.llm.backend import GenerateRequest

    _hide_mamba_ssm(monkeypatch)
    backend = MambaPyBackend(weights_dir=tmp_path)
    with pytest.raises(RuntimeError, match=r"mamba_ssm|Mamba not available"):
        backend.generate(GenerateRequest(prompt="hi", max_tokens=4))


def test_generate_text_simple_api_also_raises_when_not_loaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """簡易 generate_text() も load 未済 + mamba_ssm 不在で RuntimeError."""
    from llive.backend import MambaPyBackend

    _hide_mamba_ssm(monkeypatch)
    backend = MambaPyBackend(weights_dir=tmp_path)
    with pytest.raises(RuntimeError):
        backend.generate_text("hi", max_tokens=4)


# ---------------------------------------------------------------------------
# 5) Interface parity with RwkvPyBackend (method 名 set diff = ∅)
# ---------------------------------------------------------------------------


def _public_callables(cls: type) -> set[str]:
    """class が持つ public callable + property 名 set (継承込み)."""
    names: set[str] = set()
    for name in dir(cls):
        if name.startswith("_"):
            continue
        attr = inspect.getattr_static(cls, name, None)
        if attr is None:
            continue
        # property / staticmethod / classmethod / 通常 method を全部拾う.
        if (
            inspect.isfunction(attr)
            or inspect.ismethod(attr)
            or isinstance(attr, (staticmethod, classmethod, property))
        ):
            names.add(name)
    return names


def test_interface_includes_all_rwkv_methods() -> None:
    """MambaPyBackend は RwkvPyBackend の public method 名を **すべて含む**.

    タスク指示「interface 一致を method 名 set diff で根拠」を満たす assertion.
    Mamba 側は task 指示の追加 method (is_available / load / tokenize / detokenize /
    state_dict / load_state_dict) を superset で持つので, ``rwkv - mamba == ∅``
    で空 set diff を確認する.
    """
    from llive.backend import MambaPyBackend, RwkvPyBackend

    rwkv_methods = _public_callables(RwkvPyBackend)
    mamba_methods = _public_callables(MambaPyBackend)

    # 共通必須メソッド (skeleton 互換 contract).
    required_common = {
        "generate",
        "generate_text",
        "weights_path",
        "supports_vlm",
        "supports_coding",
        "supports_audio",
        "supports_sensor",
        "supports_prefix_embeddings",
    }
    for m in required_common:
        assert m in rwkv_methods, f"RwkvPyBackend missing {m}"
        assert m in mamba_methods, f"MambaPyBackend missing {m}"

    # 核心 assertion: rwkv が持つメソッドは全部 mamba も持つ (diff = ∅).
    diff = rwkv_methods - mamba_methods
    assert diff == set(), (
        f"MambaPyBackend is missing methods present in RwkvPyBackend: {sorted(diff)}"
    )


def test_interface_adds_mamba_specific_methods() -> None:
    """task 指示の追加 method が MambaPyBackend に存在する."""
    from llive.backend import MambaPyBackend

    mamba_methods = _public_callables(MambaPyBackend)
    for extra in (
        "is_available",
        "load",
        "tokenize",
        "detokenize",
        "state_dict",
        "load_state_dict",
    ):
        assert extra in mamba_methods, f"MambaPyBackend missing required method: {extra}"


# ---------------------------------------------------------------------------
# 6) kwargs 受け取りで例外無し
# ---------------------------------------------------------------------------


def test_init_accepts_arbitrary_kwargs() -> None:
    """``MambaPyBackend(model_path, device, dtype, **kwargs)`` で extra kwargs OK."""
    from llive.backend import MambaPyBackend

    backend = MambaPyBackend(
        model_filename="foo.safetensors",
        device="cpu",
        dtype="float32",
        # Extra unknown kwargs — must not raise.
        foo=1,
        bar="baz",
        nested={"a": [1, 2]},
    )
    assert backend.device == "cpu"
    assert backend.dtype == "float32"
    assert backend.model_filename == "foo.safetensors"


# ---------------------------------------------------------------------------
# 7) Capability flags (text only skeleton)
# ---------------------------------------------------------------------------


def test_capability_flags_are_text_only() -> None:
    from llive.backend import MambaPyBackend

    backend = MambaPyBackend()
    assert backend.supports_vlm is False
    assert backend.supports_audio is False
    assert backend.supports_sensor is False
    assert backend.supports_prefix_embeddings is False
    assert backend.supports_coding is False  # mamba-130m は code-tuned ではない


# ---------------------------------------------------------------------------
# 8) Path helpers
# ---------------------------------------------------------------------------


def test_default_weights_dir_respects_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from llive.backend.mamba_backend import default_weights_dir

    monkeypatch.setenv("LLIVE_DATA_DIR", str(tmp_path))
    assert default_weights_dir() == tmp_path / "mamba"


def test_default_weights_dir_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from llive.backend.mamba_backend import default_weights_dir

    monkeypatch.delenv("LLIVE_DATA_DIR", raising=False)
    result = default_weights_dir()
    assert result.parts[-3:] == (".llive", "data", "mamba")


def test_weights_path_combines_dir_and_filename(tmp_path: Path) -> None:
    from llive.backend import MambaPyBackend

    backend = MambaPyBackend(
        model_filename="custom.safetensors",
        weights_dir=tmp_path,
    )
    assert backend.weights_path == tmp_path / "custom.safetensors"


# ---------------------------------------------------------------------------
# 9) load() RuntimeError detail — weight missing path
# ---------------------------------------------------------------------------


def test_load_raises_runtime_error_when_weights_missing_even_with_mamba(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """mamba_ssm は import できるが重みが無い → 明確な RuntimeError."""
    from llive.backend import MambaPyBackend

    fake_mamba = mock.MagicMock()
    monkeypatch.setitem(sys.modules, "mamba_ssm", fake_mamba)

    backend = MambaPyBackend(
        model_filename="nonexistent.safetensors",
        weights_dir=tmp_path,
    )
    with pytest.raises(RuntimeError, match="weights not found"):
        backend.load()


# ---------------------------------------------------------------------------
# 10) tokenize/detokenize raises RuntimeError before load
# ---------------------------------------------------------------------------


def test_tokenize_raises_when_not_loaded() -> None:
    from llive.backend import MambaPyBackend

    backend = MambaPyBackend()
    with pytest.raises(RuntimeError, match="not loaded|load\\(\\)"):
        backend.tokenize("hello")


def test_detokenize_raises_when_not_loaded() -> None:
    from llive.backend import MambaPyBackend

    backend = MambaPyBackend()
    with pytest.raises(RuntimeError, match="not loaded|load\\(\\)"):
        backend.detokenize([1, 2, 3])


# ---------------------------------------------------------------------------
# 11) state_dict / load_state_dict round-trip
# ---------------------------------------------------------------------------


def test_state_dict_returns_metadata() -> None:
    from llive.backend import MambaPyBackend

    backend = MambaPyBackend(
        model_filename="mamba-130m.safetensors",
        device="cpu",
        dtype="float32",
    )
    state = backend.state_dict()
    assert isinstance(state, dict)
    assert state["backend"] == "mamba_py"
    assert state["device"] == "cpu"
    assert state["dtype"] == "float32"
    assert state["loaded"] is False
    assert "tensors" in state


def test_load_state_dict_roundtrip(tmp_path: Path) -> None:
    """state_dict → load_state_dict で metadata が復元される."""
    from llive.backend import MambaPyBackend

    src = MambaPyBackend(
        model_filename="src.safetensors",
        weights_dir=tmp_path,
        device="cuda",
        dtype="bfloat16",
    )
    state = src.state_dict()

    dst = MambaPyBackend(device="cpu", dtype="float32")
    dst.load_state_dict(state, strict=True)
    assert dst.device == "cuda"
    assert dst.dtype == "bfloat16"


def test_load_state_dict_rejects_non_dict() -> None:
    from llive.backend import MambaPyBackend

    backend = MambaPyBackend()
    with pytest.raises(TypeError):
        backend.load_state_dict("not a dict", strict=True)  # type: ignore[arg-type]


def test_load_state_dict_strict_missing_keys() -> None:
    from llive.backend import MambaPyBackend

    backend = MambaPyBackend()
    with pytest.raises(KeyError):
        backend.load_state_dict({"backend": "mamba_py"}, strict=True)


def test_load_state_dict_non_strict_tolerates_partial() -> None:
    from llive.backend import MambaPyBackend

    backend = MambaPyBackend(device="cpu", dtype="float32")
    # 必須キー欠如だが strict=False なら通る.
    backend.load_state_dict({"device": "cuda"}, strict=False)
    assert backend.device == "cuda"


# ---------------------------------------------------------------------------
# 12) Real mamba path skipped if not installed
# ---------------------------------------------------------------------------


def test_real_mamba_skipped_if_not_installed() -> None:
    """mamba_ssm が無い環境ではこの test は skip される (CI 互換)."""
    try:
        import mamba_ssm  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        pytest.skip("mamba_ssm package not installed — skeleton test only.")
    assert True


# ---------------------------------------------------------------------------
# 13) Misc: backend inherits LLMBackend interface
# ---------------------------------------------------------------------------


def test_inherits_llm_backend() -> None:
    """MambaPyBackend は ``LLMBackend`` を継承し, ``GenerateRequest`` を受ける."""
    from llive.backend import MambaPyBackend
    from llive.llm.backend import LLMBackend

    backend: Any = MambaPyBackend()
    assert isinstance(backend, LLMBackend)


def test_extra_kwargs_preserved_for_future_extension() -> None:
    """``**kwargs`` で渡した値は ``_extra_kwargs`` に保持される (skeleton)."""
    from llive.backend import MambaPyBackend

    backend = MambaPyBackend(custom_flag=True, sampler_temp=0.7)
    assert backend._extra_kwargs == {"custom_flag": True, "sampler_temp": 0.7}
