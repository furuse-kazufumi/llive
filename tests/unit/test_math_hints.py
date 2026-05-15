# SPDX-License-Identifier: Apache-2.0
"""Mathematical Toolkit (math_hints) の単体テスト."""

from __future__ import annotations

from pathlib import Path

from llive.memory.rad import RadCorpusIndex
from llive.memory.rad.math_hints import (
    MathHintBundle,
    gather_hints,
    list_chapters,
)


def _build_mini_rad(tmp_path: Path) -> RadCorpusIndex:
    root = tmp_path / "rad"
    root.mkdir()
    (root / "multivariate_analysis_corpus_v2").mkdir()
    (root / "multivariate_analysis_corpus_v2" / "manifold.md").write_text(
        "Manifold learning approximates high-dim data by a low-dim manifold "
        "(UMAP, t-SNE preserve local neighborhood).\n",
        encoding="utf-8",
    )
    (root / "optimization_corpus_v2").mkdir()
    (root / "optimization_corpus_v2" / "gd.md").write_text(
        "Gradient descent is the workhorse optimizer for convex problems.\n",
        encoding="utf-8",
    )
    return RadCorpusIndex(root=root)


def test_list_chapters_includes_known() -> None:
    chapters = list(list_chapters())
    assert "tlb_bridge" in chapters
    assert "apo_optimizer" in chapters
    assert "f6_time_horizon" in chapters


def test_gather_hints_for_known_chapter(tmp_path: Path) -> None:
    idx = _build_mini_rad(tmp_path)
    bundle = gather_hints(idx, "tlb_bridge", "manifold learning")
    assert isinstance(bundle, MathHintBundle)
    assert bundle.domains_queried == ("multivariate_analysis_corpus_v2",)
    assert len(bundle.hits) >= 1
    assert "manifold" in bundle.hits[0].doc_path.name


def test_gather_hints_for_unknown_chapter(tmp_path: Path) -> None:
    idx = _build_mini_rad(tmp_path)
    bundle = gather_hints(idx, "no_such_chapter", "x")
    assert bundle.domains_queried == ()
    assert bundle.hits == []


def test_gather_hints_when_domain_missing(tmp_path: Path) -> None:
    """RAD に該当 domain が無い場合は空 hits."""
    # apo_verifier は formal_methods_corpus_v2 + automated_theorem_proving_corpus_v2
    # が要るが、mini-RAD には存在しない
    idx = _build_mini_rad(tmp_path)
    bundle = gather_hints(idx, "apo_verifier", "z3 smt")
    assert bundle.hits == []
    assert bundle.domains_queried == ()


def test_gather_hints_returns_topic_in_bundle(tmp_path: Path) -> None:
    idx = _build_mini_rad(tmp_path)
    bundle = gather_hints(idx, "apo_optimizer", "gradient descent")
    assert bundle.topic == "gradient descent"
    assert bundle.chapter == "apo_optimizer"
