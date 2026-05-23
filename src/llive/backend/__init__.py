# SPDX-License-Identifier: Apache-2.0
"""llive in-process backend skeletons (non-transformer track).

ここに集める backend は **process 内**で重み (weights) を保持し,
HTTP 経由 (llama-server / RWKV.cpp HTTP / openai-compatible) を介さず
直接 LLM 推論を回すための実装です. ``llive.llm.backend`` 側の
delegating wrapper (``rwkv_cpp_server`` 等) と対になる ``*_py`` 経路.

設計方針:

* 既存 ``llive.llm.backend.LLMBackend`` interface (``generate(GenerateRequest)
  -> GenerateResponse``) を踏襲する.
* 重量級 dependency (rwkv / torch / mamba-ssm / 等) は **import 時には触れず**,
  ``generate`` 呼び出し時に lazy import. 未インストールなら
  ``RuntimeError`` を明確なメッセージで投げる.
* 重み (weights) は ``$LLIVE_DATA_DIR`` (default ``~/.llive/data``) の
  サブディレクトリを既定とする. 実 DL ロジックは別 PR でカバー
  (skeleton では placeholder).
* on-prem only. cloud API への fallback は **しない**
  (feedback_llive_measurement_purity に従う).

最初の実装は ``RwkvPyBackend`` (RWKV-7, pure PyTorch + CPU 可) です.
"""

from __future__ import annotations

from llive.backend.rwkv_backend import RwkvPyBackend, default_weights_dir
from llive.backend.mamba_backend import MambaPyBackend
from llive.backend.mamba_backend import default_weights_dir as default_mamba_weights_dir

__all__ = [
    "RwkvPyBackend",
    "MambaPyBackend",
    "default_weights_dir",
    "default_mamba_weights_dir",
]
