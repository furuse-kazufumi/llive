# SPDX-License-Identifier: Apache-2.0
"""FrozenGene — 倫理 / 規制 / IP / 安全性で進化対象外と marking する gene
(llive v0.I EV-34 skeleton).

llive 派生集団進化 (v0.C) + メタ進化 (v0.I 案 A) は genome の **全 dim** を
自由に変異させる. しかし以下のような領域に変異が及ぶと、進化系の自己改善
が逆に **致命的な制約破壊** を引き起こす:

- ユーザーデータを外部送信する処理コード (FullSense local-first 原則
  ; [[project_fullsense_ear_origin]])
- Approval Bus を bypass する処理 (再帰防止)
- 他個体のデータを許可なく読む処理 (peer evaluation bias 防止)
- EU AI Act Art. 5 prohibited / 中国 AI 弁法 第 4 条 違反 prompt
- 自社 IP / 商標 (llive / FullSense / 古瀬あいマスコット)
- 一般安全性 (CSAM / 自傷誘導 / 武器製造 等)

本モジュールは「進化禁止区画」を **frozen dataclass + signature + expiry**
で形式化する. 単体では mutation を止めない (止めるのは FrozenGeneRegistry +
Approval Bus 統合). v0.I.4 で Approval Bus / Ed25519 統合.

形式化 (詳細は `docs/requirements_v0.I_meta_evolution_and_cross_substrate.md`
§6):

```python
@dataclass(frozen=True)
class FrozenGene:
    gene_path: str       # 例 "C-prompt.persona_set[7]"
    reason: FreezeReason # ETHICS / SECURITY / REGULATION / IP / SAFETY
    signature: bytes     # Ed25519 governance secret (skeleton では sha256 hex OK)
    expiry_iso: str      # ISO 8601 monthly re-evaluation
```

References:

- EU AI Act (2024). Regulation (EU) 2024/1689. Art. 5 prohibited AI practices.
- 中国国家互联网信息办公室 (2023). 生成式人工智能服务管理暂行办法 第 4 条.
- NIST SP 800-218 SSDF — supply chain integrity (skeleton signature scheme).
- llive [[project_fullsense_ear_origin]] — local-first 原則.

Status (2026-05-22 着地): skeleton. dataclass + Registry + expiry + Kolmogorov
proxy. 実 Ed25519 verify + Approval Bus mutation hook は次フェーズ.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: signature 最小 byte 数. Ed25519 公開鍵署名は 64 bytes だが、skeleton では
#: sha256 hex (64 chars = 64 bytes) を許容するため 32 bytes 以上に緩める.
MIN_SIGNATURE_BYTES: int = 32


# ---------------------------------------------------------------------------
# FreezeReason
# ---------------------------------------------------------------------------


class FreezeReason(StrEnum):
    """Frozen gene 凍結理由分類. Enum 値は audit log に直接書ける str."""

    ETHICS = "ETHICS"          # 倫理 (差別 / 偏見 / 自傷誘導)
    SECURITY = "SECURITY"      # セキュリティ (Approval Bus bypass / 外部送信)
    REGULATION = "REGULATION"  # 規制 (EU AI Act / 中国 AI 弁法)
    IP = "IP"                  # 知的財産 (商標 / 著作権 / マスコット)
    SAFETY = "SAFETY"          # 一般安全性 (武器 / CSAM / 違法薬物 等)


# ---------------------------------------------------------------------------
# ISO 8601 helpers
# ---------------------------------------------------------------------------


def _parse_iso8601(value: str) -> datetime:
    """ISO 8601 → aware datetime. "Z" suffix を許容."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"expiry_iso must be non-empty str, got {value!r}")
    # Python 3.11+ は datetime.fromisoformat が "Z" を解釈しない (3.11 で対応).
    # 念のため Z → +00:00 に置換しておく.
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"expiry_iso {value!r} is not ISO 8601: {exc}") from exc
    if dt.tzinfo is None:
        # naive datetime は UTC とみなす (skeleton 段階の妥協).
        dt = dt.replace(tzinfo=UTC)
    return dt


def _now_utc() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# FrozenGene
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrozenGene:
    """進化対象外と marking された 1 gene の凍結記録.

    Genome の **path** で 1 dim を指定し、その dim への mutation 試行を
    Approval Bus 経由で deny + audit するための形式宣言. 本 dataclass 単体
    は判定機構を持たない (FrozenGeneRegistry が責務を担う).

    Attributes:
        gene_path: 凍結対象 gene の path. 例 ``"C-prompt.persona_set[7]"``,
            ``"C-impl.judge_model"``. 形式は dot + bracket index で、
            ImplChromosome / PromptChromosome の field 名 + index に対応.
        reason: 凍結理由分類 (Enum).
        signature: Governance authority 署名. skeleton では sha256 hex
            (64 bytes) でも可、本番は Ed25519 (64 bytes).
        expiry_iso: 期限. ISO 8601. 月次再評価を前提に、期限切れは
            ``is_expired()`` で判定し、自動 prune される.
        note: 自由記述. audit 時の人間向けコメント (例: "EU AI Act Art. 5
            (a) subliminal techniques").
    """

    gene_path: str
    reason: FreezeReason
    signature: bytes
    expiry_iso: str
    note: str = ""

    # ----- validation -----------------------------------------------------

    def __post_init__(self) -> None:
        # gene_path
        if not isinstance(self.gene_path, str) or not self.gene_path.strip():
            raise ValueError(f"gene_path must be non-empty str, got {self.gene_path!r}")

        # reason
        if not isinstance(self.reason, FreezeReason):
            raise ValueError(
                f"reason must be FreezeReason, got {type(self.reason).__name__}"
            )

        # signature
        if not isinstance(self.signature, (bytes, bytearray)):
            raise ValueError(
                f"signature must be bytes, got {type(self.signature).__name__}"
            )
        if len(self.signature) < MIN_SIGNATURE_BYTES:
            raise ValueError(
                f"signature must be >= {MIN_SIGNATURE_BYTES} bytes "
                f"(got {len(self.signature)})"
            )

        # expiry_iso (raises if invalid)
        _parse_iso8601(self.expiry_iso)

        # note
        if not isinstance(self.note, str):
            raise ValueError(f"note must be str, got {type(self.note).__name__}")

    # ----- factories ------------------------------------------------------

    @classmethod
    def default(cls) -> FrozenGene:
        """skeleton 用のダミー frozen gene. テスト / 例示用.

        本番では governance authority が生成した署名つき gene を register
        するため、この default は使わない (テスト fixture / docs 例のみ).
        """
        return cls(
            gene_path="C-prompt.persona_set[0]",
            reason=FreezeReason.ETHICS,
            signature=b"\x00" * MIN_SIGNATURE_BYTES,
            expiry_iso="2099-12-31T00:00:00Z",
            note="skeleton default — not for production",
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FrozenGene:
        """dict から復元.

        ``signature`` は hex str / list[int] / bytes のいずれも許容
        (JSON は bytes を保持できないため).
        """
        raw_sig = data["signature"]
        if isinstance(raw_sig, (bytes, bytearray)):
            sig: bytes = bytes(raw_sig)
        elif isinstance(raw_sig, str):
            sig = bytes.fromhex(raw_sig)
        elif isinstance(raw_sig, list):
            sig = bytes(raw_sig)
        else:
            raise ValueError(
                f"signature must be bytes/hex-str/list[int], got {type(raw_sig).__name__}"
            )

        reason_raw = data["reason"]
        reason = (
            reason_raw
            if isinstance(reason_raw, FreezeReason)
            else FreezeReason(reason_raw)
        )

        return cls(
            gene_path=str(data["gene_path"]),
            reason=reason,
            signature=sig,
            expiry_iso=str(data["expiry_iso"]),
            note=str(data.get("note", "")),
        )

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """dict 化. signature は hex str (JSON 化可能) で保持."""
        return {
            "gene_path": self.gene_path,
            "reason": self.reason.value,
            "signature": self.signature.hex(),
            "expiry_iso": self.expiry_iso,
            "note": self.note,
        }

    def to_json_bytes(self) -> bytes:
        """JSON 化して bytes 化 (Kolmogorov complexity proxy 用)."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )

    # ----- Kolmogorov complexity proxy ------------------------------------

    def kolmogorov_proxy(self) -> int:
        """gzip 圧縮後 byte 数. Kolmogorov complexity の計算可能近似.

        MetaChromosome と同一の近似ファミリ (Cilibrasi & Vitanyi 2005
        "Clustering by Compression"). audit log の冗長度比較に使う想定.
        """
        return len(gzip.compress(self.to_json_bytes()))

    # ----- expiry ---------------------------------------------------------

    def is_expired(self, now_iso: str | None = None) -> bool:
        """期限切れか. ``now_iso`` 省略時は UTC 現在時刻と比較.

        Args:
            now_iso: 比較基準時刻 (ISO 8601). 省略時 ``datetime.now(UTC)``.
                テストで再現性のため引数化.

        Returns:
            ``True`` if 期限切れ. 期限と完全一致は **切れていない** 扱い
            (boundary inclusive).
        """
        expiry_dt = _parse_iso8601(self.expiry_iso)
        now_dt = _parse_iso8601(now_iso) if now_iso is not None else _now_utc()
        return now_dt > expiry_dt


__all__ = [
    "MIN_SIGNATURE_BYTES",
    "FreezeReason",
    "FrozenGene",
]
