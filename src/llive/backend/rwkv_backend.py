# SPDX-License-Identifier: Apache-2.0
"""RWKV-7 in-process backend (pure PyTorch + CPU 可) — skeleton.

``llive.llm.backend.RwkvBackend`` の ``rwkv_py`` transport に相当する
**in-process** 経路の独立スケルトン. RWKV は recurrent な
state を持つ非 Transformer LLM で:

* attention の O(L^2) を持たず, 1 step あたり O(state_dim) で動く
* pure PyTorch 実装が PyPI ``rwkv`` package で配布されており,
  CUDA を持たない Windows 環境でも CPU で動作する
* 「llive を on-prem only に保ちながら非 Transformer backend を内側で
  呼ぶ」という QIITA #24-06 の公言に対し, **最も着地が容易な**候補

設計:

* ``rwkv`` package は **lazy import** — このモジュールを import するだけでは
  package が無くてもエラーにならない. ``generate()`` 呼び出し時に
  明示的な ``RuntimeError`` を投げる.
* 重みは ``$LLIVE_DATA_DIR/rwkv/`` 配下を想定. 実 DL は次フェーズで,
  ここでは weights path 解決と「無ければエラー」だけを行う.
* interface は既存 ``LLMBackend`` を踏襲しつつ, タスク指示通り
  ``generate(prompt: str, max_tokens: int = 64) -> str`` の簡易呼び出しも
  ``generate_text()`` として併設する.

License remark:
    RWKV-7-world 系の重みは Apache-2.0 互換ライセンスで配布されており
    FullSense (Apache-2.0 + Commercial dual) と矛盾しない.
    Qwen 派生は商用障壁 (feedback_qwen_commercial_barrier) のため
    default では使わない.

Next steps (重み DL):
    * 最初は ``RWKV-x070-World-0.4B-v2.9-20250107-ctx4096.pth`` (約 0.8 GB) を
      推奨 — RWKV-world 系で license が緩く, CPU 起動が現実的なサイズ.
    * URL: https://huggingface.co/BlinkDL/rwkv-7-world (HF Hub 経由).
    * 別 PR で ``libexec/llive-fetch-rwkv-weights`` などを追加して
      ``$LLIVE_DATA_DIR/rwkv/<filename>`` に置く想定.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llive.llm.backend import (
    GenerateRequest,
    GenerateResponse,
    LLMBackend,
)


# Default model file name (実 DL は次フェーズ — placeholder 値).
DEFAULT_MODEL_FILENAME = "RWKV-x070-World-0.4B-v2.9-20250107-ctx4096.pth"

# RWKV strategy string — "cpu fp32" は CUDA 不要・最も安全な選択.
# CUDA があれば "cuda fp16" 等に切り替えるが skeleton では CPU 固定.
DEFAULT_STRATEGY = "cpu fp32"


def default_weights_dir() -> Path:
    """``$LLIVE_DATA_DIR/rwkv/`` (default ``~/.llive/data/rwkv``) を返す.

    実 DL 関数 (次フェーズ) が書き込み, ``RwkvPyBackend`` が読み込む
    共通 base path. ディレクトリは存在しなくても返り値を返すだけで
    side-effect は無い.
    """
    base = os.environ.get("LLIVE_DATA_DIR")
    if base:
        return Path(base) / "rwkv"
    return Path.home() / ".llive" / "data" / "rwkv"


@dataclass
class _LazyModel:
    """rwkv.model.RWKV と PIPELINE のペアを遅延保持するコンテナ.

    skeleton では実 load は ``_ensure_loaded()`` の中で 1 回だけ行う.
    """

    weights_path: Path
    strategy: str = DEFAULT_STRATEGY
    model: Any = None  # rwkv.model.RWKV
    pipeline: Any = None  # rwkv.utils.PIPELINE
    loaded: bool = False
    # ``rwkv`` package が import できなかった場合の最後のエラー (lazy で保持).
    import_error: BaseException | None = field(default=None)


class RwkvPyBackend(LLMBackend):
    """RWKV-7 in-process backend (``rwkv_py`` 経路, skeleton).

    既存 ``llive.llm.backend.RwkvBackend`` (transport=``rwkv_cpp_server``) と
    違って HTTP を介さず, ``rwkv`` PyPI package を直接呼ぶ. クラス名を
    変えてあるのは既存 ``RwkvBackend`` (HTTP 経由) との衝突を避けるため.

    Args:
        model_filename: ``$LLIVE_DATA_DIR/rwkv/`` 配下の重みファイル名.
            None なら :data:`DEFAULT_MODEL_FILENAME` を使う.
        weights_dir: 重みファイルを置くディレクトリ. None なら
            :func:`default_weights_dir` を使う.
        strategy: ``rwkv.model.RWKV(strategy=...)`` に渡す device 文字列.
            ``"cpu fp32"`` がもっとも環境依存が少ない (CUDA 不要).
        tokens_per_chunk: ``PIPELINE.generate()`` の内部 chunk size.

    Raises:
        この時点では何も raise しない. 実エラーは ``generate()`` 時点まで
        遅延する (lazy import + lazy load).
    """

    name = "rwkv_py"
    DEFAULT_MODEL = "rwkv-7-world"

    def __init__(
        self,
        model_filename: str | None = None,
        *,
        weights_dir: Path | None = None,
        strategy: str | None = None,
        tokens_per_chunk: int = 256,
    ) -> None:
        self.weights_dir = Path(weights_dir) if weights_dir else default_weights_dir()
        self.model_filename = (
            model_filename
            or os.environ.get("LLIVE_RWKV_MODEL_FILENAME")
            or DEFAULT_MODEL_FILENAME
        )
        self.strategy = (
            strategy or os.environ.get("LLIVE_RWKV_STRATEGY") or DEFAULT_STRATEGY
        )
        self.tokens_per_chunk = int(tokens_per_chunk)
        self.model = self.DEFAULT_MODEL
        self._lazy = _LazyModel(weights_path=self.weights_path, strategy=self.strategy)

    # ------------------------------------------------------------------
    # Capability flags
    # ------------------------------------------------------------------
    @property
    def supports_vlm(self) -> bool:
        return False  # RWKV-7 text only (vision-rwkv は別系統)

    @property
    def supports_coding(self) -> bool:
        return True  # RWKV-world は code corpus も含む

    @property
    def supports_audio(self) -> bool:
        return False

    @property
    def supports_sensor(self) -> bool:
        return False

    @property
    def supports_prefix_embeddings(self) -> bool:
        # 原理的には可能 (rwkv は inputs_embeds 受け取り可) だが skeleton
        # では未配線. Phase C-1.4 で配線したら True にする.
        return False

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------
    @property
    def weights_path(self) -> Path:
        """重みファイルのフルパス (存在チェックなし)."""
        return self.weights_dir / self.model_filename

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        """rwkv package を import し, 重みを 1 回だけロードする.

        Raises:
            RuntimeError: ``rwkv`` package が見つからない場合, または
                重みファイルが見つからない場合. メッセージで原因と
                対処手順を明示する.
        """
        if self._lazy.loaded:
            return
        # 1) lazy import — ここで初めて rwkv に触る
        try:
            from rwkv.model import RWKV  # type: ignore[import-not-found]
            from rwkv.utils import PIPELINE  # type: ignore[import-not-found]
        except ImportError as exc:  # rwkv package 未インストール
            self._lazy.import_error = exc
            raise RuntimeError(
                "RwkvPyBackend requires the 'rwkv' PyPI package. "
                "Install with:  pip install rwkv tokenizers "
                "(plus torch>=2.0 for CPU/CUDA inference)."
            ) from exc

        # 2) 重みファイル存在チェック
        wp = self.weights_path
        if not wp.is_file():
            raise RuntimeError(
                f"RWKV weights not found at {wp!s}. "
                "Place a RWKV-7-world .pth file there, or set "
                "$LLIVE_DATA_DIR to a directory containing 'rwkv/<filename>.pth'. "
                "Suggested first model: "
                f"'{DEFAULT_MODEL_FILENAME}' from "
                "https://huggingface.co/BlinkDL/rwkv-7-world."
            )

        # 3) load — strategy は "cpu fp32" 等. ここで OOM の可能性あり.
        model = RWKV(model=str(wp.with_suffix("")), strategy=self.strategy)
        pipeline = PIPELINE(model, "rwkv_vocab_v20230424")
        self._lazy.model = model
        self._lazy.pipeline = pipeline
        self._lazy.loaded = True

    # ------------------------------------------------------------------
    # Public generate API
    # ------------------------------------------------------------------
    def generate_text(self, prompt: str, max_tokens: int = 64) -> str:
        """簡易インタフェース — タスク指示通りの shape.

        既存 backend (``LLMBackend.generate(GenerateRequest)``) と並列に
        提供する. 内部で ``GenerateRequest`` を組み立てる.
        """
        req = GenerateRequest(prompt=prompt, max_tokens=int(max_tokens))
        return self.generate(req).text

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        """既存 ``LLMBackend`` interface — テキストのみ.

        Raises:
            RuntimeError: ``rwkv`` package or weights が見つからない場合.
        """
        self._ensure_loaded()

        pipeline = self._lazy.pipeline
        # PIPELINE.generate signature (rwkv >= 0.8):
        #   pipeline.generate(ctx: str, token_count: int, args, callback=None, state=None)
        # args は PIPELINE_ARGS 推奨だが skeleton では default で OK.
        try:
            from rwkv.utils import PIPELINE_ARGS  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - rwkv 不在時は _ensure_loaded が先に raise
            raise RuntimeError("rwkv package missing PIPELINE_ARGS") from exc

        args = PIPELINE_ARGS(
            temperature=float(max(request.temperature, 0.01)),
            top_p=0.85,
            alpha_frequency=0.2,
            alpha_presence=0.2,
            token_ban=[],
            token_stop=[0],
            chunk_len=self.tokens_per_chunk,
        )
        try:
            text = pipeline.generate(
                request.prompt,
                token_count=int(request.max_tokens),
                args=args,
            )
        except Exception as exc:  # rwkv 内部エラーを公開 surface に乗せる
            return GenerateResponse(
                text="",
                finish_reason="error",
                backend=self.name,
                model=self.model,
                raw={"error": str(exc), "error_type": type(exc).__name__},
            )

        return GenerateResponse(
            text=str(text),
            finish_reason="stop",
            backend=self.name,
            model=self.model,
            raw={
                "weights_path": str(self.weights_path),
                "strategy": self.strategy,
            },
        )
