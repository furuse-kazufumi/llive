# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-02 拡張テスト — embedding semantic similarity.

期待する振る舞い:
- similarity_fn が None なら従来 token match のみで採点 (回帰無し).
- similarity_fn が注入されていれば token match との max を採点に使う.
- similarity_fn が例外を投げても token match で fallback.
- EmbeddingSimilarityFn は MemoryEncoder で cosine 類似度を返す.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest

from llive.cognitive_mesh.embedding_similarity import EmbeddingSimilarityFn
from llive.cognitive_mesh.title_recall import (
    RecallStatus,
    TitleRecallPlanner,
)


class _FakeEncoder:
    """encode([a, b]) -> 2 ベクトル. 同じテキストは同方向."""

    def __init__(self, vectors: dict[str, list[float]]):
        self._vectors = {k: np.asarray(v, dtype=np.float32) for k, v in vectors.items()}

    def encode(self, texts):  # noqa: ANN001
        return np.stack([self._vectors[t] for t in texts], axis=0)


def test_default_uses_token_match_only() -> None:
    planner = TitleRecallPlanner()
    planner.setup(text="build success", tag="t1")
    report = planner.evaluate("the build success was announced")
    assert report.recall_rate == pytest.approx(1.0)
    assert planner.all_foreshadows()[0].status == RecallStatus.RECOVERED


def test_default_misses_when_no_token_match() -> None:
    planner = TitleRecallPlanner()
    planner.setup(text="alpha beta gamma", tag="t1")
    report = planner.evaluate("totally unrelated content")
    assert report.recall_rate == pytest.approx(0.0)
    assert planner.all_foreshadows()[0].status == RecallStatus.MISSED


def test_similarity_fn_recovers_when_tokens_miss() -> None:
    """token match で取れないケースを embedding 類似度で拾う."""
    # token 共有なし
    fs_text = "ベンチ品質"
    final_text = "計測精度"
    # token match では 0 のはずだが、similarity_fn が 0.9 を返せば recovered
    sim_fn: Callable[[str, str], float] = lambda a, b: 0.9 if (a, b) == (fs_text, final_text) else 0.0
    planner = TitleRecallPlanner(similarity_fn=sim_fn)
    planner.setup(text=fs_text, tag="t1")
    report = planner.evaluate(final_text)
    assert planner.all_foreshadows()[0].status == RecallStatus.RECOVERED
    # similarity スコアが採点 (token は 0)
    assert report.recovered_weight == pytest.approx(0.9)


def test_similarity_fn_exception_falls_back_to_token() -> None:
    def bad_sim(a: str, b: str) -> float:
        raise RuntimeError("encoder unavailable")

    planner = TitleRecallPlanner(similarity_fn=bad_sim)
    planner.setup(text="build success", tag="t1")
    # token match (build success) は完全一致で recover
    report = planner.evaluate("the build success was announced")
    assert planner.all_foreshadows()[0].status == RecallStatus.RECOVERED
    assert report.recall_rate == pytest.approx(1.0)


def test_similarity_fn_clipped_to_unit_interval() -> None:
    """similarity_fn が範囲外を返しても [0, 1] に clip."""
    planner = TitleRecallPlanner(similarity_fn=lambda a, b: 1.5)
    planner.setup(text="xyz", tag="t1")
    report = planner.evaluate("unrelated")
    # 1.5 は 1.0 に clip、recovered_weight も 1.0
    assert report.recovered_weight == pytest.approx(1.0)


def test_similarity_fn_max_with_token() -> None:
    """token match の方が高いケースは token を採用."""
    planner = TitleRecallPlanner(similarity_fn=lambda a, b: 0.2)
    planner.setup(text="alpha", tag="t1")
    # "alpha" の token match は 1.0
    report = planner.evaluate("alpha is here")
    assert report.recovered_weight == pytest.approx(1.0)


def test_embedding_similarity_fn_with_fake_encoder() -> None:
    """EmbeddingSimilarityFn が cosine sim を [0, 1] で返す."""
    encoder = _FakeEncoder(
        {
            "x": [1.0, 0.0, 0.0],
            "y": [1.0, 0.0, 0.0],  # 完全一致
            "z": [0.0, 1.0, 0.0],  # 直交
            "w": [-1.0, 0.0, 0.0],  # 反対方向
        }
    )
    sim_fn = EmbeddingSimilarityFn(encoder=encoder)  # type: ignore[arg-type]
    assert sim_fn("x", "y") == pytest.approx(1.0)
    assert sim_fn("x", "z") == pytest.approx(0.0)
    # 負方向は 0 に clip
    assert sim_fn("x", "w") == pytest.approx(0.0)


def test_embedding_similarity_fn_handles_zero_vector() -> None:
    encoder = _FakeEncoder({"a": [0.0, 0.0, 0.0], "b": [1.0, 0.0, 0.0]})
    sim_fn = EmbeddingSimilarityFn(encoder=encoder)  # type: ignore[arg-type]
    assert sim_fn("a", "b") == 0.0


def test_embedding_similarity_fn_failclosed_on_encoder_exception() -> None:
    class BadEncoder:
        def encode(self, texts):  # noqa: ANN001
            raise RuntimeError("boom")

    sim_fn = EmbeddingSimilarityFn(encoder=BadEncoder())  # type: ignore[arg-type]
    assert sim_fn("a", "b") == 0.0
