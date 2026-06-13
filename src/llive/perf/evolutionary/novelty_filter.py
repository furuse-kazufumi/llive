# SPDX-License-Identifier: Apache-2.0
"""NoveltyFilter — ShinkaEvolve 流 *評価前* novelty-based rejection (T2 2-2).

ShinkaEvolve (arXiv:2509.19349, ICLR 2026) の中核機構の 1 つ
``novelty rejection-sampling`` を llive の進化ループに移植したもの。

中学生向けに言うと——進化では「新しく作った変異の良し悪しを測る」のに **LLM を
呼ぶ** から、これが一番お金 (時間) のかかる工程。だから測る *前* に、既に測った
ものとそっくりな変異は「どうせ似た点数だろう」と判断して **測らずに捨てる**。
これで限られた評価予算を有望な変異に集中できる。

本 module は llive 進化ループの「**評価 (fitness 呼び出し) の直前**」に挿す
optional な間引きフィルタである。

設計の要点
----------
* **評価前 rejection** — 既に :class:`NoveltyFilter` が見た (= 評価に回した)
  個体の表現を保持し、新候補の最大類似度が ``threshold`` を超えたら
  ``reject`` を返す。``reject`` された候補は LLM 評価を **スキップ** できる
  ので、評価コスト (= 進化の最大ボトルネック; 15h marathon の確定教訓) を節約
  する。既存の :class:`~llive.perf.evolutionary.diversity.DiversityPreservingBreedFilter`
  が「breed 時に reject+**resample**」なのに対し、本 filter は「**評価**時に
  reject (= スキップして淘汰)」であり、節約対象が異なる (前者は多様性確保、
  後者は評価コスト削減)。

* **表現の選択 (Optional extras 哲学を厳守)**
  - 既定 = **genome flat vector の cosine 類似** (numpy のみ)。
    :func:`~llive.perf.evolutionary.genome_3d.genome_flat_vector` で flat
    :class:`Genome` / :class:`Genome3D` の双方を数値ベクトル化する。
  - テキスト変異 (プロンプト等) 用に **hashing n-gram ベクトル化 (stdlib
    only)** の fallback を内蔵。``encoder="text"`` で有効化。
  - sentence-transformers 等の重い embedding は **optional extra** とし、
    遅延 import + 失敗時は既定にフォールバックする (``encoder="st"``)。
    重依存の必須化はしない (基本機能は stdlib + numpy で動く)。

* **fail-open を明記** — 本 filter は **効率最適化であって安全ゲートではない**。
  証明・採用の安全判断は llcore の証明ゲートの役割であり、本 filter は
  「探索を速くするためのふるい」に過ぎない (G15 二層倫理: 探索は自由・採用は
  仁)。ベクトル化不能・依存欠落・想定外の例外が起きたら、候補は **accept
  (素通し)** する。フィルタが壊れても進化は止まらず、最悪でも「従来どおり
  全部評価する」だけになる (fail-open)。

* **統計 API** — :class:`FilterStats` で 受理 / 棄却 / fail-open / 節約評価数
  を取得できる。「棄却で節約した評価コスト > 判定器のコスト」を実測で確認
  する honest disclosure ([[feedback_benchmark_honest_disclosure]]) のための
  計測点。

honest な限界
-------------
genome cosine 類似は「**genome 空間の近さ**」であって「**振る舞い (出力) の
新規性**」とは厳密には一致しない。同じ genome 近傍でも fitness 地形が急峻なら
振る舞いは大きく違いうるし、逆に遠い genome が似た振る舞いを生むこともある。
ShinkaEvolve は加えて LLM-as-novelty-judge を併用するが、それは別途高コストな
ので本移植では **数値ベクトル類似のみ** を既定にした (judge は将来拡張)。
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from llive.perf.evolutionary.genome_3d import genome_flat_vector
from llive.perf.evolutionary.individual import Individual

EncoderName = Literal["genome", "text", "st"]


# ---------------------------------------------------------------------------
# 統計
# ---------------------------------------------------------------------------


@dataclass
class FilterStats:
    """:class:`NoveltyFilter` の累積統計.

    Attributes
    ----------
    accepted : int
        評価に回した (= novel と判定した) 候補数。
    rejected : int
        評価せずに棄却した (= 既存と類似した) 候補数。これがそのまま
        **節約された評価回数** (``saved_evaluations``) になる。
    failed_open : int
        ベクトル化不能 / 依存欠落 / 例外で fail-open (素通し accept) した数。
        ``accepted`` の内数ではなく **独立カウント** (accept でもあるが、
        「正常に novel 判定した accept」と「fail-open で素通しした accept」を
        区別したいので別に数える)。
    seen : int
        参照アーカイブに登録済みの個体表現数 (= これまで accept した数)。
    """

    accepted: int = 0
    rejected: int = 0
    failed_open: int = 0
    seen: int = 0

    @property
    def total(self) -> int:
        """フィルタを通過させた総候補数 (accepted + rejected)."""
        return self.accepted + self.rejected

    @property
    def saved_evaluations(self) -> int:
        """棄却によって節約された評価 (LLM 呼び出し) 回数 = ``rejected``."""
        return self.rejected

    @property
    def rejection_rate(self) -> float:
        """棄却率 = rejected / total (total=0 なら 0.0)."""
        return self.rejected / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": int(self.accepted),
            "rejected": int(self.rejected),
            "failed_open": int(self.failed_open),
            "seen": int(self.seen),
            "total": int(self.total),
            "saved_evaluations": int(self.saved_evaluations),
            "rejection_rate": float(self.rejection_rate),
        }


# ---------------------------------------------------------------------------
# テキストエンコーダ (stdlib only)
# ---------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def hashing_ngram_vector(
    text: str,
    *,
    dim: int = 256,
    ngram: int = 3,
) -> np.ndarray:
    """テキストを hashing trick で固定長 L2 正規化ベクトルにする (stdlib only).

    char n-gram と word token を Python 組込 :func:`hash` ではなく
    deterministic な :func:`hashlib`-free の積和ハッシュでバケットに割当てる
    (プロセス間で再現するよう ``hash()`` の salt を避ける)。sentence-transformers
    等が無い環境でも **テキスト変異の類似度** を測れる軽量 fallback。

    Parameters
    ----------
    text : str
        対象テキスト。
    dim : int
        出力ベクトル次元 (ハッシュバケット数)。default 256。
    ngram : int
        文字 n-gram の n。default 3。

    Returns
    -------
    np.ndarray
        shape ``(dim,)`` の L2 正規化済み float64 ベクトル (空文字なら 0 ベクトル)。
    """
    vec = np.zeros(dim, dtype=np.float64)
    if not text:
        return vec
    lowered = text.lower()

    def _bucket(token: str) -> int:
        # FNV-1a 風の deterministic hash (Python の salt 付き hash() を避ける)。
        h = 0x811C9DC5
        for ch in token:
            h ^= ord(ch)
            h = (h * 0x01000193) & 0xFFFFFFFF
        return h % dim

    # word tokens
    for tok in _TOKEN_RE.findall(lowered):
        vec[_bucket(tok)] += 1.0
    # char n-grams (語順・部分一致を捉える)
    if ngram > 0 and len(lowered) >= ngram:
        for i in range(len(lowered) - ngram + 1):
            vec[_bucket(lowered[i : i + ngram])] += 1.0

    norm = float(np.linalg.norm(vec))
    if norm > 0.0:
        vec /= norm
    return vec


def _cosine_max(candidate: np.ndarray, archive: np.ndarray) -> float:
    """candidate と archive 各行の cosine 類似の **最大値** を返す.

    archive が空なら -inf (= どれにも似ていない → 必ず accept)。ゼロベクトルは
    cosine 未定義なので類似度 0.0 とみなす (安全側 = accept されやすい)。
    """
    if archive.shape[0] == 0:
        return float("-inf")
    cand_norm = float(np.linalg.norm(candidate))
    if cand_norm == 0.0:
        return 0.0
    arch_norms = np.linalg.norm(archive, axis=1)
    safe = arch_norms > 0.0
    if not safe.any():
        return 0.0
    sims = (archive[safe] @ candidate) / (arch_norms[safe] * cand_norm)
    return float(np.max(sims))


# ---------------------------------------------------------------------------
# NoveltyFilter
# ---------------------------------------------------------------------------


@dataclass
class NoveltyFilter:
    """評価前 novelty-based rejection フィルタ (ShinkaEvolve 流).

    使い方は 2 通り:

    1. **個別判定** — :meth:`accepts` で 1 候補を判定し、accept したものだけ
       評価に回す。accept された候補は内部アーカイブに自動登録される。
    2. **ループ統合** — :class:`~llive.perf.evolutionary.loop.EvolutionLoop`
       の ``novelty_filter`` 引数に渡すと、各世代の評価直前に自動適用される
       (棄却個体は LLM 評価をスキップして淘汰)。

    Attributes
    ----------
    threshold : float
        cosine 類似度の棄却閾値。新候補の (アーカイブ中) 最大類似度が
        ``threshold`` を **超えたら棄却**。``[0, 1]`` 推奨 (1.0 で「完全一致
        のみ棄却」、低いほど積極的に棄却)。default 0.95。
    encoder : {"genome", "text", "st"}
        表現の選び方。``"genome"`` (default) = genome flat vector の cosine。
        ``"text"`` = ``text_of`` で取り出した文字列を hashing n-gram 化。
        ``"st"`` = sentence-transformers (optional, 遅延 import; 失敗時は
        ``"text"`` 相当に自動フォールバック)。
    text_of : Callable[[Individual], str] | None
        ``encoder in {"text", "st"}`` のときに個体からテキストを取り出す関数。
        ``None`` なら ``str(individual.genome)`` を使う。
    archive_max_size : int
        参照アーカイブ上限。超過は FIFO で古いものを破棄 (default 2000)。
    text_dim : int
        ``"text"`` encoder の hashing 次元 (default 256)。
    text_ngram : int
        ``"text"`` encoder の char n-gram の n (default 3)。
    st_model_name : str
        ``"st"`` encoder のモデル名 (default ``"all-MiniLM-L6-v2"``)。
    stats : FilterStats
        累積統計 (自動更新)。
    """

    threshold: float = 0.95
    encoder: EncoderName = "genome"
    text_of: Callable[[Individual], str] | None = None
    archive_max_size: int = 2000
    text_dim: int = 256
    text_ngram: int = 3
    st_model_name: str = "all-MiniLM-L6-v2"
    stats: FilterStats = field(default_factory=FilterStats)

    # 内部状態 (init=False)
    _archive: deque[np.ndarray] = field(default_factory=deque, init=False, repr=False)
    _st_model: Any | None = field(default=None, init=False, repr=False)
    _st_failed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"threshold must be in [0, 1], got {self.threshold}")
        if self.archive_max_size < 1:
            raise ValueError("archive_max_size must be >= 1")
        if self.encoder not in ("genome", "text", "st"):
            raise ValueError(f"unknown encoder: {self.encoder!r}")

    # -- encoding ---------------------------------------------------------

    def _encode(self, individual: Individual) -> np.ndarray | None:
        """個体を表現ベクトルにする. 失敗時は ``None`` (→ fail-open accept).

        例外・依存欠落は **握り潰して None** を返す (fail-open: 効率最適化で
        あって安全ゲートではないため、フィルタ不能なら素通しする)。
        """
        try:
            if self.encoder == "genome":
                return np.asarray(genome_flat_vector(individual.genome), dtype=np.float64)
            text = self.text_of(individual) if self.text_of else str(individual.genome)
            if self.encoder == "st":
                vec = self._encode_st(text)
                if vec is not None:
                    return vec
                # st 失敗 → text fallback
            return hashing_ngram_vector(text, dim=self.text_dim, ngram=self.text_ngram)
        except Exception:
            # ベクトル化不能 — fail-open (accept)
            return None

    def _encode_st(self, text: str) -> np.ndarray | None:
        """sentence-transformers で encode. 遅延 import; 失敗時は ``None``.

        一度 import / load に失敗したら ``_st_failed`` を立てて以降は試みない
        (毎回 import 例外を踏むコストを避ける)。
        """
        if self._st_failed:
            return None
        if self._st_model is None:
            try:
                from sentence_transformers import SentenceTransformer  # noqa: PLC0415

                self._st_model = SentenceTransformer(self.st_model_name)
            except Exception:
                self._st_failed = True
                return None
        try:
            vec = self._st_model.encode([text])[0]
            return np.asarray(vec, dtype=np.float64)
        except Exception:
            self._st_failed = True
            return None

    # -- archive ----------------------------------------------------------

    def _add_to_archive(self, vec: np.ndarray) -> None:
        self._archive.append(np.asarray(vec, dtype=np.float64).copy())
        while len(self._archive) > self.archive_max_size:
            self._archive.popleft()
        self.stats.seen = len(self._archive)

    def _archive_matrix(self) -> np.ndarray:
        if not self._archive:
            return np.empty((0, 0), dtype=np.float64)
        # 次元が混在しない前提 (1 run 内は homogeneous)。混在したら最後の dim に
        # 合うものだけ使う (fail-open 寄り) — 通常は起きない。
        return np.stack(list(self._archive), axis=0)

    # -- public: 1 候補判定 -----------------------------------------------

    def accepts(self, individual: Individual) -> bool:
        """1 候補を判定する. accept なら ``True`` (= 評価に回すべき).

        accept した候補はアーカイブに登録され、以後の候補の比較対象になる。
        reject した候補は登録しない (評価しない個体は「既知の良い解」を構成
        しないため、参照点に加えると誤って後続を棄却し続けるのを避ける)。

        fail-open: ベクトル化不能 / archive 比較不能のときは accept する
        (ただし統計上 ``failed_open`` を増やし、登録もする — 次回以降の参照点に
        はなるよう、ベクトルが取れていれば登録する)。
        """
        vec = self._encode(individual)
        if vec is None or vec.size == 0:
            # fail-open: 表現が取れない → 素通し (accept)。登録はできない。
            self.stats.accepted += 1
            self.stats.failed_open += 1
            return True

        archive = self._archive_matrix()
        try:
            if archive.shape[0] > 0 and archive.shape[1] != vec.shape[0]:
                # 次元不一致 (想定外) — fail-open accept + 登録
                self.stats.accepted += 1
                self.stats.failed_open += 1
                self._add_to_archive(vec)
                return True
            max_sim = _cosine_max(vec, archive)
        except Exception:
            # 比較中の予期せぬ例外 — fail-open accept + 登録
            self.stats.accepted += 1
            self.stats.failed_open += 1
            self._add_to_archive(vec)
            return True

        if max_sim > self.threshold:
            # 既存と類似 → 評価せず棄却 (登録しない)
            self.stats.rejected += 1
            return False

        # novel → accept + 登録
        self.stats.accepted += 1
        self._add_to_archive(vec)
        return True

    def partition(
        self, individuals: Sequence[Individual]
    ) -> tuple[list[Individual], list[Individual]]:
        """候補列を (accepted, rejected) に分割する.

        各候補を :meth:`accepts` で順に判定する (順序依存: 先に来た novel 個体が
        後続の参照点になる)。

        Returns
        -------
        tuple[list[Individual], list[Individual]]
            ``(accepted, rejected)``。``accepted`` が評価に回すべき個体、
            ``rejected`` が評価をスキップして淘汰すべき個体。
        """
        accepted: list[Individual] = []
        rejected: list[Individual] = []
        for ind in individuals:
            (accepted if self.accepts(ind) else rejected).append(ind)
        return accepted, rejected

    def reset(self) -> None:
        """アーカイブと統計をクリアする (run 再利用時)."""
        self._archive.clear()
        self.stats = FilterStats()
        self._st_model = None
        self._st_failed = False


__all__ = [
    "EncoderName",
    "FilterStats",
    "NoveltyFilter",
    "hashing_ngram_vector",
]
