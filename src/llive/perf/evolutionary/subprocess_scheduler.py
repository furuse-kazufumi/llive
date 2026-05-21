# SPDX-License-Identifier: Apache-2.0
"""VariantSubprocessScheduler — Phase 2 前倒し subprocess transport.

llive v0.C Phase 2 interface spec の subprocess 経路を **EvolutionLoop の
scheduler** として完成させたもの.

variant_runner を 1 派生 = 1 process で起動し, result.json を読んで
FitnessReport に復元する. 並列度は ThreadPoolExecutor で握る (個々の
評価は CPU/credential を持つ別 process 側で消費されるため, スレッド側は
ほぼ I/O 待ち).

実 LlivKernel spawn (credential / kernel module 後) は variant_runner 側で
``--transport in_process`` を実装することで切り替わる. **scheduler 自体は
transport agnostic**.

## Why subprocess scheduler

* 派生間のプロセス分離 — global state (faiss index / DuckDB conn) が衝突しない
* fault isolation — 1 派生が segfault しても他派生は止まらない
* timeout を OS レベルで握れる — Python の cooperative cancel に頼らない
* 実 LLM backend を立てたままでも data_dir 隔離で並走可能

## Usage

```python
from llive.perf.evolutionary import (
    EvolutionLoop, EvolutionConfig, VariantSubprocessScheduler,
    Population, LIVE_VARIANT_GENOME_BOUNDS, mock_variant_fitness_factory,
)

scheduler = VariantSubprocessScheduler(
    tmp_dir=Path("out/subprocess_evol"),
    transport="mock",       # credential 後 "in_process" に
    timeout_sec=60.0,
    max_workers=4,
    retries=1,
    fail_on_error=False,
    cleanup=True,
)
loop = EvolutionLoop(
    fitness_fn=mock_variant_fitness_factory(),  # ignored by subprocess path
    scheduler=scheduler,
)
result = loop.run(population, EvolutionConfig(max_generations=10))
```

scheduler が injection されている間, ``fitness_fn`` は **EvolutionLoop の
seed-aware path で読まれない**よう subprocess scheduler を passing するため
の placeholder として渡す.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from llive.perf.evolutionary.fitness import Fitness
from llive.perf.evolutionary.individual import FitnessReport, Individual
from llive.perf.evolutionary.llive_variant import LlivVariantBuilder


class VariantSubprocessError(RuntimeError):
    """1 派生 subprocess 評価が決定的に失敗したときに上げる例外.

    ``fail_on_error=True`` の scheduler のみで raise される.
    """


@dataclass
class VariantSubprocessScheduler:
    """``variant_runner`` を subprocess.run で起動する SchedulerFn.

    Attributes
    ----------
    tmp_dir : Path
        派生ごとに ``<tmp_dir>/<variant_id>/`` を作って config.json / result.json
        を読み書きする. 親 dir は事前に作られる. ``cleanup=True`` の場合,
        評価後に variant dir を rmtree する.
    python_exe : str
        subprocess で起動する Python interpreter. default = ``sys.executable``.
    transport : str
        ``variant_runner --transport`` に渡す値. ``"mock"`` (credential 不要) /
        ``"in_process"`` (実 LlivKernel, Phase 2 完了後).
    timeout_sec : float
        1 派生 subprocess の wall-clock timeout. ``subprocess.TimeoutExpired``
        は 1 回の評価失敗として扱う.
    max_workers : int
        並列度. 1 なら逐次. >1 なら ThreadPoolExecutor で同時に subprocess を
        起動する (派生間 data_dir 隔離が前提).
    retries : int
        失敗時の retry 回数. 0 なら 1 回のみ.
    fail_on_error : bool
        retries まで使い切っても失敗した場合の挙動.
        ``True`` → ``VariantSubprocessError`` を raise.
        ``False`` → ``score=0.0`` の :class:`FitnessReport` で代替.
    cleanup : bool
        評価後に ``<tmp_dir>/<variant_id>/`` を削除するか. ``False`` だと
        デバッグ用に config / result が残る.
    builder : LlivVariantBuilder
        Genome → LlivVariantConfig 変換器. injection で test 容易.
    log_progress : bool
        各派生の start / end / failure を stdout に書く.
    """

    tmp_dir: Path
    python_exe: str = field(default_factory=lambda: sys.executable)
    transport: str = "mock"
    timeout_sec: float = 300.0
    max_workers: int = 1
    retries: int = 0
    fail_on_error: bool = True
    cleanup: bool = True
    builder: LlivVariantBuilder = field(default_factory=LlivVariantBuilder)
    log_progress: bool = False

    # -- public API --------------------------------------------------------

    def __post_init__(self) -> None:
        if self.timeout_sec <= 0:
            raise ValueError("timeout_sec must be > 0")
        if self.max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if self.retries < 0:
            raise ValueError("retries must be >= 0")
        if self.transport not in ("mock", "in_process"):
            raise ValueError(f"unknown transport: {self.transport!r}")
        self.tmp_dir = Path(self.tmp_dir)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def __call__(
        self,
        fitness_fn: Fitness,
        individuals: Iterable[Individual],
    ) -> list[FitnessReport]:
        """EvolutionLoop の SchedulerFn として呼ばれる entry point.

        ``fitness_fn`` は **使わない**. subprocess 経由で
        ``llive.variant_runner`` 側で評価する. interface 互換のため受け取る.
        """
        inds = list(individuals)
        results: dict[str, FitnessReport] = {}
        if self.max_workers == 1:
            for ind in inds:
                results[ind.individual_id] = self._evaluate_one(ind)
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futures = {
                    pool.submit(self._evaluate_one, ind): ind.individual_id
                    for ind in inds
                }
                for fut in as_completed(futures):
                    ind_id = futures[fut]
                    results[ind_id] = fut.result()
        # 入力順を保ったまま返す (EvolutionLoop が zip で結合するため)
        return [results[ind.individual_id] for ind in inds]

    # -- internals ---------------------------------------------------------

    def _evaluate_one(self, ind: Individual) -> FitnessReport:
        """1 派生を subprocess で評価. retries まで試す."""
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return self._run_subprocess(ind, attempt=attempt)
            except (
                subprocess.TimeoutExpired,
                subprocess.CalledProcessError,
                FileNotFoundError,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                last_exc = exc
                if self.log_progress:
                    print(
                        f"[subprocess_scheduler] {ind.individual_id} "
                        f"attempt {attempt + 1}/{self.retries + 1} failed: {exc!r}"
                    )
                continue
        # ここに来たら retries 使い切り
        if self.fail_on_error:
            raise VariantSubprocessError(
                f"individual {ind.individual_id} failed after "
                f"{self.retries + 1} attempts: {last_exc!r}"
            ) from last_exc
        return _failure_fitness_report(ind.individual_id, last_exc)

    def _run_subprocess(self, ind: Individual, *, attempt: int) -> FitnessReport:
        """1 派生 1 試行. 失敗は例外で伝播."""
        # variant_id は ind.individual_id を採用 (進化系統と紐付け)
        variant_id = ind.individual_id
        variant_dir = self.tmp_dir / variant_id
        variant_dir.mkdir(parents=True, exist_ok=True)
        config_path = variant_dir / "config.json"
        result_path = variant_dir / "result.json"

        config = self.builder.build_config(ind.genome, variant_id=variant_id)
        config_path.write_text(
            json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cmd = [
            self.python_exe,
            "-m",
            "llive.variant_runner",
            "--config-json",
            str(config_path),
            "--output-json",
            str(result_path),
            "--transport",
            self.transport,
        ]

        start = time.perf_counter()
        if self.log_progress:
            print(
                f"[subprocess_scheduler] start {variant_id} "
                f"attempt={attempt + 1} cmd={' '.join(cmd[2:])}"
            )
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
        )
        elapsed = time.perf_counter() - start

        if completed.returncode != 0:
            raise subprocess.CalledProcessError(
                completed.returncode,
                cmd,
                output=completed.stdout,
                stderr=completed.stderr,
            )
        if not result_path.exists():
            raise FileNotFoundError(
                f"variant_runner exited 0 but result.json was not created at "
                f"{result_path}; stderr={completed.stderr!r}"
            )

        data = json.loads(result_path.read_text(encoding="utf-8"))
        report = _fitness_report_from_variant_result(data, subprocess_elapsed=elapsed)

        # cleanup は **成功時のみ** (デバッグのため失敗時は残す)
        if self.cleanup:
            shutil.rmtree(variant_dir, ignore_errors=True)

        if self.log_progress:
            print(
                f"[subprocess_scheduler] done  {variant_id} "
                f"score={report.score:.4f} elapsed={elapsed:.3f}s"
            )
        return report


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fitness_report_from_variant_result(
    data: dict, *, subprocess_elapsed: float
) -> FitnessReport:
    """``variant_runner`` の result.json から :class:`FitnessReport` を復元.

    variant_runner.evaluate_variant() が返す shape:

    .. code-block:: json

        {
          "variant_id": "...",
          "transport": "mock",
          "score": 0.74,
          "breakdown": {...},
          "runtime_metadata": {...},
          "n_samples": 1,
          "notes": "...",
          "elapsed_seconds": 0.012
        }

    subprocess 起動含む wall-clock (``subprocess_elapsed``) は
    ``runtime_metadata["subprocess_wallclock_sec"]`` に追加する.
    """
    runtime_md = dict(data.get("runtime_metadata", {}))
    runtime_md["subprocess_wallclock_sec"] = f"{subprocess_elapsed:.6f}"
    return FitnessReport(
        score=float(data["score"]),
        breakdown=dict(data.get("breakdown", {})),
        runtime_metadata=runtime_md,
        n_samples=int(data.get("n_samples", 1)),
        notes=str(data.get("notes", "")),
    )


def _failure_fitness_report(
    individual_id: str, exc: Exception | None
) -> FitnessReport:
    """``fail_on_error=False`` の代替 FitnessReport.

    score=0.0, notes に失敗理由を含む. 次世代で淘汰される想定.
    """
    err_repr = repr(exc) if exc is not None else "unknown"
    return FitnessReport(
        score=0.0,
        breakdown={"subprocess_failure": 1.0},
        runtime_metadata={},
        n_samples=0,
        notes=(
            f"variant_subprocess_failure | id={individual_id} error={err_repr}"
        ),
    )


__all__ = [
    "VariantSubprocessError",
    "VariantSubprocessScheduler",
]
