# SPDX-License-Identifier: Apache-2.0
"""NoveltyFilter — ShinkaEvolve 流 評価前 novelty-based rejection の unit test (T2 2-2).

カバレッジ:
(i)   重複 genome ストリームで棄却率が上がる
(ii)  多様な genome は素通し (accept)
(iii) loop で novelty_filter=None (default) なら旧挙動不変 (後方互換)
(iv)  依存欠落 (st encoder) 時 pass-through (fail-open)
(v)   loop に挿すと評価がスキップされ (LLM 呼び出し回数が減り) sentinel で淘汰される
(vi)  ミニ計測: 重複 50% の 200 候補で節約評価数を数値検証
"""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    EvolutionConfig,
    EvolutionLoop,
    FilterStats,
    Genome,
    GenomeBounds,
    Individual,
    NoveltyFilter,
    Population,
    hashing_ngram_vector,
    sphere_fitness,
)

_B1 = GenomeBounds(lower=(-5.0,), upper=(5.0,))
_B3 = GenomeBounds(lower=(-5.0, -5.0, -5.0), upper=(5.0, 5.0, 5.0))


def _ind(values: tuple[float, ...], bounds: GenomeBounds) -> Individual:
    return Individual.from_genome(Genome.from_values(values, bounds=bounds))


# ---------------------------------------------------------------------------
# (i) 重複ストリームで棄却率が上がる
# ---------------------------------------------------------------------------


def test_duplicate_stream_rejects() -> None:
    """同一 genome を連投すると 2 件目以降は棄却される."""
    nf = NoveltyFilter(threshold=0.99, encoder="genome")
    same = (1.0, 2.0, 3.0)
    # 1 件目: archive 空 → accept
    assert nf.accepts(_ind(same, _B3)) is True
    # 2-10 件目: 完全一致 (cosine=1.0 > 0.99) → 全部 reject
    for _ in range(9):
        assert nf.accepts(_ind(same, _B3)) is False
    assert nf.stats.accepted == 1
    assert nf.stats.rejected == 9
    assert nf.stats.saved_evaluations == 9
    assert nf.stats.rejection_rate == pytest.approx(0.9)


def test_near_duplicate_rejected_below_threshold() -> None:
    """閾値を下げると「ほぼ同じ向き」の genome も棄却される."""
    nf = NoveltyFilter(threshold=0.9, encoder="genome")
    assert nf.accepts(_ind((1.0, 0.0, 0.0), _B3)) is True
    # ほぼ同方向 (cosine ~ 0.9999) → reject
    assert nf.accepts(_ind((1.0, 0.001, 0.0), _B3)) is False


# ---------------------------------------------------------------------------
# (ii) 多様な genome は素通し
# ---------------------------------------------------------------------------


def test_diverse_stream_passes() -> None:
    """直交方向の genome は cosine が低く、全部 accept される."""
    nf = NoveltyFilter(threshold=0.5, encoder="genome")
    diverse = [
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0),
    ]
    for v in diverse:
        assert nf.accepts(_ind(v, _B3)) is True
    assert nf.stats.accepted == 4
    assert nf.stats.rejected == 0
    assert nf.stats.rejection_rate == 0.0


def test_partition_splits() -> None:
    nf = NoveltyFilter(threshold=0.99, encoder="genome")
    same = _ind((2.0, 2.0, 2.0), _B3)
    cands = [
        _ind((2.0, 2.0, 2.0), _B3),  # accept (1st)
        _ind((2.0, 2.0, 2.0), _B3),  # reject (dup)
        _ind((-3.0, 1.0, 0.0), _B3),  # accept (novel)
    ]
    accepted, rejected = nf.partition(cands)
    assert len(accepted) == 2
    assert len(rejected) == 1
    _ = same  # silence


# ---------------------------------------------------------------------------
# (iii) loop で novelty_filter=None なら旧挙動不変 (後方互換)
# ---------------------------------------------------------------------------


def test_loop_default_disabled_unchanged() -> None:
    """novelty_filter 未設定 (default None) で結果が従来と同一であること."""
    pop_a = Population.random(_B3, size=8, seed=7)
    loop_a = EvolutionLoop(fitness_fn=sphere_fitness)  # filter なし
    cfg = EvolutionConfig(max_generations=5, patience=99, diversity_floor=0.0, log_progress=False)
    res_a = loop_a.run(pop_a, cfg)

    # 同 seed で filter=None を明示してももう一度回し、bit-identical を確認
    pop_b = Population.random(_B3, size=8, seed=7)
    loop_b = EvolutionLoop(fitness_fn=sphere_fitness, novelty_filter=None)
    res_b = loop_b.run(pop_b, cfg)

    assert loop_a.novelty_filter is None
    assert res_a.best_score == pytest.approx(res_b.best_score)
    assert res_a.final_population.generation == res_b.final_population.generation
    assert len(res_a.stats_history) == len(res_b.stats_history)


# ---------------------------------------------------------------------------
# (iv) 依存欠落 (st encoder) 時 pass-through (fail-open)
# ---------------------------------------------------------------------------


def test_st_encoder_missing_dep_falls_back_to_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """sentence-transformers が無くても st encoder は text fallback で動く (fail-open)."""
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("sentence_transformers"):
            raise ImportError("sentence_transformers not installed (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    nf = NoveltyFilter(threshold=0.99, encoder="st", text_of=lambda ind: "hello world")
    # 同じテキストを 2 回 → st 失敗 → text fallback で類似判定 → 2 回目は reject
    assert nf.accepts(_ind((1.0,), _B1)) is True
    assert nf.accepts(_ind((2.0,), _B1)) is False  # text 同一 → reject (fallback 動作)
    # st が壊れても例外で落ちず判定が成立している = fail-open かつ機能継続
    assert nf._st_failed is True


def test_encode_exception_fails_open() -> None:
    """ベクトル化が例外を投げたら accept (fail-open) + failed_open カウント."""
    def _boom(_ind: Individual) -> str:
        raise RuntimeError("encoder boom")

    nf = NoveltyFilter(encoder="text", text_of=_boom)
    assert nf.accepts(_ind((1.0,), _B1)) is True
    assert nf.stats.failed_open == 1
    assert nf.stats.accepted == 1


# ---------------------------------------------------------------------------
# (v) loop に挿すと評価がスキップされる
# ---------------------------------------------------------------------------


def test_loop_skips_evaluation_for_rejected() -> None:
    """棄却個体は fitness_fn が呼ばれず sentinel(-inf) で淘汰される."""
    call_count = {"n": 0}

    def counting_fitness(genome: Genome):
        call_count["n"] += 1
        return sphere_fitness(genome)

    # 全個体を同一 genome にした集団 → 1 体だけ accept、残りは reject されるはず
    same = Genome.from_values((1.0, 1.0, 1.0), bounds=_B3)
    inds = [Individual.from_genome(same) for _ in range(6)]
    pop = Population(individuals=inds, bounds=_B3, seed=0)

    nf = NoveltyFilter(threshold=0.99, encoder="genome")
    loop = EvolutionLoop(fitness_fn=counting_fitness, novelty_filter=nf)
    cfg = EvolutionConfig(max_generations=0, patience=99, diversity_floor=0.0, log_progress=False)
    loop.run(pop, cfg)

    # gen 0 のみ評価。6 体中 1 体だけ評価 → fitness_fn は 1 回だけ呼ばれる
    assert call_count["n"] == 1
    assert nf.stats.accepted == 1
    assert nf.stats.rejected == 5
    # 棄却個体は sentinel -inf
    skipped = [i for i in pop.individuals if i.fitness and i.fitness.score == float("-inf")]
    assert len(skipped) == 5
    assert all("novelty_skipped" in i.fitness.breakdown for i in skipped)


# ---------------------------------------------------------------------------
# (vi) ミニ計測: 重複 50% の 200 候補で節約評価数
# ---------------------------------------------------------------------------


def test_mini_measurement_50pct_duplicate_stream() -> None:
    """重複 50% の 200 件ストリームで節約評価数を数値検証 + 報告.

    生成方法: 100 個の distinct な「基準 genome」を作り、各々を 2 回ずつ
    (= 計 200 件) ランダム順で流す。重複の 2 回目以降は棄却されるべき。
    distinct 100 件は全部 accept、重複 100 件は全部 reject される設計なので
    理論棄却率 = 50%、節約評価数 = 100。
    """
    rng = np.random.default_rng(2024)
    n_distinct = 100
    # 各次元を十分離して cosine 類似が低い distinct 群を作る (3 次元では足りない
    # ので 16 次元の bounds を使う)。
    dim = 16
    bounds = GenomeBounds(lower=(-10.0,) * dim, upper=(10.0,) * dim)
    bases = [
        Genome.from_values(tuple(rng.uniform(-10, 10, size=dim)), bounds=bounds)
        for _ in range(n_distinct)
    ]
    stream: list[Individual] = []
    for g in bases:
        stream.append(Individual.from_genome(g))  # 1 回目
        stream.append(Individual.from_genome(g))  # 2 回目 (完全重複)
    rng.shuffle(stream)  # ランダム順 (重複の前後関係は保たれないが、必ず片方が先)

    nf = NoveltyFilter(threshold=0.999, encoder="genome", archive_max_size=10_000)
    accepted, rejected = nf.partition(stream)

    # distinct 100 件は accept、重複 100 件は reject (cosine=1.0 > 0.999)
    assert len(accepted) == n_distinct
    assert len(rejected) == n_distinct
    assert nf.stats.saved_evaluations == n_distinct
    assert nf.stats.rejection_rate == pytest.approx(0.5)
    assert nf.stats.failed_open == 0

    # 数値報告 (pytest -s で見える)
    print(
        f"\n[mini-measurement] stream={len(stream)} "
        f"accepted={nf.stats.accepted} rejected={nf.stats.rejected} "
        f"saved_evaluations={nf.stats.saved_evaluations} "
        f"rejection_rate={nf.stats.rejection_rate:.2%}"
    )


# ---------------------------------------------------------------------------
# 周辺: validation / stats / text encoder / reset
# ---------------------------------------------------------------------------


def test_validates_options() -> None:
    with pytest.raises(ValueError, match="threshold"):
        NoveltyFilter(threshold=1.5)
    with pytest.raises(ValueError, match="threshold"):
        NoveltyFilter(threshold=-0.1)
    with pytest.raises(ValueError, match="archive_max_size"):
        NoveltyFilter(archive_max_size=0)
    with pytest.raises(ValueError, match="encoder"):
        NoveltyFilter(encoder="bogus")  # type: ignore[arg-type]


def test_filter_stats_to_dict() -> None:
    s = FilterStats(accepted=3, rejected=7, failed_open=1, seen=3)
    d = s.to_dict()
    assert d["total"] == 10
    assert d["saved_evaluations"] == 7
    assert d["rejection_rate"] == pytest.approx(0.7)
    assert d["failed_open"] == 1


def test_hashing_ngram_vector_self_similarity() -> None:
    """同一テキストは cosine=1, 全く違うテキストは低 cosine."""
    a = hashing_ngram_vector("the quick brown fox", dim=256)
    b = hashing_ngram_vector("the quick brown fox", dim=256)
    c = hashing_ngram_vector("zzz qqq vvv", dim=256)
    assert float(a @ b) == pytest.approx(1.0, abs=1e-9)
    assert float(a @ c) < 0.5
    # 空文字は 0 ベクトル
    assert float(np.linalg.norm(hashing_ngram_vector("", dim=256))) == 0.0


def test_text_encoder_dedup() -> None:
    """text encoder で同一テキスト変異を棄却できる."""
    nf = NoveltyFilter(threshold=0.99, encoder="text", text_of=lambda ind: "rewrite as poem")
    assert nf.accepts(_ind((1.0,), _B1)) is True
    assert nf.accepts(_ind((9.0,), _B1)) is False  # genome 違うが text 同一 → reject


def test_reset_clears_state() -> None:
    nf = NoveltyFilter(threshold=0.99, encoder="genome")
    nf.accepts(_ind((1.0, 1.0, 1.0), _B3))
    nf.accepts(_ind((1.0, 1.0, 1.0), _B3))
    assert nf.stats.total == 2
    nf.reset()
    assert nf.stats.total == 0
    assert nf.stats.seen == 0
    # reset 後は再び archive 空 → accept
    assert nf.accepts(_ind((1.0, 1.0, 1.0), _B3)) is True
