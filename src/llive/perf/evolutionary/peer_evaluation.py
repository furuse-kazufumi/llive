# SPDX-License-Identifier: Apache-2.0
"""PeerEvaluationMatrix — llive v0.E CE-01 (skeleton).

派生集団内で **個体 i が個体 j を採点した結果** を 2D 行列 ``M[i, j]``
として保持し, 集約 (row mean / column mean / weighted) で **peer-derived
fitness** を計算する dataclass.

設計判断:

- 採点者 (i) と被採点者 (j) は **同じ集団** を仮定 (n×n 正方).
- ``M[i, i]`` (自己採点) は default で NaN → 集約時に除外.
- 集約は ``column_mean`` (= 自分が他者から受けた点の平均) を default に.
- 共謀検出は ``collusion_score()`` で row variance / off-diagonal symmetry
  / score concentration を 3 指標として返す.
- Mermaid 可視化 (``render_mermaid``) で agent 間の peer flow を見える化.

実 LLM peer 評価は credential 後. 本 skeleton では:
- ``record(i_id, j_id, score)`` で 1 つの採点を埋める
- aggregate / collusion / mermaid を提供
- AI judge / external evaluator はこの dataclass の上に乗る

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` CE-01/03/06.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

from llive.perf.evolutionary.individual import FitnessReport, Individual


@dataclass
class PeerEvaluationMatrix:
    """N 体集団の peer evaluation matrix.

    Attributes
    ----------
    agent_ids : tuple[str, ...]
        集団の個体 id 列. index は ``agent_ids.index(id)`` で求まる.
    matrix : np.ndarray
        ``(N, N)`` の 2D float array. ``M[i, j]`` は agent i が agent j を
        採点した score. 未採点は NaN.
    signed_by : str
        この matrix を生成した evaluator の id (Ed25519 署名は将来 SEC-02).
    generation : int
        どの世代の評価か.
    metadata : dict[str, Any]
        追加情報 (タスク id / 評価軸 / etc.).
    """

    agent_ids: tuple[str, ...]
    matrix: np.ndarray
    signed_by: str = ""
    generation: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = len(self.agent_ids)
        if self.matrix.shape != (n, n):
            raise ValueError(
                f"matrix shape {self.matrix.shape} != ({n}, {n}). "
                f"agent_ids len = {n}"
            )

    # ---------- public API ----------------------------------------------

    @classmethod
    def empty(
        cls,
        agent_ids: Iterable[str],
        *,
        signed_by: str = "",
        generation: int = 0,
    ) -> PeerEvaluationMatrix:
        """全 NaN の N×N matrix を作る."""
        ids = tuple(agent_ids)
        n = len(ids)
        m = np.full((n, n), np.nan, dtype=np.float64)
        return cls(
            agent_ids=ids, matrix=m, signed_by=signed_by, generation=generation
        )

    def record(self, evaluator_id: str, target_id: str, score: float) -> None:
        """1 つの採点を記録. evaluator が target に対して score を付ける."""
        i = self.agent_ids.index(evaluator_id)
        j = self.agent_ids.index(target_id)
        self.matrix[i, j] = float(score)

    def column_mean(self, *, exclude_self: bool = True) -> np.ndarray:
        """各 agent が **他者から** 受けた score の平均 (列平均).

        ``exclude_self=True`` (default) なら対角 (自己採点) を除外.

        Returns
        -------
        np.ndarray shape (N,)
            agent_ids 順. 未評価は NaN.
        """
        m = self.matrix.copy()
        if exclude_self:
            np.fill_diagonal(m, np.nan)
        with np.errstate(invalid="ignore"):
            return np.nanmean(m, axis=0)

    def row_mean(self, *, exclude_self: bool = True) -> np.ndarray:
        """各 agent が **他者を** 採点した平均 (行平均).

        評価者が「全体的に高得点を出す甘口」「低得点を出す辛口」の特性を
        持つかを見るのに使う.
        """
        m = self.matrix.copy()
        if exclude_self:
            np.fill_diagonal(m, np.nan)
        with np.errstate(invalid="ignore"):
            return np.nanmean(m, axis=1)

    # ---------- aggregations to FitnessReport ----------------------------

    def to_fitness_reports(
        self,
        *,
        score_aggregator: str = "column_mean",
        nan_fill: float = 0.0,
    ) -> dict[str, FitnessReport]:
        """agent_id → FitnessReport の dict を返す.

        ``score_aggregator``:
            - ``column_mean``: 自分が他者から受けた score の平均 (default)
            - ``row_mean``: 自分が他者に与えた score の平均
            - ``column_minus_row``: column - row (甘口バイアス補正)
        """
        if score_aggregator == "column_mean":
            scores = self.column_mean()
        elif score_aggregator == "row_mean":
            scores = self.row_mean()
        elif score_aggregator == "column_minus_row":
            scores = self.column_mean() - self.row_mean()
        else:
            raise ValueError(f"unknown score_aggregator: {score_aggregator!r}")

        # NaN を nan_fill で埋める
        scores = np.where(np.isnan(scores), nan_fill, scores)
        result: dict[str, FitnessReport] = {}
        for i, aid in enumerate(self.agent_ids):
            result[aid] = FitnessReport(
                score=float(scores[i]),
                breakdown={
                    "peer_score": float(scores[i]),
                    "peer_score_var": float(
                        np.nanvar(np.delete(self.matrix[:, i], i))
                        if len(self.agent_ids) > 1
                        else 0.0
                    ),
                },
                runtime_metadata={"signed_by": self.signed_by},
                notes=(
                    f"peer_evaluation gen={self.generation} "
                    f"agg={score_aggregator}"
                ),
            )
        return result

    # ---------- collusion detection ------------------------------------

    def collusion_score(self) -> dict[str, float]:
        """共謀リスクの 3 指標を返す.

        - ``score_variance``: 全 off-diagonal score の分散. **低い**ほど
          「全員が同じ点をつける = 共謀疑い".
        - ``symmetry``: ``corr(M, M.T)``. **高い**ほど 「i↔j で点を交換する
          = 互酬共謀疑い".
        - ``concentration``: column_mean の top-1 / mean. **低い**ほど
          「全員が高得点 = 嘘の評価」.
        """
        m = self.matrix.copy()
        np.fill_diagonal(m, np.nan)
        valid = ~np.isnan(m)
        if not valid.any():
            return {"score_variance": 0.0, "symmetry": 0.0, "concentration": 0.0}
        score_variance = float(np.nanvar(m))

        # symmetry
        m_flat = m[valid]
        m_t = m.T
        m_t_flat = m_t[valid]
        if len(m_flat) >= 2 and np.nanstd(m_flat) > 1e-12 and np.nanstd(m_t_flat) > 1e-12:
            symmetry = float(np.corrcoef(m_flat, m_t_flat)[0, 1])
        else:
            symmetry = 0.0

        # concentration: top-1 / mean (col mean)
        col_mean = self.column_mean()
        col_valid = col_mean[~np.isnan(col_mean)]
        if len(col_valid) > 0 and col_valid.mean() > 1e-12:
            concentration = float(col_valid.max() / col_valid.mean())
        else:
            concentration = 0.0

        return {
            "score_variance": score_variance,
            "symmetry": symmetry,
            "concentration": concentration,
        }

    def is_suspected_collusion(
        self,
        *,
        variance_threshold: float = 1e-3,
        symmetry_threshold: float = 0.8,
        concentration_floor: float = 1.05,
    ) -> bool:
        """3 指標から共謀疑い判定. 1 つでも該当すれば True."""
        s = self.collusion_score()
        return (
            s["score_variance"] < variance_threshold
            or s["symmetry"] > symmetry_threshold
            or s["concentration"] < concentration_floor
        )

    # ---------- serialization ------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_ids": list(self.agent_ids),
            "matrix": self.matrix.tolist(),
            "signed_by": self.signed_by,
            "generation": int(self.generation),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PeerEvaluationMatrix:
        return cls(
            agent_ids=tuple(data["agent_ids"]),
            matrix=np.asarray(data["matrix"], dtype=np.float64),
            signed_by=str(data.get("signed_by", "")),
            generation=int(data.get("generation", 0)),
            metadata=dict(data.get("metadata", {})),
        )

    def write_jsonl(self, path: Path | str, *, append: bool = True) -> None:
        """1 行 JSON で書き出し (世代間の append 蓄積 OK)."""
        line = json.dumps(self.to_dict(), ensure_ascii=False)
        mode = "a" if append else "w"
        with open(path, mode, encoding="utf-8") as fh:
            fh.write(line + "\n")

    # ---------- visualization ------------------------------------------

    def render_mermaid(self, *, top_k_edges: int = 0) -> str:
        """agent 間の peer score を Mermaid graph LR で表現.

        ``top_k_edges > 0`` で score 上位 k 本のエッジに絞る.
        """
        lines = ["graph LR"]
        edges: list[tuple[float, str, str]] = []
        n = len(self.agent_ids)
        for i in range(n):
            for j in range(n):
                if i == j or np.isnan(self.matrix[i, j]):
                    continue
                edges.append((float(self.matrix[i, j]), self.agent_ids[i], self.agent_ids[j]))
        if top_k_edges > 0:
            edges.sort(reverse=True, key=lambda x: x[0])
            edges = edges[:top_k_edges]
        for score, i_id, j_id in edges:
            label = f"{score:.2f}"
            lines.append(f'    {i_id} -- "{label}" --> {j_id}')
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# PeerFitnessAdapter — EvolutionLoop の fitness_fn を peer-based に置換
# ---------------------------------------------------------------------------


PairScoreFn = Callable[[Individual, Individual], float]


@dataclass
class PeerFitnessAdapter:
    """``EvolutionLoop`` の scheduler-style API を peer evaluation で実装.

    pair_score_fn(evaluator, target) を全 i×j で呼び出し
    PeerEvaluationMatrix を構築 → column_mean を FitnessReport にして
    返す.

    ``EvolutionLoop`` の ``scheduler`` slot に差し込んで使う設計 (1 個体内
    の fitness_fn ではなく **集団全体** の評価):

    .. code-block:: python

        adapter = PeerFitnessAdapter(pair_score_fn=my_pairwise)
        loop = EvolutionLoop(
            fitness_fn=placeholder,  # adapter 使うので不要
            scheduler=adapter,
        )

    Attributes
    ----------
    pair_score_fn : PairScoreFn
        ``(evaluator: Individual, target: Individual) -> float``
    score_aggregator : str
        ``column_mean`` (default) / ``row_mean`` / ``column_minus_row``
    include_self : bool
        ``True`` なら自己採点も pair_score_fn に依頼 (default False).
    matrix_jsonl_path : Path | None
        指定すれば世代ごとに PeerEvaluationMatrix を JSONL append.
    signed_by : str
        生成 matrix の signed_by フィールド.
    generation_counter : list[int]
        内部 counter (世代ごとに +1). default [0].
    """

    pair_score_fn: PairScoreFn
    score_aggregator: str = "column_mean"
    include_self: bool = False
    matrix_jsonl_path: Path | None = None
    signed_by: str = ""
    generation_counter: list[int] = field(default_factory=lambda: [0])

    def __call__(
        self,
        fitness_fn: Callable[..., Any],  # noqa: ARG002 — placeholder, unused
        individuals: Iterable[Individual],
    ) -> list[FitnessReport]:
        inds = list(individuals)
        ids = tuple(ind.individual_id for ind in inds)
        matrix = PeerEvaluationMatrix.empty(
            ids,
            signed_by=self.signed_by,
            generation=self.generation_counter[0],
        )
        for evaluator in inds:
            for target in inds:
                if not self.include_self and evaluator.individual_id == target.individual_id:
                    continue
                score = float(self.pair_score_fn(evaluator, target))
                matrix.record(evaluator.individual_id, target.individual_id, score)
        if self.matrix_jsonl_path is not None:
            matrix.write_jsonl(self.matrix_jsonl_path, append=True)
        self.generation_counter[0] += 1
        reports_by_id = matrix.to_fitness_reports(score_aggregator=self.score_aggregator)
        return [reports_by_id[ind.individual_id] for ind in inds]


__all__ = [
    "PairScoreFn",
    "PeerEvaluationMatrix",
    "PeerFitnessAdapter",
]
