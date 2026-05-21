# SPDX-License-Identifier: Apache-2.0
"""VariantSubprocessScheduler — Phase 2 前倒し subprocess transport の単体テスト.

variant_runner を子 process として実行し, FitnessReport を復元する経路を
end-to-end で検証する. credential 不要 (transport="mock"), kernel module 不要.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pytest

from llive.perf.evolutionary import (
    EvolutionConfig,
    EvolutionLoop,
    Genome,
    Individual,
    LIVE_VARIANT_GENOME_BOUNDS,
    LIVE_VARIANT_GENOME_LABELS,
    LlivVariantBuilder,
    Population,
    VariantSubprocessError,
    VariantSubprocessScheduler,
    mock_variant_fitness_factory,
)
from llive.perf.evolutionary.subprocess_scheduler import (
    _failure_fitness_report,
    _fitness_report_from_variant_result,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_individuals(n: int, *, seed: int = 0) -> list[Individual]:
    rng = np.random.default_rng(seed)
    inds: list[Individual] = []
    for _ in range(n):
        g = Genome.random(LIVE_VARIANT_GENOME_BOUNDS, rng, labels=LIVE_VARIANT_GENOME_LABELS)
        inds.append(Individual.from_genome(g))
    return inds


def _make_population(n: int, *, seed: int = 0) -> Population:
    return Population.random(
        LIVE_VARIANT_GENOME_BOUNDS,
        size=n,
        seed=seed,
        labels=LIVE_VARIANT_GENOME_LABELS,
    )


# ---------------------------------------------------------------------------
# 1. construction / validation
# ---------------------------------------------------------------------------


def test_init_validates_timeout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timeout_sec"):
        VariantSubprocessScheduler(tmp_dir=tmp_path, timeout_sec=0.0)


def test_init_validates_max_workers(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_workers"):
        VariantSubprocessScheduler(tmp_dir=tmp_path, max_workers=0)


def test_init_validates_retries(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="retries"):
        VariantSubprocessScheduler(tmp_dir=tmp_path, retries=-1)


def test_init_rejects_unknown_transport(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="transport"):
        VariantSubprocessScheduler(tmp_dir=tmp_path, transport="bogus")


def test_init_creates_tmp_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "subdir"
    sched = VariantSubprocessScheduler(tmp_dir=target)
    assert target.is_dir()
    assert sched.tmp_dir == target


# ---------------------------------------------------------------------------
# 2. helper functions (no subprocess)
# ---------------------------------------------------------------------------


def test_fitness_report_from_variant_result_preserves_score() -> None:
    data = {
        "variant_id": "v1",
        "transport": "mock",
        "score": 0.74,
        "breakdown": {"quality": 0.7, "latency_ms": 5.0},
        "runtime_metadata": {"llama_cpp_sha": "deadbeef"},
        "n_samples": 1,
        "notes": "hello",
    }
    rep = _fitness_report_from_variant_result(data, subprocess_elapsed=0.123)
    assert rep.score == pytest.approx(0.74)
    assert rep.breakdown["quality"] == pytest.approx(0.7)
    assert rep.runtime_metadata["llama_cpp_sha"] == "deadbeef"
    # subprocess_wallclock_sec が後追加されている
    assert "subprocess_wallclock_sec" in rep.runtime_metadata
    assert float(rep.runtime_metadata["subprocess_wallclock_sec"]) == pytest.approx(0.123, abs=1e-6)
    assert rep.notes == "hello"


def test_failure_fitness_report_marks_score_zero() -> None:
    rep = _failure_fitness_report("ind1", RuntimeError("boom"))
    assert rep.score == 0.0
    assert rep.breakdown["subprocess_failure"] == 1.0
    assert "ind1" in rep.notes
    assert "boom" in rep.notes
    assert rep.n_samples == 0


# ---------------------------------------------------------------------------
# 3. end-to-end subprocess evaluation (mock transport, real variant_runner)
# ---------------------------------------------------------------------------


def test_single_individual_subprocess_eval(tmp_path: Path) -> None:
    inds = _make_individuals(1, seed=11)
    sched = VariantSubprocessScheduler(
        tmp_dir=tmp_path,
        transport="mock",
        timeout_sec=30.0,
        max_workers=1,
        cleanup=False,  # 後で result.json の存在を確認
    )
    reports = sched(mock_variant_fitness_factory(), inds)
    assert len(reports) == 1
    rep = reports[0]
    assert 0.0 <= rep.score <= 1.0
    assert "factor_coverage" in rep.breakdown
    # result.json と config.json が残っている
    variant_dir = tmp_path / inds[0].individual_id
    assert (variant_dir / "config.json").exists()
    assert (variant_dir / "result.json").exists()
    payload = json.loads((variant_dir / "result.json").read_text(encoding="utf-8"))
    assert payload["score"] == pytest.approx(rep.score, abs=1e-9)


def test_parity_with_in_process_mock(tmp_path: Path) -> None:
    """同じ Genome を subprocess / in-process それぞれで評価し score が一致.

    mock_variant_fitness_factory は deterministic (runtime_metadata 以外) なので
    subprocess 経路と in-process 経路で score / breakdown が **完全一致** するはず.
    """
    inds = _make_individuals(3, seed=42)

    # in-process
    in_process_fn = mock_variant_fitness_factory()
    in_process_reports = [in_process_fn(ind.genome) for ind in inds]

    # subprocess
    sched = VariantSubprocessScheduler(
        tmp_dir=tmp_path,
        transport="mock",
        timeout_sec=30.0,
        max_workers=1,
    )
    sub_reports = sched(in_process_fn, inds)

    assert len(sub_reports) == 3
    for sub, inp in zip(sub_reports, in_process_reports, strict=True):
        assert sub.score == pytest.approx(inp.score, abs=1e-9)
        # 8 軸 breakdown は完全一致 (runtime_metadata は subprocess 側で差分があるので比較しない)
        for k, v in inp.breakdown.items():
            assert sub.breakdown[k] == pytest.approx(v, abs=1e-9)


def test_parallel_max_workers_preserves_order(tmp_path: Path) -> None:
    """max_workers > 1 でも入力順を保って返る (EvolutionLoop の zip 前提)."""
    inds = _make_individuals(4, seed=7)
    # 注: thread 並列で subprocess を spawn. 4 個体, 2 workers.
    sched = VariantSubprocessScheduler(
        tmp_dir=tmp_path,
        transport="mock",
        timeout_sec=30.0,
        max_workers=2,
    )
    reports = sched(mock_variant_fitness_factory(), inds)
    in_process_fn = mock_variant_fitness_factory()
    expected = [in_process_fn(ind.genome) for ind in inds]
    assert len(reports) == 4
    for sub, inp in zip(reports, expected, strict=True):
        assert sub.score == pytest.approx(inp.score, abs=1e-9)


def test_cleanup_removes_variant_dir(tmp_path: Path) -> None:
    inds = _make_individuals(1, seed=3)
    sched = VariantSubprocessScheduler(
        tmp_dir=tmp_path,
        transport="mock",
        timeout_sec=30.0,
        cleanup=True,
    )
    sched(mock_variant_fitness_factory(), inds)
    variant_dir = tmp_path / inds[0].individual_id
    assert not variant_dir.exists()


# ---------------------------------------------------------------------------
# 4. failure handling — fail_on_error / retries
# ---------------------------------------------------------------------------


class _FailingScheduler(VariantSubprocessScheduler):
    """python_exe を絶対に存在しないパスにして強制失敗させる test 用 subclass."""

    def __post_init__(self) -> None:  # type: ignore[override]
        super().__post_init__()
        # FileNotFoundError 系を強制発生させる
        self.python_exe = str(Path("/__definitely_not_existing_python__"))


def test_fail_on_error_true_raises(tmp_path: Path) -> None:
    inds = _make_individuals(1, seed=1)
    sched = _FailingScheduler(
        tmp_dir=tmp_path,
        transport="mock",
        timeout_sec=5.0,
        retries=0,
        fail_on_error=True,
    )
    with pytest.raises(VariantSubprocessError):
        sched(mock_variant_fitness_factory(), inds)


def test_fail_on_error_false_returns_zero_score(tmp_path: Path) -> None:
    inds = _make_individuals(1, seed=2)
    sched = _FailingScheduler(
        tmp_dir=tmp_path,
        transport="mock",
        timeout_sec=5.0,
        retries=0,
        fail_on_error=False,
    )
    reports = sched(mock_variant_fitness_factory(), inds)
    assert len(reports) == 1
    assert reports[0].score == 0.0
    assert reports[0].breakdown.get("subprocess_failure") == 1.0


def test_retries_eventually_succeed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """retries を消費して最終的に成功する path. subprocess.run を 1 回失敗→成功させる."""
    inds = _make_individuals(1, seed=33)
    sched = VariantSubprocessScheduler(
        tmp_dir=tmp_path,
        transport="mock",
        timeout_sec=30.0,
        retries=2,
        fail_on_error=True,
    )

    real_run = subprocess.run
    state = {"calls": 0}

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        state["calls"] += 1
        if state["calls"] == 1:
            # 1 回目: FileNotFoundError として扱う subprocess.CalledProcessError 相当を発生
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr="injected")
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    reports = sched(mock_variant_fitness_factory(), inds)
    assert len(reports) == 1
    assert reports[0].score > 0
    assert state["calls"] == 2  # 1 失敗 + 1 成功


def test_timeout_triggers_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """subprocess.TimeoutExpired を inject して timeout 経路を確認."""
    inds = _make_individuals(1, seed=4)
    sched = VariantSubprocessScheduler(
        tmp_dir=tmp_path,
        transport="mock",
        timeout_sec=0.1,
        retries=0,
        fail_on_error=False,
    )

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=0.1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    reports = sched(mock_variant_fitness_factory(), inds)
    assert len(reports) == 1
    assert reports[0].score == 0.0
    assert "TimeoutExpired" in reports[0].notes


def test_zero_returncode_but_missing_result_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """subprocess が exit 0 でも result.json が無ければ失敗扱い."""
    inds = _make_individuals(1, seed=5)
    sched = VariantSubprocessScheduler(
        tmp_dir=tmp_path,
        transport="mock",
        timeout_sec=10.0,
        retries=0,
        fail_on_error=False,
    )

    class FakeCompleted:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)
    reports = sched(mock_variant_fitness_factory(), inds)
    assert len(reports) == 1
    assert reports[0].score == 0.0
    assert "FileNotFoundError" in reports[0].notes or "result.json" in reports[0].notes


# ---------------------------------------------------------------------------
# 5. EvolutionLoop 統合
# ---------------------------------------------------------------------------


@pytest.mark.timeout(180)
def test_evolution_loop_uses_subprocess_scheduler(tmp_path: Path) -> None:
    """EvolutionLoop に subprocess scheduler を差し込み 2 世代回す.

    fitness_fn は placeholder. scheduler 経由で subprocess が呼ばれることを
    確認する.
    """
    population = _make_population(3, seed=21)
    scheduler = VariantSubprocessScheduler(
        tmp_dir=tmp_path,
        transport="mock",
        timeout_sec=30.0,
        max_workers=2,
        cleanup=True,
    )
    loop = EvolutionLoop(
        fitness_fn=mock_variant_fitness_factory(),  # placeholder, not used by scheduler
        scheduler=scheduler,
    )
    config = EvolutionConfig(
        max_generations=1,
        log_progress=False,
        patience=99,
    )
    result = loop.run(population, config)
    # 評価された個体は履歴を持つ
    for ind in result.final_population.individuals:
        assert ind.fitness is not None
        assert 0.0 <= ind.fitness.score <= 1.0
    # 進化が走った形跡 (stats が世代分溜まる)
    assert len(result.stats_history) >= 1
