# SPDX-License-Identifier: Apache-2.0
"""FrozenGeneRegistry — FrozenGene の集合管理 + violation 判定
(llive v0.I EV-34 skeleton).

[[frozen_gene.py]] (FrozenGene 単体) は形式宣言のみで、judge 機構を持たない.
本 registry が:

1. gene_path → FrozenGene の dict 保持
2. ``is_frozen(path)`` — 指定 path が凍結されているか
3. ``violates(mutation_target_path)`` — 突然変異対象が違反 gene か判定
4. ``prune_expired()`` — 期限切れ gene の自動削除
5. serialization (audit log / governance authority への引き渡し用)

を提供する. 実 Approval Bus 統合 (Ed25519 verify + mutation deny hook) は
v0.I.4 次フェーズ.

violates の path 判定は **prefix match** で行う:

- registry に ``"C-prompt.persona_set"`` (集合全体) が登録されていれば、
  ``"C-prompt.persona_set[7]"`` も違反扱い.
- registry に ``"C-prompt.persona_set[7]"`` (個別 index) が登録されていれば、
  ``"C-prompt.persona_set[7]"`` のみ違反 (``[8]`` は許可).

これにより「集合 wildcards」と「個別 freeze」を同一 API で扱える.

Status (2026-05-22 着地): skeleton. dataclass + dict 管理 + prefix match +
expiry prune + JSON round-trip. 実 Ed25519 verify + Approval Bus mutation
hook + 月次再評価 cron は v0.I.4.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from llive.perf.evolutionary.frozen_gene import FrozenGene

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass
class FrozenGeneRegistry:
    """FrozenGene の集合管理 + violation 判定 registry.

    Attributes:
        _genes: gene_path → FrozenGene の dict. 同一 path 再登録時は
            **最新で上書き** する (governance authority による expiry 延長 /
            note 更新を許容).

    Note:
        Skeleton 段階では thread safety を保証しない. 並行 mutation を
        伴う本番統合では ``threading.RLock`` を __post_init__ で生成する.
    """

    _genes: dict[str, FrozenGene] = field(default_factory=dict)

    # ----- mutation -------------------------------------------------------

    def register(self, gene: FrozenGene) -> None:
        """gene を registry に登録. 同一 gene_path は上書き.

        Args:
            gene: 凍結対象 FrozenGene.

        Raises:
            ValueError: ``gene`` が FrozenGene でない場合.
        """
        if not isinstance(gene, FrozenGene):
            raise ValueError(
                f"register expects FrozenGene, got {type(gene).__name__}"
            )
        self._genes[gene.gene_path] = gene

    def unregister(self, gene_path: str) -> bool:
        """gene_path に対応する gene を削除. 存在しなければ ``False``."""
        return self._genes.pop(gene_path, None) is not None

    def prune_expired(self, now_iso: str | None = None) -> int:
        """期限切れ gene を一括削除. 削除数を返す.

        Args:
            now_iso: 比較基準時刻. 省略時 UTC 現在時刻.

        Returns:
            削除した gene 数.
        """
        expired_paths = [
            path for path, g in self._genes.items() if g.is_expired(now_iso)
        ]
        for path in expired_paths:
            del self._genes[path]
        return len(expired_paths)

    # ----- query ----------------------------------------------------------

    def is_frozen(self, gene_path: str) -> bool:
        """``gene_path`` に **完全一致** する gene が登録済みか.

        集合 wildcards 判定が必要な場合は :meth:`violates` を使う.
        """
        return gene_path in self._genes

    def violates(self, mutation_target_path: str) -> FrozenGene | None:
        """突然変異対象 path が登録済み frozen gene に違反するか.

        Prefix match で集合 wildcards を扱う:

        - registry に ``"C-prompt.persona_set"`` があれば
          ``"C-prompt.persona_set[7]"`` も違反.
        - 完全一致も違反.
        - 期限切れ gene は **判定対象から除外** する (skeleton の都合上、
          呼び出し側で ``prune_expired`` を先に呼ぶ運用も可だが、無料で
          静止 expiry チェックを入れることで「忘れて誤判定」を防ぐ).

        Args:
            mutation_target_path: 突然変異が当てようとしている gene path.

        Returns:
            違反した FrozenGene. 違反なければ ``None``.
        """
        if not isinstance(mutation_target_path, str) or not mutation_target_path:
            return None

        # 完全一致と prefix を 1 pass で確認.
        # prefix match: "C-prompt.persona_set" は "C-prompt.persona_set[7]" や
        # "C-prompt.persona_set.foo" にもマッチ. ただし接尾辞は
        # `[` / `.` で始まること (誤マッチ防止: "persona_set_v2" は別物).
        for path, gene in self._genes.items():
            if gene.is_expired():
                continue
            if mutation_target_path == path:
                return gene
            if mutation_target_path.startswith(path) and len(mutation_target_path) > len(path):
                next_char = mutation_target_path[len(path)]
                if next_char in "[.":
                    return gene
        return None

    def list_active(self, now_iso: str | None = None) -> list[FrozenGene]:
        """期限内 (active) な gene を list で返す (path 昇順)."""
        return sorted(
            (g for g in self._genes.values() if not g.is_expired(now_iso)),
            key=lambda g: g.gene_path,
        )

    def __len__(self) -> int:
        return len(self._genes)

    def __contains__(self, gene_path: object) -> bool:
        return isinstance(gene_path, str) and gene_path in self._genes

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """JSON 化可能な dict に変換. audit log / inter-process 転送用."""
        return {
            "genes": [
                self._genes[path].to_dict() for path in sorted(self._genes.keys())
            ]
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FrozenGeneRegistry:
        """to_dict 出力から復元."""
        reg = cls()
        for entry in data.get("genes", []):
            reg.register(FrozenGene.from_dict(entry))
        return reg


__all__ = [
    "FrozenGeneRegistry",
]
