# SPDX-License-Identifier: Apache-2.0
"""Mamba (State Space Model) in-process backend — skeleton (SSM 系第 2 弾).

``RwkvPyBackend`` (SSM 系第 1 弾, ``rwkv_backend.py``) と **対** をなす,
``mamba-ssm`` PyPI package を直接呼ぶ in-process 経路の skeleton.

Mamba は Albert Gu / Tri Dao の選択的状態空間モデル (Selective SSM):

* attention の O(L^2) を持たず, 1 step あたり O(state_dim) で動く点は
  RWKV と同じ
* ただし参照実装の ``mamba-ssm`` は **CUDA 必須** (Triton kernel) で,
  pure CPU では動かない. WSL2 + CUDA が無い Windows 環境では
  「import は通る」「実 generate は明確 RuntimeError」 が現実的着地.
* AI taxonomy (`project_ai_algorithms_taxonomy`) 優先度 #3 に対応

設計:

* ``mamba_ssm`` package は **lazy import** — このモジュールを import
  するだけでは package が無くてもエラーにならない (テスト 1 件目).
* ``is_available()`` で「mamba_ssm + (任意 import 可能な torch)」可否を
  bool で返す. CUDA まで踏み込む判定は呼ぶ側に委ねる.
* ``load()`` で実 import + 重み解決を 1 回. 失敗は明確 RuntimeError.
* ``generate(GenerateRequest)`` は load 未済なら RuntimeError, 済でも
  weight load 自体が skeleton なので明示 NotImplementedError を投げる.
* interface は ``RwkvPyBackend`` を踏襲しつつ, task 指示の追加 method
  (``is_available`` / ``load`` / ``tokenize`` / ``detokenize`` /
  ``state_dict`` / ``load_state_dict``) も superset として追加.

Next steps (実 weight load):
    * WSL2 + CUDA 12.x + ``pip install mamba-ssm causal-conv1d`` 後に
      ``state-spaces/mamba-130m`` 等を HF Hub から DL.
    * 重みは ``$LLIVE_DATA_DIR/mamba/`` に置く.
    * 別 PR で ``_ensure_loaded()`` の中身を本実装に差し替える.

License remark:
    mamba-ssm は Apache-2.0 で配布. FullSense (Apache-2.0 + Commercial dual)
    と矛盾しない.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from llive.llm.backend import (
    GenerateRequest,
    GenerateResponse,
    LLMBackend,
)


# Default model file name (実 DL は次フェーズ — placeholder 値).
# state-spaces/mamba-130m は最も小さく試しやすい (~260MB fp32).
DEFAULT_MODEL_FILENAME = "mamba-130m.safetensors"

# Mamba は CUDA 必須なので CPU では実 generate できない. skeleton では
# "cuda" を default にしておくが, is_available() で False を返した時点で
# generate() は RuntimeError を投げる.
DEFAULT_DEVICE = "cuda"
DEFAULT_DTYPE = "float16"


def default_weights_dir() -> Path:
    """``$LLIVE_DATA_DIR/mamba/`` (default ``~/.llive/data/mamba``) を返す.

    実 DL 関数 (次フェーズ) が書き込み, ``MambaPyBackend`` が読み込む
    共通 base path. ディレクトリは存在しなくても返り値を返すだけで
    side-effect は無い.
    """
    base = os.environ.get("LLIVE_DATA_DIR")
    if base:
        return Path(base) / "mamba"
    return Path.home() / ".llive" / "data" / "mamba"


@dataclass
class _LazyMambaModel:
    """``mamba_ssm`` 由来オブジェクトを遅延保持するコンテナ.

    skeleton では実 load は ``_ensure_loaded()`` の中で 1 回だけ行う.
    """

    weights_path: Path
    device: str = DEFAULT_DEVICE
    dtype: str = DEFAULT_DTYPE
    model: Any = None  # mamba_ssm.models.mixer_seq_simple.MambaLMHeadModel
    tokenizer: Any = None  # transformers.AutoTokenizer 等
    loaded: bool = False
    # ``mamba_ssm`` package が import できなかった場合の最後のエラー.
    import_error: BaseException | None = field(default=None)
    # ``torch`` package の import 結果 (cuda 判定用キャッシュ).
    torch_available: bool | None = None
    cuda_available: bool | None = None


class MambaPyBackend(LLMBackend):
    """Mamba (SSM) in-process backend — skeleton.

    Args:
        model_filename: ``$LLIVE_DATA_DIR/mamba/`` 配下の重みファイル名.
            None なら :data:`DEFAULT_MODEL_FILENAME` を使う.
        weights_dir: 重みファイルを置くディレクトリ. None なら
            :func:`default_weights_dir` を使う.
        device: ``"cuda"`` / ``"cpu"``. Mamba は実質 CUDA 必須.
        dtype: ``"float16"`` / ``"bfloat16"`` / ``"float32"``.

    Raises:
        この時点では何も raise しない. 実エラーは ``load()`` /
        ``generate()`` 時点まで遅延する (lazy import + lazy load).
    """

    name = "mamba_py"
    DEFAULT_MODEL = "mamba-130m"

    def __init__(
        self,
        model_filename: str | None = None,
        *,
        weights_dir: Path | None = None,
        device: str | None = None,
        dtype: str | None = None,
        **kwargs: Any,
    ) -> None:
        # 余分な kwargs は将来拡張用に raw で保持しておく (例外は出さない).
        self._extra_kwargs: dict[str, Any] = dict(kwargs)
        self.weights_dir = Path(weights_dir) if weights_dir else default_weights_dir()
        self.model_filename = (
            model_filename
            or os.environ.get("LLIVE_MAMBA_MODEL_FILENAME")
            or DEFAULT_MODEL_FILENAME
        )
        self.device = device or os.environ.get("LLIVE_MAMBA_DEVICE") or DEFAULT_DEVICE
        self.dtype = dtype or os.environ.get("LLIVE_MAMBA_DTYPE") or DEFAULT_DTYPE
        self.model = self.DEFAULT_MODEL
        self._lazy = _LazyMambaModel(
            weights_path=self.weights_path,
            device=self.device,
            dtype=self.dtype,
        )

    # ------------------------------------------------------------------
    # Capability flags (RwkvPyBackend と同 shape)
    # ------------------------------------------------------------------
    @property
    def supports_vlm(self) -> bool:
        return False  # Mamba は text only (vision-mamba は別系統)

    @property
    def supports_coding(self) -> bool:
        # state-spaces/mamba は code corpus を含まない一般 LM.
        # CodeMamba 派生は出ているが skeleton では False で安全側.
        return False

    @property
    def supports_audio(self) -> bool:
        return False

    @property
    def supports_sensor(self) -> bool:
        return False

    @property
    def supports_prefix_embeddings(self) -> bool:
        # 原理的には可能 (Mamba は inputs_embeds 受け取り可) だが skeleton
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
    # Availability probing (新規追加 — task 指示の追加 method)
    # ------------------------------------------------------------------
    @classmethod
    def is_available(cls) -> bool:
        """``mamba_ssm`` package が import 可能かを bool で返す.

        CUDA 可否までは判定しない (環境変数や WSL2 経由でも変わるため).
        実際の generate ができるかは ``load()`` を呼ぶまで確定しない.
        """
        try:
            import mamba_ssm  # type: ignore[import-not-found]  # noqa: F401
        except Exception:  # ImportError or its variants
            return False
        return True

    def _probe_torch(self) -> tuple[bool, bool]:
        """``(torch_available, cuda_available)`` を 1 回だけ確認して cache.

        torch import 自体重いので skeleton では明示呼出時のみ実行.
        """
        if self._lazy.torch_available is not None and self._lazy.cuda_available is not None:
            return self._lazy.torch_available, self._lazy.cuda_available
        try:
            import torch  # type: ignore[import-not-found]
        except Exception:
            self._lazy.torch_available = False
            self._lazy.cuda_available = False
            return False, False
        self._lazy.torch_available = True
        try:
            self._lazy.cuda_available = bool(torch.cuda.is_available())
        except Exception:
            self._lazy.cuda_available = False
        return self._lazy.torch_available, self._lazy.cuda_available

    # ------------------------------------------------------------------
    # Lazy loading (task 指示: load() / _ensure_loaded() 兼用)
    # ------------------------------------------------------------------
    def load(self) -> None:
        """実 load. ``mamba_ssm`` が不在なら明確な RuntimeError.

        Raises:
            RuntimeError: ``mamba_ssm`` package が見つからない場合, または
                重みファイルが見つからない場合, または CUDA が使えない場合.
                メッセージで原因と troubleshooting hint を明示する.
        """
        self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        if self._lazy.loaded:
            return
        # 1) lazy import — ここで初めて mamba_ssm に触る
        try:
            import mamba_ssm  # type: ignore[import-not-found]  # noqa: F401
        except ImportError as exc:  # mamba_ssm package 未インストール
            self._lazy.import_error = exc
            raise RuntimeError(
                "Mamba not available: mamba_ssm package is not installed. "
                "Install with:  pip install mamba-ssm causal-conv1d  "
                "(requires CUDA 11.6+ / 12.x and Linux or WSL2; "
                "Windows native is not supported by the upstream kernel)."
            ) from exc

        # 2) 重みファイル存在チェック
        wp = self.weights_path
        if not wp.is_file():
            raise RuntimeError(
                f"Mamba not available: weights not found at {wp!s}. "
                "Place a Mamba checkpoint there, or set "
                "$LLIVE_DATA_DIR to a directory containing 'mamba/<filename>'. "
                "Suggested first model: "
                f"'{DEFAULT_MODEL_FILENAME}' from "
                "https://huggingface.co/state-spaces/mamba-130m."
            )

        # 3) torch + CUDA 可否 (Mamba は CUDA 必須)
        torch_ok, cuda_ok = self._probe_torch()
        if not torch_ok:
            raise RuntimeError(
                "Mamba not available: torch package is not installed. "
                "Install with:  pip install torch  "
                "(requires CUDA build for Mamba inference)."
            )
        if self.device.startswith("cuda") and not cuda_ok:
            raise RuntimeError(
                "Mamba not available: CUDA is not available but device=cuda was requested. "
                "Mamba requires CUDA (Triton kernel). Try WSL2 + CUDA 12.x, "
                "or set device='cpu' (note: most Mamba ops will still fail on CPU)."
            )

        # 4) 実 weight load — skeleton では未実装. 明示 NotImplementedError.
        raise NotImplementedError(
            "Mamba weight load skeleton — wire when WSL2/CUDA available. "
            "Expected next step: instantiate mamba_ssm.models.mixer_seq_simple.MambaLMHeadModel "
            f"from {wp!s} on device={self.device} dtype={self.dtype}."
        )

    # ------------------------------------------------------------------
    # Tokenizer (sentencepiece fallback — skeleton)
    # ------------------------------------------------------------------
    def _ensure_tokenizer(self) -> Any:
        """tokenizer を 1 回だけ用意. skeleton では未配線で None.

        実装時は GPT-NeoX tokenizer (state-spaces/mamba 公式) か
        sentencepiece モデルを読む.
        """
        if self._lazy.tokenizer is not None:
            return self._lazy.tokenizer
        # 実装は後続 PR. skeleton では明示 RuntimeError でも良いが,
        # tokenize()/detokenize() は単体テストしやすい shape にするため
        # 「load 未済なら RuntimeError」 を一貫させる.
        raise RuntimeError(
            "Mamba tokenizer not loaded. Call load() first "
            "(skeleton: tokenizer wiring deferred until WSL2/CUDA available)."
        )

    def tokenize(self, text: str) -> list[int]:
        """text → token id list. load 未済なら RuntimeError.

        Raises:
            RuntimeError: load() 未済もしくは tokenizer 未配線.
        """
        if not self._lazy.loaded:
            raise RuntimeError(
                "Mamba not loaded: call load() before tokenize(). "
                "(skeleton: actual tokenization deferred until weights load)."
            )
        tokenizer = self._ensure_tokenizer()
        return list(tokenizer.encode(text))  # pragma: no cover - skeleton

    def detokenize(self, ids: Iterable[int]) -> str:
        """token id list → text. load 未済なら RuntimeError.

        Raises:
            RuntimeError: load() 未済もしくは tokenizer 未配線.
        """
        if not self._lazy.loaded:
            raise RuntimeError(
                "Mamba not loaded: call load() before detokenize(). "
                "(skeleton: actual detokenization deferred until weights load)."
            )
        tokenizer = self._ensure_tokenizer()
        return str(tokenizer.decode(list(ids)))  # pragma: no cover - skeleton

    # ------------------------------------------------------------------
    # State management (task 指示の追加 method)
    # ------------------------------------------------------------------
    def state_dict(self) -> dict[str, Any]:
        """Mamba SSM の hidden state を serialise.

        skeleton では空 dict + metadata を返す. 実装時は
        ``model.state_dict()`` (torch) + 走行中の SSM state を含める.
        """
        return {
            "backend": self.name,
            "model": self.model,
            "weights_path": str(self.weights_path),
            "device": self.device,
            "dtype": self.dtype,
            "loaded": self._lazy.loaded,
            # skeleton: 実 weight tensor は含めない (load 未配線のため).
            "tensors": {},
        }

    def load_state_dict(self, state: dict[str, Any], *, strict: bool = True) -> None:
        """``state_dict()`` で出した dict を復元.

        skeleton では metadata だけ反映 (weights_path / device / dtype).
        実 tensor 復元は実装後.

        Args:
            state: ``state_dict()`` 由来 dict.
            strict: True なら必須キー欠如で KeyError, False なら無視.
        """
        if not isinstance(state, dict):
            raise TypeError(f"state_dict must be a dict, got {type(state).__name__}")
        required = {"backend", "model", "weights_path", "device", "dtype"}
        missing = required - set(state.keys())
        if missing and strict:
            raise KeyError(f"state_dict missing required keys: {sorted(missing)}")
        if "weights_path" in state:
            self._lazy.weights_path = Path(str(state["weights_path"]))
        if "device" in state:
            self.device = str(state["device"])
            self._lazy.device = self.device
        if "dtype" in state:
            self.dtype = str(state["dtype"])
            self._lazy.dtype = self.dtype
        if "model" in state:
            self.model = str(state["model"])
        # tensors の実復元は次フェーズ.

    # ------------------------------------------------------------------
    # Public generate API
    # ------------------------------------------------------------------
    def generate_text(self, prompt: str, max_tokens: int = 64) -> str:
        """簡易インタフェース — タスク指示通りの shape.

        既存 ``LLMBackend.generate(GenerateRequest)`` と並列に提供する.
        内部で ``GenerateRequest`` を組み立てる.

        Raises:
            RuntimeError: load 未済 / mamba_ssm 不在.
            NotImplementedError: load 済でも weight load 自体が skeleton.
        """
        req = GenerateRequest(prompt=prompt, max_tokens=int(max_tokens))
        return self.generate(req).text

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        """既存 ``LLMBackend`` interface — テキストのみ.

        Raises:
            RuntimeError: ``mamba_ssm`` package / weights / CUDA が無い場合.
            NotImplementedError: load 済でも weight load 自体が skeleton.
        """
        # load 済でなければ load 試行 (失敗時 RuntimeError or NotImplementedError).
        self._ensure_loaded()

        # ここに到達したら ``_ensure_loaded()`` が NotImplementedError を投げる
        # ので本来の generate ロジックは未着地. 念のため defence-in-depth で
        # 明示 RuntimeError.
        raise RuntimeError(  # pragma: no cover - _ensure_loaded が先に raise
            "Mamba generate path is a skeleton — weight load not wired yet."
        )
