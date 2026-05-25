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

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from llive.benchmark.runtime_metadata import collect_runtime_metadata
from llive.perf.evolutionary.fitness import Fitness
from llive.perf.evolutionary.genome import Genome
from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.genome_3d_operators import (
    Genome3DCrossover,
    Genome3DMutation,
)
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
    _resume_from_snapshot,
)
from llive.perf.evolutionary.persona import (
    PERSONA_ONTOLOGY,
    RESEARCH_METHODOLOGY_PERSONA_IDS,
    THOUGHT_FACTORS,
    get_persona,
)
from llive.perf.evolutionary.population import Population
from llive.perf.evolutionary.thought_factor_per_layer import (
    ThoughtFactorPerLayerChromosome,
)

#: founder の ``individual_id`` に付けるプレフィックス. 世代交代後も parent_ids を
#: 辿れば founder 由来かどうか判別できる. 既存 Individual 機構を壊さない
#: (uuid hex の代わりに人間可読 id を入れるだけ).
FOUNDER_ID_PREFIX = "founder"

#: 思考因子 dim の bounds 内 index (LIVE_VARIANT_GENOME_BOUNDS の 0..9).
#: persona.factor_affinity を書き込む先. THOUGHT_FACTORS と
#: THOUGHT_FACTOR_LABELS は同順 (構造化→現実接続) であることを起動時に検証する.
_FACTOR_DIM_COUNT = len(THOUGHT_FACTOR_LABELS)

#: founder の backend_id dim と on-prem 初期値。bounds 中点 (≈2.5 → anthropic=cloud) だと
#: 実 LLM fitness (on_prem fail-closed) 下で全 founder が淘汰され mock 個体に収束してしまう。
#: founder は on-prem 純な mock (=0) から始め、進化が mutate で他 on-prem backend を探索する。
#: proxy fitness には backend_id は無関係なので影響しない (走行前に確定すべき凍結点)。
_BACKEND_ID_DIM = LIVE_VARIANT_GENOME_LABELS.index("backend_id")
_ON_PREM_FOUNDER_BACKEND_ID = 0  # _BACKEND_NAMES[0] = "mock" (on-prem, fail-closed を通る)

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


def _thought_factor_vector(genome: Genome | Genome3D) -> np.ndarray:
    """両 genome 型から 10-dim 思考因子ベクトルを取り出す (G3 fitness adapter).

    - flat :class:`Genome` — 思考因子 dim 0..9 (``as_array()[:10]``, 既存挙動を
      完全保持)。
    - :class:`Genome3D` — ``c_factors`` (10×層 matrix) の **層平均** で 10-dim に
      集約 (proxy は全体傾向しか見ないため層平均が妥当)。
    """
    if isinstance(genome, Genome3D):
        return genome.c_factors.as_array().mean(axis=1)
    return genome.as_array()[:_FACTOR_DIM_COUNT]


def _proxy_fitness(genome: Genome | Genome3D) -> FitnessReport:
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
    factors = _thought_factor_vector(genome)

    mean = float(factors.mean())
    std = float(factors.std())
    balance = float(max(0.0, min(1.0, mean * (1.0 - std))))

    provenance_idx = THOUGHT_FACTOR_LABELS.index("factor_provenance")
    provenance = float(max(0.0, min(1.0, factors[provenance_idx])))

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
    # backend_id を on-prem (mock=0) で初期化。bounds 中点 (≈anthropic=cloud) のままだと
    # 実 LLM fitness の fail-closed で全 founder が淘汰されるため (進化が mutate で他 on-prem を探索)。
    values[_BACKEND_ID_DIM] = float(_ON_PREM_FOUNDER_BACKEND_ID)
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


def build_founder_genome_3d(
    persona_id: str,
    *,
    broadcast_strategy: str = "uniform",
) -> Genome3D:
    """1 persona から founder 用 :class:`Genome3D` を構築する (多層版, G4).

    persona の ``factor_affinity`` (10 思考因子) を **c_factors** 層に
    :meth:`ThoughtFactorPerLayerChromosome.from_persona_affinity` で書き込み、
    残り 3 層 (impl / prompt / meta) は default (中立) から始める。因子層が
    persona の同一性を担い、他層は進化が探索する — flat founder の「思考因子 dim に
    affinity, 残りは bounds 中点」と同じ思想を多層に持ち上げたもの。

    Parameters
    ----------
    persona_id : str
        :data:`PERSONA_ONTOLOGY` のキー。
    broadcast_strategy : str
        affinity を層へ broadcast する戦略 ("uniform" / "working_heavy" /
        "episodic_heavy")。default は全層複製。

    Returns
    -------
    Genome3D
        c_factors = persona affinity 由来、他 3 chromosome = default。
    """
    persona = get_persona(persona_id)
    affinity = tuple(float(v) for v in persona.factor_affinity)
    c_factors = ThoughtFactorPerLayerChromosome.from_persona_affinity(
        affinity, broadcast_strategy=broadcast_strategy
    )
    base = Genome3D.default()
    # frozen dataclass: 因子層のみ差し替えた新インスタンスを作る。
    return Genome3D(
        c_impl=base.c_impl,
        c_prompt=base.c_prompt,
        c_meta=base.c_meta,
        c_factors=c_factors,
    )


def _random_genome3d(rng: np.random.Generator) -> Genome3D:
    """gen0 padding 用のランダム Genome3D.

    c_factors のみ random ([0,1] uniform) にし、impl/prompt/meta は default から
    始める。多様性/novelty は c_factors の flat view で測る (genome_flat_vector)
    ため、padding の多様性は c_factors random で十分。impl/prompt/meta は進化の
    mutation (sample_neighborhood) が探索する。
    """
    base = Genome3D.default()
    return Genome3D(
        c_impl=base.c_impl,
        c_prompt=base.c_prompt,
        c_meta=base.c_meta,
        c_factors=ThoughtFactorPerLayerChromosome.random(rng),
    )


def build_founder_individuals_3d(
    persona_ids: Sequence[str],
    *,
    broadcast_strategy: str = "uniform",
) -> list[Individual]:
    """各 persona を gen0 の Genome3D founder :class:`Individual` にする (G4).

    flat 版 :func:`build_founder_individuals` と同じ founder-id 規約
    (``"founder:<persona_id>"``) なので :func:`is_founder` /
    :func:`founder_persona_id` がそのまま使える。
    """
    founders: list[Individual] = []
    for pid in persona_ids:
        genome = build_founder_genome_3d(pid, broadcast_strategy=broadcast_strategy)
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
    #: immigration で走行中に追加投入した persona id (resume + inject 時のみ非空)。
    injected_persona_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "evolution_result": self.evolution_result.to_dict(),
            "winners_path": str(self.winners_path) if self.winners_path else None,
            "lineage_path": str(self.lineage_path) if self.lineage_path else None,
            "founder_ids": list(self.founder_ids),
            "used_proxy_fitness": self.used_proxy_fitness,
            "injected_persona_ids": list(self.injected_persona_ids),
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
    is_proxy: bool | None = None,
    log_progress: bool = False,
    # ---- Genome3D (多層ゲノム) モード: founder/padding/operator を Genome3D に切替 ----
    genome3d: bool = False,
    crossover_mode: str = "intra",
    mutation_step: float = 0.1,
    # ---- 段階的追加 (immigration): 走行中の集団に新 persona founder を移民 ----
    inject_persona_ids: Sequence[str] | None = None,
    # ---- 長期運用パラメータ (2026-05-23 環境整備: 100→1000 世代研究用) ----
    patience: int | None = None,
    diversity_floor: float | None = None,
    checkpoint_every: int | None = None,
    resume_from: Path | None = None,
    max_wallclock_seconds: float | None = None,
    persist_generation_log: bool = False,
    # ---- 安全弁 (長時間 run で「全個体同一→同じ結果を吐き続ける空回り」を止める) ----
    max_stall_generations: int | None = 25,
    # ---- 選択圧 (lldarwin): None なら EvolutionLoop 既定 TournamentSelection (後方互換) ----
    selection: Callable | None = None,
    # ---- lldarwin Stage1.5: lineage-niched 中立貯蔵庫 (絶滅 founder 系統を毎世代 re-inject) ----
    lineage_reservoir: bool = False,
    reinject_interval: int = 1,
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
    genome3d : bool
        多層ゲノム (:class:`Genome3D`) モード。True で founder/padding を Genome3D
        に、operator を :class:`Genome3DCrossover` / :class:`Genome3DMutation` に
        切り替える。default False (flat 19-dim Genome、後方互換)。
    crossover_mode : str
        genome3d 時の crossover 戦略 ("intra" 層内 / "cross" 層間)。default "intra"。
    mutation_step : float
        genome3d 時の mutation neighborhood step_size。default 0.1。
    max_stall_generations : int | None
        **安全弁**: 全個体が同一 genome に収束 (distinct==1) した状態が連続でこの
        世代数続いたら ``population_collapsed`` で停止する。patience を無効化する
        長時間 run でも「同じ結果を吐き続ける空回り」を断つ。default 25。``None``
        で無効。EvolutionLoop は ``max_generations`` で必ず有界 (真の無限ループは
        起きない) が、本ガードは無駄な長時間空回りを早期に止める。

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

    used_proxy = (fitness_fn is None) if is_proxy is None else bool(is_proxy)
    effective_fitness: Fitness = fitness_fn if fitness_fn is not None else _proxy_fitness

    # ---- gen0 個体: founders + random padding ----
    rng = np.random.default_rng(seed)
    n_random = population_size - n_founders
    if genome3d:
        # 多層ゲノム: founder は c_factors に persona affinity、padding は random
        # Genome3D、bounds は None (Genome3D は単一 GenomeBounds を持たない)。
        founders = build_founder_individuals_3d(founder_ids)
        random_individuals = [
            Individual.from_genome(_random_genome3d(rng), birth_generation=0)
            for _ in range(n_random)
        ]
        population_bounds = None
    else:
        founders = build_founder_individuals(founder_ids)
        random_individuals = [
            Individual.from_genome(
                Genome.random(
                    LIVE_VARIANT_GENOME_BOUNDS, rng, labels=LIVE_VARIANT_GENOME_LABELS
                ),
                birth_generation=0,
            )
            for _ in range(n_random)
        ]
        population_bounds = LIVE_VARIANT_GENOME_BOUNDS
    individuals = founders + random_individuals

    population = Population(
        individuals=individuals,
        bounds=population_bounds,
        generation=0,
        seed=seed,
        generation_seeds=[seed],
    )

    # ---- immigration: 走行中の集団に新 persona founder を移民 (段階的追加) ----
    # 「ペルソナを段階的に定期追加しながら世代交代」を **走行を止めず連続** で行う。
    # resume_from の snapshot を driver 側で読み、最弱 k 体を新 founder で置換する。
    # → loop 側 resume は無効化 (二重 resume 防止)。snapshot が無ければ no-op。
    # extensibility 契約準拠: genome dim 不変・既存個体は survivors として保持。
    loop_resume_from = resume_from
    injected_ids: tuple[str, ...] = ()
    if inject_persona_ids:
        # fail-closed (B-LOGIC-2): inject 指定は immigration を期待する明示要求。
        # resume snapshot が無いと実行できないので silent no-op でなく明示エラー。
        if resume_from is None:
            raise ValueError(
                "inject_persona_ids requires resume_from (immigration は resume "
                "snapshot に対して行う). resume_from を指定するか inject_persona_ids を空に。"
            )
        snap = _resume_from_snapshot(resume_from)
        if snap is None:
            raise ValueError(
                f"inject_persona_ids 指定だが resume_from={resume_from!r} の "
                "snapshot を読めない。snapshot パスを確認。"
            )
        immigrants = (
            build_founder_individuals_3d(inject_persona_ids)
            if genome3d
            else build_founder_individuals(inject_persona_ids)
        )
        k = len(immigrants)
        if k >= snap.size:
            raise ValueError(
                f"inject count ({k}) >= resumed population size ({snap.size}); "
                "would replace the entire population. Reduce inject_persona_ids."
            )
        # 移民は現世代で誕生 (birth_generation = 現 generation)
        for f in immigrants:
            f.birth_generation = snap.generation
        # 最弱 k 体を drop (score 昇順) し、移民を加える → 集団サイズ不変
        survivors = sorted(snap.individuals, key=lambda i: i.score, reverse=True)
        snap.individuals = immigrants + survivors[: snap.size - k]
        population = snap
        loop_resume_from = None  # driver 側で resume 済 → loop で再 load しない
        injected_ids = tuple(inject_persona_ids)

    # ---- winners.jsonl + metrics.jsonl 世代追記 hook ----
    # on_generation_end は **毎世代** 発火する (loop.py)。EvolutionConfig の
    # checkpoint_every は snapshot/generations.jsonl の粒度を制御するが、SVG の
    # 滑らかな時系列には毎世代の集計が要るので、metrics.jsonl をフックで別途書く。
    # → snapshot は粗く (checkpoint_every)、metrics は毎世代、と分離する。
    winners_path: Path | None = None
    metrics_path: Path | None = None
    founder_lineage_path: Path | None = None
    on_generation_end = None

    # ---- founder lineage (provenance) 追跡 ----
    # winners.jsonl は各世代 top3 + その親 id しか残さないため、後付けで全個体を
    # founder へ遡れない (非勝者祖先が dead-end する)。そこで **走行中に全集団を見る**
    # on_generation_end フックで root-founder を伝播し、毎世代の全個体 founder 分布を
    # founder_lineage.jsonl に書く。来歴 (factor_provenance) を進化自身に適用する形。
    # 解決規則: founder は自身の persona、それ以外は parent_ids[0] の founder を継承、
    # 親不明/padding は "(random)"。gen0 を seed し、以後は前世代が必ず map 済 (親は
    # 前世代集団のメンバ) なので O(1) で確定する。
    founder_map: dict[str, str] = {}
    for _ind in population.individuals:  # gen0 (immigration 適用後)
        _pid = founder_persona_id(_ind)
        founder_map[_ind.individual_id] = _pid if _pid else "(random)"

    def _resolve_origin(ind: Individual) -> str:
        pid = founder_persona_id(ind)
        if pid is not None:  # 走行中 immigration で投入された founder も拾う
            return pid
        if ind.parent_ids:
            return founder_map.get(ind.parent_ids[0], "(random)")
        return "(random)"

    # lldarwin Stage1.5: 中立貯蔵庫。founder_map を **共有** し、貯蔵庫が再投入した
    # 個体の系統も founder_lineage.jsonl ログと整合させる (revived は parent 無しでも
    # 貯蔵庫が founder_map に正しい系統を登録するため、on_generation_end の
    # founder_map.get(id) で先に解決される)。protected = "(random)" を除く persona founders。
    reservoir_hook: Callable | None = None
    if lineage_reservoir:
        from llive.perf.evolutionary.lineage_reservoir import LineageReservoir

        protected = frozenset(v for v in founder_map.values() if v != "(random)")
        reservoir_hook = LineageReservoir(
            lineage_of=founder_map,
            protected_lineages=protected,
            reinject_interval=reinject_interval,
        )

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        winners_path = out_dir / "winners.jsonl"
        metrics_path = out_dir / "metrics.jsonl"
        founder_lineage_path = out_dir / "founder_lineage.jsonl"
        # 過去 run の追記混入を防ぐため新規 run 開始時に消す (resume 時は残す)。
        if resume_from is None:
            for p in (winners_path, metrics_path, founder_lineage_path):
                if p.exists():
                    p.unlink()

        def on_generation_end(pop: Population, stats) -> None:  # noqa: ANN001
            write_winners_jsonl(winners_path, pop, top_n=3)
            # 毎世代の集計 (best/mean/std/diversity) を append = SVG 時系列材料。
            with metrics_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(stats.to_dict(), ensure_ascii=False) + "\n")
            # 全個体の root-founder 分布を append (P2 支配ストリームの素材)。
            counts: dict[str, int] = {}
            for ind in pop.individuals:
                origin = founder_map.get(ind.individual_id)
                if origin is None:
                    origin = _resolve_origin(ind)
                    founder_map[ind.individual_id] = origin
                counts[origin] = counts.get(origin, 0) + 1
            rec = {
                "generation": int(pop.generation),
                "n_individuals": len(pop.individuals),
                "founder_counts": counts,
            }
            with founder_lineage_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- EvolutionLoop (flat=default operators / genome3d=Genome3D operators) ----
    loop_kwargs: dict = {
        "fitness_fn": effective_fitness,
        "on_generation_end": on_generation_end,
    }
    # lldarwin: 多目的選択圧 (MultiPressureSelector 等) を注入。None なら既定 Tournament。
    if selection is not None:
        loop_kwargs["selection"] = selection
    # lldarwin Stage1.5: 中立貯蔵庫を on_population_bred に注入 (絶滅 founder 系統を再投入)。
    if reservoir_hook is not None:
        loop_kwargs["on_population_bred"] = reservoir_hook
    if genome3d:
        loop_kwargs["crossover"] = Genome3DCrossover(mode=crossover_mode)
        loop_kwargs["mutation"] = Genome3DMutation(step_size=mutation_step)
    loop = EvolutionLoop(**loop_kwargs)
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
    if loop_resume_from is not None:
        cfg_kwargs["resume_from"] = loop_resume_from
    if max_wallclock_seconds is not None:
        cfg_kwargs["max_wallclock_seconds"] = max_wallclock_seconds
    # 安全弁: 全個体同一 (distinct==1) が連続したら停止。長時間 run で patience/
    # diversity_floor を無効化していても「同じ結果を吐き続ける空回り」を断つ。
    if max_stall_generations is not None:
        cfg_kwargs["max_stall_generations"] = max_stall_generations
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
        injected_persona_ids=injected_ids,
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
    "build_founder_genome_3d",
    "build_founder_individuals",
    "build_founder_individuals_3d",
    "compare_against_llm_baselines",
    "founder_persona_id",
    "is_founder",
    "read_winners",
    "run_persona_evolution",
]
