# SPDX-License-Identifier: Apache-2.0
"""NoveltyLane — behavior-based novelty preservation (llive v0.F EV-15/16 柱 B).

v0.F 柱 B "Novelty Preservation" (要件 §B) の中核 substrate-agnostic
コンポーネント. ``diversity.NoveltyScorer`` が **genome value (パラメータ
空間)** 上の k-NN を計算するのに対し, 本モジュールは **behavior descriptor
(振る舞い空間)** 上の k-NN を計算する. Lehman & Stanley (2008/2011) の
novelty search の "behavioral diversity" 思想に近い.

主構成 (要件 §B-1〜B-3):

* :class:`NoveltyDescriptor` — 個体の振る舞いを固定次元 embedding で表現
* :class:`NoveltyScore` — 1 個体に対する k-NN 距離スコア (frozen)
* :func:`compute_novelty_scores` — 集団全体に対する k-NN novelty 計算
* :class:`MultiObjectiveSelector` — fitness top-N + novelty top-M ハイブリッド選択
  (要件 §B-1 デフォルト 0.6:0.4)

設計方針:

1. **substrate-agnostic** — embedding は任意次元 tuple. genome 値ベクトル,
   出力テキスト embedding, persona+skill bitmask hash, いずれにも適用可
2. **既存 NoveltyScorer (diversity.py) と共存** — file/namespace を完全分離.
   diversity.NoveltyScorer は genome 距離 + archive 蓄積, 本モジュールは
   behavior descriptor + 集団内瞬時計算
3. **frozen dataclass** — 履歴ログ用途で hash 可能 / immutable

References:

- Lehman & Stanley (2008/2011). Novelty Search.
- 要件: ``docs/requirements_v0.F_genome_two_layer_and_novelty.md`` §B.

Status (2026-05-22 着地): skeleton. データ構造 + k-NN 計算 + multi-objective
selection のみ. 実 EvolutionLoop 統合は EV-17 (Novelty Lane subprocess) 以降.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NoveltyDescriptor:
    """個体の振る舞い記述子 (substrate-agnostic behavior fingerprint).

    任意次元 embedding と補助 metadata を持つ. embedding 内容は呼び出し側が
    決める (genome 値, LLM 出力 embedding, persona+skill set の hash 等).

    Attributes
    ----------
    embedding : tuple[float, ...]
        固定次元 embedding (default 想定 32 dim, 任意次元可).
    metadata : tuple[tuple[str, str], ...]
        補助情報 (key, value) ペア tuple. 例: (("backend", "openai"),
        ("persona", "polya")). 距離計算には使わない.
    """

    embedding: tuple[float, ...]
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.embedding:
            raise ValueError("embedding must be non-empty")


@dataclass(frozen=True)
class NoveltyScore:
    """1 個体に対する k-NN 距離 novelty スコア.

    Attributes
    ----------
    individual_id : str
        個体識別子 (SHA-256 hash / UUID / 任意 ID).
    score : float
        集団内 k-NN 距離平均. 大きいほど novel.
    k : int
        実際に集約した k 値 (集団 size-1 と min を取った後の値).
    """

    individual_id: str
    score: float
    k: int


# ---------------------------------------------------------------------------
# k-NN novelty calculation
# ---------------------------------------------------------------------------


_SUPPORTED_DISTANCES = ("euclidean", "manhattan", "cosine")


def _pairwise_distance_matrix(
    embeddings: np.ndarray,
    distance: str,
) -> np.ndarray:
    """N×N 距離行列を返す. 自己距離は 0."""
    if distance == "euclidean":
        # (N, 1, D) - (1, N, D) → (N, N, D) → norm
        diff = embeddings[:, None, :] - embeddings[None, :, :]
        return np.linalg.norm(diff, axis=2)
    if distance == "manhattan":
        diff = embeddings[:, None, :] - embeddings[None, :, :]
        return np.abs(diff).sum(axis=2)
    if distance == "cosine":
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        # avoid divide-by-zero — zero vector → cosine 距離 1 (= 完全に異質扱い)
        safe_norms = np.where(norms > 0.0, norms, 1.0)
        normalized = embeddings / safe_norms
        sim = normalized @ normalized.T
        # 数値安定化のため clip
        sim = np.clip(sim, -1.0, 1.0)
        return 1.0 - sim
    raise ValueError(
        f"unsupported distance: {distance!r} "
        f"(expected one of {_SUPPORTED_DISTANCES})"
    )


def compute_novelty_scores(
    descriptors: list[tuple[str, NoveltyDescriptor]],
    k: int = 15,
    distance: str = "euclidean",
) -> list[NoveltyScore]:
    """集団全体に対する novelty スコアを計算する (k-NN 距離平均).

    各個体 i について, 自己を除く他個体との距離を sort し最近接 k 個の平均を
    novelty score とする. 集団サイズ N が k+1 未満の場合は ``k_use = N - 1``
    に自動 fallback. 全要素同一の embedding でも 0.0 (= 完全同質) を返すだけで
    例外は出さない.

    Parameters
    ----------
    descriptors : list[tuple[str, NoveltyDescriptor]]
        ``(individual_id, descriptor)`` ペアの list. 全 descriptor の
        ``embedding`` 次元は一致している必要がある.
    k : int
        k-NN の k. default 15 (要件 §B-1).
    distance : str
        距離関数. "euclidean" (default) / "manhattan" / "cosine".

    Returns
    -------
    list[NoveltyScore]
        入力と同じ順序の NoveltyScore list.

    Raises
    ------
    ValueError
        ``k < 1`` / descriptors が空 / embedding 次元が不揃い / 未対応 distance.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if not descriptors:
        return []
    if distance not in _SUPPORTED_DISTANCES:
        raise ValueError(
            f"unsupported distance: {distance!r} "
            f"(expected one of {_SUPPORTED_DISTANCES})"
        )

    n = len(descriptors)
    dim = len(descriptors[0][1].embedding)
    if dim == 0:
        raise ValueError("descriptor embedding must be non-empty")
    for ind_id, desc in descriptors:
        if len(desc.embedding) != dim:
            raise ValueError(
                f"embedding dimension mismatch: {ind_id} has "
                f"{len(desc.embedding)} dims, expected {dim}"
            )

    if n == 1:
        # 集団サイズ 1 → 比較対象がない. score=0.0, k=0 で返す.
        return [NoveltyScore(individual_id=descriptors[0][0], score=0.0, k=0)]

    embeddings = np.array(
        [desc.embedding for _, desc in descriptors], dtype=np.float64
    )
    dist_matrix = _pairwise_distance_matrix(embeddings, distance)

    # 自己距離 (対角) は除外したいので +inf に置く
    np.fill_diagonal(dist_matrix, np.inf)

    k_use = min(k, n - 1)
    # 各行で小さい順 k_use 個を取る. argpartition の方が速いが N=100 程度なら
    # sort で十分 & 読みやすい. skeleton 段階なので可読性優先.
    sorted_dists = np.sort(dist_matrix, axis=1)
    nearest_k = sorted_dists[:, :k_use]
    scores = nearest_k.mean(axis=1)

    return [
        NoveltyScore(individual_id=ind_id, score=float(scores[i]), k=k_use)
        for i, (ind_id, _) in enumerate(descriptors)
    ]


# ---------------------------------------------------------------------------
# Multi-objective selection (fitness top-N + novelty top-M)
# ---------------------------------------------------------------------------


@dataclass
class MultiObjectiveSelector:
    """fitness top-N + novelty top-M のハイブリッド選択 (要件 §B-1).

    既存 ``selection.TournamentSelection`` / ``RouletteSelection`` が単一目的
    (fitness のみ) なのに対し, 本 selector は **fitness 上位 N + novelty 上位 M**
    を非重複で結合する. 要件 §B-1 の "selection は (fitness top-N) + (novelty
    top-M) のハイブリッド (N:M = 0.6:0.4 default)" に対応.

    Attributes
    ----------
    n_fitness : int
        fitness top-N の N. 0 以上.
    m_novelty : int
        novelty top-M の M. 0 以上.

    Notes
    -----
    * 同一 ID が両 ranking に出る場合は **fitness ranking 側を優先** し,
      novelty ranking から除外する. 結果として返る list の長さは
      ``<= n_fitness + m_novelty``.
    * fitness ranking / novelty ranking はそれぞれ降順 (大きい方が優先).
    * 空 ranking でも例外は出さない (空 list を返す).
    """

    n_fitness: int
    m_novelty: int

    def __post_init__(self) -> None:
        if self.n_fitness < 0:
            raise ValueError(f"n_fitness must be >= 0, got {self.n_fitness}")
        if self.m_novelty < 0:
            raise ValueError(f"m_novelty must be >= 0, got {self.m_novelty}")

    def select(
        self,
        fitness_scores: dict[str, float],
        novelty_scores: dict[str, float],
    ) -> list[str]:
        """selected ID list を返す (順序: fitness top → novelty top, 重複除く).

        Parameters
        ----------
        fitness_scores : dict[str, float]
            ``individual_id → fitness`` (large is better).
        novelty_scores : dict[str, float]
            ``individual_id → novelty`` (large is better).

        Returns
        -------
        list[str]
            選択された individual_id の list. fitness top-N を先頭に置き,
            その後ろに novelty top-M (fitness 側と重複しないもの) を続ける.
        """
        # fitness ranking — 降順, 同点は ID 昇順で決定論的に
        fitness_ranking = sorted(
            fitness_scores.items(), key=lambda kv: (-kv[1], kv[0])
        )
        fitness_top = [
            ind_id for ind_id, _ in fitness_ranking[: self.n_fitness]
        ]
        fitness_top_set = set(fitness_top)

        # novelty ranking — 降順, fitness top と重複は除外
        novelty_ranking = sorted(
            novelty_scores.items(), key=lambda kv: (-kv[1], kv[0])
        )
        novelty_top: list[str] = []
        for ind_id, _ in novelty_ranking:
            if len(novelty_top) >= self.m_novelty:
                break
            if ind_id in fitness_top_set:
                continue
            novelty_top.append(ind_id)

        return fitness_top + novelty_top


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


__all__ = [
    "MultiObjectiveSelector",
    "NoveltyDescriptor",
    "NoveltyScore",
    "compute_novelty_scores",
]
