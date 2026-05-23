# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for ``llive.backend.rwkv_backend.RwkvPyBackend`` (skeleton).

Goals:
* import が落ちないこと (rwkv package 未インストール環境でも OK).
* rwkv package が無いとき, generate() 呼び出しで明確な RuntimeError が出ること.
* 重みファイルが無いとき, package があっても明確な RuntimeError が出ること.
* GenerateRequest interface と簡易 generate_text() の両方が動くこと.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Top-level import must succeed even without rwkv installed.
# ---------------------------------------------------------------------------


def test_module_import_does_not_require_rwkv() -> None:
    """rwkv が未インストールでも skeleton 自体は import できるべき."""
    # If rwkv was somehow installed in CI, this still passes — the contract is
    # "no exception at import time", which is independent of installation state.
    from llive.backend import RwkvPyBackend, default_weights_dir  # noqa: F401

    # Construction must not touch rwkv either.
    backend = RwkvPyBackend()
    assert backend.name == "rwkv_py"
    assert isinstance(default_weights_dir(), Path)


def test_default_weights_dir_respects_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``$LLIVE_DATA_DIR`` をセットすれば weights_dir はその下に来る."""
    from llive.backend.rwkv_backend import default_weights_dir

    monkeypatch.setenv("LLIVE_DATA_DIR", str(tmp_path))
    expected = tmp_path / "rwkv"
    assert default_weights_dir() == expected


def test_default_weights_dir_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """env 未設定なら ``~/.llive/data/rwkv`` を返す."""
    from llive.backend.rwkv_backend import default_weights_dir

    monkeypatch.delenv("LLIVE_DATA_DIR", raising=False)
    result = default_weights_dir()
    # path tail invariant — home が何であれ末尾は ``.llive/data/rwkv``
    assert result.parts[-3:] == (".llive", "data", "rwkv")


# ---------------------------------------------------------------------------
# Capability flags
# ---------------------------------------------------------------------------


def test_capability_flags_are_text_only() -> None:
    from llive.backend import RwkvPyBackend

    backend = RwkvPyBackend()
    assert backend.supports_vlm is False
    assert backend.supports_audio is False
    assert backend.supports_sensor is False
    assert backend.supports_prefix_embeddings is False
    # RWKV-world includes code corpus
    assert backend.supports_coding is True


def test_weights_path_combines_dir_and_filename(tmp_path: Path) -> None:
    from llive.backend import RwkvPyBackend

    backend = RwkvPyBackend(
        model_filename="custom.pth",
        weights_dir=tmp_path,
    )
    assert backend.weights_path == tmp_path / "custom.pth"


# ---------------------------------------------------------------------------
# generate() error paths — these must work regardless of rwkv presence.
# ---------------------------------------------------------------------------


def _hide_rwkv(monkeypatch: pytest.MonkeyPatch) -> None:
    """``import rwkv.*`` が必ず ImportError になるよう sys.modules を操作."""
    # Block both top-level and submodules.
    for mod in ("rwkv", "rwkv.model", "rwkv.utils"):
        monkeypatch.setitem(sys.modules, mod, None)


def test_generate_raises_runtime_error_when_rwkv_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """rwkv package が無いと generate() は RuntimeError を出すべき."""
    from llive.backend import RwkvPyBackend
    from llive.llm.backend import GenerateRequest

    _hide_rwkv(monkeypatch)
    backend = RwkvPyBackend(weights_dir=tmp_path)
    with pytest.raises(RuntimeError, match=r"rwkv.*package|Install with"):
        backend.generate(GenerateRequest(prompt="hello", max_tokens=8))


def test_generate_text_simple_api_also_raises_when_rwkv_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """簡易 generate_text(prompt, max_tokens) も同様にエラー."""
    from llive.backend import RwkvPyBackend

    _hide_rwkv(monkeypatch)
    backend = RwkvPyBackend(weights_dir=tmp_path)
    with pytest.raises(RuntimeError):
        backend.generate_text("hello", max_tokens=8)


def test_generate_raises_when_weights_missing_even_with_rwkv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """rwkv は import できるが weights が無い ─ 明確な RuntimeError.

    ``rwkv.model`` / ``rwkv.utils`` を MagicMock で差し込んで「rwkv あり」
    状態を作り, 重みファイルだけ無い状況を確認する.
    """
    from llive.backend import RwkvPyBackend
    from llive.llm.backend import GenerateRequest

    fake_rwkv = mock.MagicMock()
    fake_rwkv_model = mock.MagicMock()
    fake_rwkv_utils = mock.MagicMock()
    # ``from rwkv.model import RWKV`` が成功するよう attribute を生やす.
    fake_rwkv_model.RWKV = mock.MagicMock()
    fake_rwkv_utils.PIPELINE = mock.MagicMock()
    fake_rwkv_utils.PIPELINE_ARGS = mock.MagicMock()
    monkeypatch.setitem(sys.modules, "rwkv", fake_rwkv)
    monkeypatch.setitem(sys.modules, "rwkv.model", fake_rwkv_model)
    monkeypatch.setitem(sys.modules, "rwkv.utils", fake_rwkv_utils)

    backend = RwkvPyBackend(
        model_filename="nonexistent-weights.pth",
        weights_dir=tmp_path,  # empty directory
    )
    with pytest.raises(RuntimeError, match="weights not found"):
        backend.generate(GenerateRequest(prompt="hi", max_tokens=4))


# ---------------------------------------------------------------------------
# Happy path with fully mocked rwkv + dummy weights file.
# ---------------------------------------------------------------------------


def test_generate_happy_path_with_mocked_rwkv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """rwkv 全体を mock + 重み placeholder file を置き, GenerateResponse 整合性確認.

    rwkv 自体が pure PyTorch で重い import なため CI で実 rwkv を要求しない.
    """
    from llive.backend import RwkvPyBackend
    from llive.llm.backend import GenerateRequest

    # Pre-create a fake weights file so existence check passes.
    weights_file = tmp_path / "dummy.pth"
    weights_file.write_bytes(b"\x00" * 32)

    pipeline_instance = mock.MagicMock()
    pipeline_instance.generate.return_value = "hello world"

    fake_rwkv = mock.MagicMock()
    fake_model = mock.MagicMock()
    fake_utils = mock.MagicMock()
    fake_model.RWKV = mock.MagicMock(return_value=mock.MagicMock(name="rwkv_model_instance"))
    fake_utils.PIPELINE = mock.MagicMock(return_value=pipeline_instance)

    class _FakeArgs:
        def __init__(self, **kw: Any) -> None:
            self.kw = kw

    fake_utils.PIPELINE_ARGS = _FakeArgs

    monkeypatch.setitem(sys.modules, "rwkv", fake_rwkv)
    monkeypatch.setitem(sys.modules, "rwkv.model", fake_model)
    monkeypatch.setitem(sys.modules, "rwkv.utils", fake_utils)

    backend = RwkvPyBackend(model_filename="dummy.pth", weights_dir=tmp_path)
    resp = backend.generate(GenerateRequest(prompt="prompt", max_tokens=16))

    assert resp.text == "hello world"
    assert resp.backend == "rwkv_py"
    assert resp.finish_reason == "stop"
    assert resp.raw["weights_path"].endswith("dummy.pth")
    # generate_text simple API
    assert backend.generate_text("again", max_tokens=8) == "hello world"


def test_generate_returns_error_response_when_pipeline_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PIPELINE.generate が例外を出したら GenerateResponse(finish_reason='error')."""
    from llive.backend import RwkvPyBackend
    from llive.llm.backend import GenerateRequest

    weights_file = tmp_path / "dummy.pth"
    weights_file.write_bytes(b"\x00" * 32)

    pipeline_instance = mock.MagicMock()
    pipeline_instance.generate.side_effect = ValueError("boom")

    fake_rwkv = mock.MagicMock()
    fake_model = mock.MagicMock()
    fake_utils = mock.MagicMock()
    fake_model.RWKV = mock.MagicMock(return_value=mock.MagicMock())
    fake_utils.PIPELINE = mock.MagicMock(return_value=pipeline_instance)

    class _FakeArgs:
        def __init__(self, **kw: Any) -> None:
            self.kw = kw

    fake_utils.PIPELINE_ARGS = _FakeArgs

    monkeypatch.setitem(sys.modules, "rwkv", fake_rwkv)
    monkeypatch.setitem(sys.modules, "rwkv.model", fake_model)
    monkeypatch.setitem(sys.modules, "rwkv.utils", fake_utils)

    backend = RwkvPyBackend(model_filename="dummy.pth", weights_dir=tmp_path)
    resp = backend.generate(GenerateRequest(prompt="x", max_tokens=4))
    assert resp.finish_reason == "error"
    assert resp.text == ""
    assert resp.raw["error_type"] == "ValueError"
    assert "boom" in resp.raw["error"]


# ---------------------------------------------------------------------------
# Live rwkv path — only run if the real package is installed.
# ---------------------------------------------------------------------------


def test_real_rwkv_skipped_if_not_installed() -> None:
    """rwkv が無い環境ではこの test は skip される (CI 互換)."""
    try:
        import rwkv  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        pytest.skip("rwkv package not installed — skeleton test only.")
    # 実 rwkv があっても重みファイルが無ければ意味が無いので, ここでは
    # import が通ることだけ確認 (no-op smoke).
    assert True
