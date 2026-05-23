# SPDX-License-Identifier: Apache-2.0
"""Persona 世代交代 turnkey ドライバ (llive v0.E CE / persona founder evolution).

ユーザー要望 (2026-05-23):
    「ペルソナ founder からの世代交代を 1 コマンドで回す turnkey ドライバ。
    roster は段階的に定期追加 (ID を足すだけ。歴史人物も混在可)。
    現状の LLM との比較もしたい (これは別層・stub)。」

本 module は既存の成熟した進化系 (``genome`` / ``individual`` / ``population`` /
``loop`` / ``lineage``) を **薄く束ねる** orchestrator で、新しい進化アルゴリズムは
導入しない。やることは 3 点:

1. **founder 生成** — :data:`PERSONA_ONTOLOGY` の各 persona を gen0 の種個体に
   する。persona の ``factor_affinity`` (10 思考因子) を
   :data:`LIVE_VARIANT_GENOME_BOUNDS` の思考因子 dim (0..9) に書き込み、残り 9
   dim は bounds 中点で埋めて :class:`Genome` を構築する。
2. **集団構築 + 進化** — founders を gen0 に確実に含め、残りを random Genome で
   埋めて :class:`Population` を作り、default operators の :class:`EvolutionLoop`
   を回す。世代ごとに ``winners.jsonl`` を追記する。
3. **系統樹出力** — run 後に ``lineage.mmd`` (Mermaid) を書く。

honest disclosure
------------------
本 module の **fitness は proxy** (:func:`_proxy_fitness`) である。実 LLM タスク
評価でも「現状 LLM との比較」でもない。proxy は決定論的・on-prem 純度を保ち
(LLM を呼ばない)、思考因子の均衡 + 来歴 (provenance) 因子加点という研究的に
意味のある heuristic を返すだけ。実 fitness と LLM 比較への配線は
:func:`compare_against_llm_baselines` の docstring に設計を残す (本セッションは
stub)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from llive.benchmark.runtime_metadata import collect_runtime_metadata
from llive.perf.evolutionary.fitness import Fitness
from llive.perf.evolutionary.genome import Genome
from llive.perf.evolutionary.individual import FitnessReport, Individual
from llive.perf.evolutionary.lineage import (
    load_winners_jsonl,
    render_lineage_mermaid,
    write_lineage_mermaid_file,
    write_winners_jsonl,
)
from llive.perf.evolutionary.llive_variant import (
    LIVE_VARIANT_GENOME_BOUNDS,
    LIVE_VARIANT_GENOME_LABELS,
    THOUGHT_FACTOR_LABELS,
)
from llive.perf.evolutionary.loop import (
    EvolutionConfig,
    EvolutionLoop,
    EvolutionResult,
)
from llive.perf.evolutionary.persona import (
    PERSONA_ONTOLOGY,
    RESEARCH_METHODOLOGY_PERSONA_IDS,
    THOUGHT_FACTORS,
    get_persona,
)
from llive.perf.evolutionary.population import Population

#: founder の ``individual_id`` に付けるプレフィックス. 世代交代後も parent_ids を
#: 辿れば founder 由来かどうか判別できる. 既存 Individual 機構を壊さない
#: (uuid hex の代わりに人間可読 id を入れるだけ).
FOUNDER_ID_PREFIX = "founder"

#: 思考因子 dim の bounds 内 index (LIVE_VARIANT_GENOME_BOUNDS の 0..9).
#: persona.factor_affinity を書き込む先. THOUGHT_FACTORS と
#: THOUGHT_FACTOR_LABELS は同順 (構造化→現実接続) であることを起動時に検証する.
_FACTOR_DIM_COUNT = len(THOUGHT_FACTOR_LABELS)

# 起動時健全性検査: persona 側 (THOUGHT_FACTORS) と genome 側
# (THOUGHT_FACTOR_LABELS) の思考因子ラベルが完全一致していること。
# 一致しないと founder の affinity を誤った dim に書き込んでしまう。
if tuple(THOUGHT_FACTORS) != tuple(THOUGHT_FACTOR_LABELS):
    raise RuntimeError(
        "THOUGHT_FACTORS (persona) と THOUGHT_FACTOR_LABELS (genome) の順序が "
        f"一致しません: {THOUGHT_FACTORS!r} != {THOUGHT_FACTOR_LABELS!r}"
    )


# ---------------------------------------------------------------------------
# proxy fitness (honest disclosure: 実 LLM 評価ではない)
# ---------------------------------------------------------------------------


def _proxy_fitness(genome: Genome) -> FitnessReport:
    """**proxy fitness** — 決定論的・on-prem 純度維持 (LLM を呼ばない).

    .. warning::

        これは **proxy** である。実 fitness ではない。実 fitness は
        「実 LLM タスク評価 + 現状 LLM との比較 (次層)」であり、本関数はそれを
        模した heuristic に過ぎない。ベンチマーク値として外部に出すときは必ず
        「proxy」と明記すること (feedback_benchmark_honest_disclosure 準拠)。

    研究的に意味のある proxy として、思考因子 10 次元 (genome dim 0..9) に対し
    2 項を合成する:

    1. **均衡 (balance)** — 因子 weight が全て高めかつ偏らないほど高い。
       ``mean * (1 - std)``。すべて 0 だと 0、全て 1 だと 1、1 つだけ突出は低い。
    2. **来歴 (provenance) 加点** — ``factor_provenance`` (dim 7) を別建てで加点。
       furuse 調査者ペルソナの核 (源流まで辿る規律) を進化が捨てないよう、
       provenance を明示的に報酬化する。

    score = 0.7 * balance + 0.3 * provenance

    Returns
    -------
    FitnessReport
        ``breakdown`` に balance / provenance / 各因子平均を入れ、``notes`` に
        proxy である旨を明記する。
    """
    arr = genome.as_array()
    factors = arr[:_FACTOR_DIM_COUNT]

    mean = float(factors.mean())
    std = float(factors.std())
    balance = float(max(0.0, min(1.0, mean * (1.0 - std))))

    provenance_idx = THOUGHT_FACTOR_LABELS.index("factor_provenance")
    provenance = float(max(0.0, min(1.0, arr[provenance_idx])))

    score = 0.7 * balance + 0.3 * provenance

    md = collect_runtime_metadata()
    return FitnessReport(
        score=float(score),
        breakdown={
            "balance": balance,
            "provenance": provenance,
            "factor_mean": mean,
            "factor_std": std,
        },
        runtime_metadata=dict(md),
        n_samples=1,
        notes=(
            "PROXY fitness (NOT real LLM evaluation). "
            "score = 0.7*balance + 0.3*provenance over thought-factor dims 0..9. "
            "Real fitness = LLM task eval + comparison vs current LLMs (see "
            "compare_against_llm_baselines)."
        ),
    )


# ---------------------------------------------------------------------------
# founder 生成
# ---------------------------------------------------------------------------


def _bounds_midpoint() -> np.ndarray:
    """LIVE_VARIANT_GENOME_BOUNDS の per-dim 中点ベクトル (19-dim)."""
    lower = np.asarray(LIVE_VARIANT_GENOME_BOUNDS.lower, dtype=np.float64)
    upper = np.asarray(LIVE_VARIANT_GENOME_BOUNDS.upper, dtype=np.float64)
    return (lower + upper) / 2.0


def build_founder_genome(persona_id: str) -> Genome:
    """1 persona から founder 用 :class:`Genome` を構築する.

    思考因子 dim (0..9) に ``persona.factor_affinity`` を書き込み、残り dim は
    bounds 中点で埋める。bounds は :class:`Genome.from_values` が自動 clip する。

    Parameters
    ----------
    persona_id : str
        :data:`PERSONA_ONTOLOGY` のキー。

    Returns
    -------
    Genome
        19-dim, ラベル付き。
    """
    persona = get_persona(persona_id)
    values = _bounds_midpoint()
    affinity = np.asarray(persona.factor_affinity, dtype=np.float64)
    values[:_FACTOR_DIM_COUNT] = affinity
    return Genome.from_values(
        values, LIVE_VARIANT_GENOME_BOUNDS, labels=LIVE_VARIANT_GENOME_LABELS
    )


def build_founder_individuals(persona_ids: Sequence[str]) -> list[Individual]:
    """各 persona を gen0 の founder :class:`Individual` にする.

    ``individual_id`` を ``"founder:<persona_id>"`` に上書きして founder を辿れる
    ようにする (既存 uuid hex 機構を壊さず、可読 id を割り当てるだけ)。
    ``parent_ids=()`` / ``birth_generation=0``。
    """
    founders: list[Individual] = []
    for pid in persona_ids:
        genome = build_founder_genome(pid)
        ind = Individual.from_genome(genome, parent_ids=(), birth_generation=0)
        ind.individual_id = f"{FOUNDER_ID_PREFIX}:{pid}"
        founders.append(ind)
    return founders


def is_founder(individual: Individual) -> bool:
    """``individual`` が founder (gen0 の persona 種個体) か判定する."""
    return individual.individual_id.startswith(f"{FOUNDER_ID_PREFIX}:")


def founder_persona_id(individual: Individual) -> str | None:
    """founder なら元 persona_id を返す。違えば None。"""
    prefix = f"{FOUNDER_ID_PREFIX}:"
    if individual.individual_id.startswith(prefix):
        return individual.individual_id[len(prefix):]
    return None


# ---------------------------------------------------------------------------
# 結果 dataclass
# ---------------------------------------------------------------------------


@dataclass
class PersonaEvolutionResult:
    """:func:`run_persona_evolution` の戻り値.

    Attributes
    ----------
    evolution_result : EvolutionResult
        既存 EvolutionLoop の生結果 (best_individual / stats_history 等)。
    winners_path : Path | None
        ``winners.jsonl`` のパス (out_dir 未指定なら None)。
    lineage_path : Path | None
        ``lineage.mmd`` のパス (out_dir 未指定なら None)。
    founder_ids : tuple[str, ...]
        gen0 に投入した persona id 列。
    used_proxy_fitness : bool
        proxy fitness を使ったか (honest disclosure 用)。
    """

    evolution_result: EvolutionResult
    winners_path: Path | None
    lineage_path: Path | None
    founder_ids: tuple[str, ...]
    used_proxy_fitness: bool

    def to_dict(self) -> dict:
        return {
            "evolution_result": self.evolution_result.to_dict(),
            "winners_path": str(self.winners_path) if self.winners_path else None,
            "lineage_path": str(self.lineage_path) if self.lineage_path else None,
            "founder_ids": list(self.founder_ids),
            "used_proxy_fitness": self.used_proxy_fitness,
        }


# ---------------------------------------------------------------------------
# turnkey driver
# ---------------------------------------------------------------------------


def run_persona_evolution(
    persona_ids: Sequence[str] = RESEARCH_METHODOLOGY_PERSONA_IDS,
    *,
    population_size: int = 12,
    generations: int = 15,
    seed: int = 0,
    out_dir: Path | None = None,
    fitness_fn: Fitness | None = None,
    log_progress: bool = False,
    # ---- 長期運用パラメータ (2026-05-23 環境整備: 100→1000 世代研究用) ----
    patience: int | None = None,
    diversity_floor: float | None = None,
    checkpoint_every: int | None = None,
    resume_from: Path | None = None,
    max_wallclock_seconds: float | None = None,
    persist_generation_log: bool = False,
) -> PersonaEvolutionResult:
    """ペルソナ founder からの世代交代を 1 コマンドで回す turnkey ドライバ.

    roster (``persona_ids``) はパラメータ化されている。**段階的に定期追加** =
    ID を足すだけ。歴史人物 (oka-kiyoshi / grothendieck / ...) も研究方法論
    ペルソナ (furuse-kazufumi / friston / ...) も同じ仕組みで混在できる。

    Parameters
    ----------
    persona_ids : Sequence[str]
        gen0 の founder にする persona id 列。default は研究方法論ペルソナ 4 名
        (:data:`RESEARCH_METHODOLOGY_PERSONA_IDS`)。
    population_size : int
        集団サイズ。founder 数より小さいと founder を切り落とすため
        ``ValueError``。
    generations : int
        進化世代数 (EvolutionConfig.max_generations)。
    seed : int
        RNG seed。同 seed なら決定論的 (best_score 再現)。
    out_dir : Path | None
        出力先。指定すると ``winners.jsonl`` (世代ごと top3 追記) と
        ``lineage.mmd`` を書く。None なら何も書かない。
    fitness_fn : Fitness | None
        ``Callable[[Genome], FitnessReport]``。None なら :func:`_proxy_fitness`
        (**proxy**, honest disclosure) を使う。
    log_progress : bool
        EvolutionLoop の世代ごと print を有効化するか。default False (テストを
        静かにするため)。

    Returns
    -------
    PersonaEvolutionResult

    Raises
    ------
    ValueError
        ``population_size`` が founder 数 (= len(persona_ids)) 未満のとき。
    """
    founder_ids = tuple(persona_ids)
    n_founders = len(founder_ids)
    if n_founders == 0:
        raise ValueError("persona_ids must be non-empty")
    if population_size < n_founders:
        raise ValueError(
            f"population_size ({population_size}) < founder count ({n_founders}); "
            "founders would be dropped. Increase population_size."
        )

    used_proxy = fitness_fn is None
    effective_fitness: Fitness = fitness_fn if fitness_fn is not None else _proxy_fitness

    # ---- gen0 個体: founders + random padding ----
    founders = build_founder_individuals(founder_ids)
    rng = np.random.default_rng(seed)
    n_random = population_size - n_founders
    random_individuals = [
        Individual.from_genome(
            Genome.random(
                LIVE_VARIANT_GENOME_BOUNDS, rng, labels=LIVE_VARIANT_GENOME_LABELS
            ),
            birth_generation=0,
        )
        for _ in range(n_random)
    ]
    individuals = founders + random_individuals

    population = Population(
        individuals=individuals,
        bounds=LIVE_VARIANT_GENOME_BOUNDS,
        generation=0,
        seed=seed,
        generation_seeds=[seed],
    )

    # ---- winners.jsonl 世代追記 hook ----
    winners_path: Path | None = None
    on_generation_end = None
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        winners_path = out_dir / "winners.jsonl"
        # 過去 run の追記混入を防ぐため新規 run 開始時に消す。
        if winners_path.exists():
            winners_path.unlink()

        def on_generation_end(pop: Population, _stats) -> None:  # noqa: ANN001
            write_winners_jsonl(winners_path, pop, top_n=3)

    # ---- EvolutionLoop (default operators) ----
    loop = EvolutionLoop(
        fitness_fn=effective_fitness,
        on_generation_end=on_generation_end,
    )
    # 長期運用 (100→1000 世代) 対応: 後方互換のため新パラメータは None default で、
    # 指定時のみ EvolutionConfig に渡す (None → 既存の EvolutionConfig 既定値)。
    # - persist_generation_log + out_dir → generations.jsonl / snapshot_gen_*.json を
    #   書き、resume と SVG 時系列材料の素材にする。
    # - patience を generations+1 等にすれば早期停止せず指定世代を完走できる
    #   (proxy fitness は早く収束するため、長期研究では patience 無効化が必須)。
    cfg_kwargs: dict = {
        "max_generations": generations,
        "log_progress": log_progress,
        "out_dir": out_dir if (persist_generation_log and out_dir is not None) else None,
    }
    if patience is not None:
        cfg_kwargs["patience"] = patience
    if diversity_floor is not None:
        cfg_kwargs["diversity_floor"] = diversity_floor
    if checkpoint_every is not None:
        cfg_kwargs["checkpoint_every"] = checkpoint_every
    if resume_from is not None:
        cfg_kwargs["resume_from"] = resume_from
    if max_wallclock_seconds is not None:
        cfg_kwargs["max_wallclock_seconds"] = max_wallclock_seconds
    config = EvolutionConfig(**cfg_kwargs)
    result = loop.run(population, config)

    # ---- lineage.mmd 出力 ----
    lineage_path: Path | None = None
    if out_dir is not None and winners_path is not None:
        winners = load_winners_jsonl(winners_path)
        lineage_path = out_dir / "lineage.mmd"
        write_lineage_mermaid_file(
            lineage_path,
            winners,
            title=f"persona evolution lineage (founders={', '.join(founder_ids)})",
        )

    return PersonaEvolutionResult(
        evolution_result=result,
        winners_path=winners_path,
        lineage_path=lineage_path,
        founder_ids=founder_ids,
        used_proxy_fitness=used_proxy,
    )


# ---------------------------------------------------------------------------
# LLM 比較 interface (stub — 本セッションでは未実装)
# ---------------------------------------------------------------------------


def compare_against_llm_baselines(
    result: PersonaEvolutionResult,
    *,
    baselines: Sequence[str] = (),
    out_dir: Path | None = None,
) -> dict:
    """進化した best 個体を **現状 LLM ベースライン** と比較する (stub).

    .. note:: 本セッションでは **未実装** (``NotImplementedError``)。設計のみ残す。

    ユーザー要望「現状の LLM との比較」に対応する次層 interface。実 fitness
    (proxy ではなく実 LLM タスク評価) が配線された後に、進化集団の best 構成と
    既製 LLM (OpenAI / Anthropic / Ollama 等) を **同一タスクセット・同一採点基準**
    で並べて比較するためのエントリポイント。

    設計 (lleval 連携)
    ------------------
    比較は llive 単体ではなく **lleval** (project_lleval_v01_poc_scope,
    ``docs`` の lleval) に委ねる想定:

    1. best 個体の :class:`LlivVariantConfig` を ``LlivVariantBuilder`` で実体化し、
       lleval の「被験者 (subject under test)」として登録する。
    2. ``baselines`` で指定した現状 LLM (例: ``("gpt-4o", "claude-sonnet",
       "ollama:qwen2.5")``) を同じ lleval task suite に登録する。
    3. lleval が共通 task × 共通 rubric で全 subject を採点し、勝率 / Elo /
       per-task breakdown を返す。
    4. 戻り値 dict に ``{subject_id: {win_rate, elo, per_task: {...}}}`` を入れ、
       ``out_dir`` 指定時は JSON で書き出す。

    honest disclosure 制約 (feedback_llive_measurement_purity)
    ----------------------------------------------------------
    * llive 被験者は **on-prem only** で評価し、cloud LLM ベースラインとは
      measurement purity を分けて記録する (混ぜた集計値だけを出さない)。
    * promptfoo は *外部リファレンス* 扱い (lleval が正)。

    Parameters
    ----------
    result : PersonaEvolutionResult
        :func:`run_persona_evolution` の戻り値。best 個体を比較対象にする。
    baselines : Sequence[str]
        比較する現状 LLM の識別子列。
    out_dir : Path | None
        比較結果 JSON の出力先。

    Raises
    ------
    NotImplementedError
        常に。実 fitness + lleval 配線後に実装する。
    """
    raise NotImplementedError(
        "compare_against_llm_baselines is a stub. "
        "Real implementation requires: (1) real LLM-task fitness wired in place "
        "of _proxy_fitness, and (2) lleval integration to score the evolved best "
        "config against current LLM baselines on a shared task suite/rubric. "
        "See docstring for the lleval design and measurement-purity constraints."
    )


# read_winners は lineage の load_winners_jsonl の別名 (呼びやすさのため再公開).
read_winners = load_winners_jsonl


__all__ = [
    "FOUNDER_ID_PREFIX",
    "PersonaEvolutionResult",
    "build_founder_genome",
    "build_founder_individuals",
    "compare_against_llm_baselines",
    "founder_persona_id",
    "is_founder",
    "read_winners",
    "run_persona_evolution",
]
