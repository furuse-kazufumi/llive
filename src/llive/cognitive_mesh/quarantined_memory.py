# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-04 SEC-01 — Quarantined Memory + SEC-02 Ed25519 signature.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-04 で予告した「ingest した
content は Quarantined Memory に着地し、署名検証通過分のみ active memory
に昇格する」を最小実装。

設計:
- ``SignedPayload`` — payload + signature + signer_id の triple. 署名なし
  ingest は ``SignedPayload(payload, signature=None)`` 相当として扱える.
- ``Ed25519Verifier`` — ``signer_id -> public_key (32 bytes)`` を保持。
  ``verify(signed) -> bool`` で 1 件検証。public_key 未登録は False (fail-closed).
- ``QuarantinedMemory`` — quarantine() で隔離領域に積み、promote()/reject()
  で出口を決める。``active_items()`` で承認済を取り出す.

セキュリティ境界:
- 署名検証が False → quarantine 行き → 自動 promote しない (operator review
  が必要).
- verifier 未設定 → 既定で「全件 promote」(backward compat: 既存挙動)。実
  運用では verifier を注入することを推奨。
- promote/reject は ledger に時刻つきで残す (audit).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


@dataclass(frozen=True)
class SignedPayload:
    """署名つき ingest payload."""

    payload: Any
    signer_id: str | None = None
    signature: bytes | None = None
    """payload を canonical bytes 化 (str(payload).encode()) したものへの署名."""

    def is_signed(self) -> bool:
        return self.signer_id is not None and self.signature is not None


@dataclass
class Ed25519Verifier:
    """signer_id -> Ed25519 公開鍵 を保持し、SignedPayload を検証する."""

    public_keys: dict[str, bytes] = field(default_factory=dict)

    def register(self, signer_id: str, public_key: bytes) -> None:
        if len(public_key) != 32:
            raise ValueError("Ed25519 public key must be 32 bytes")
        if signer_id in self.public_keys:
            raise ValueError(f"signer_id '{signer_id}' already registered")
        self.public_keys[signer_id] = public_key

    def verify(self, signed: SignedPayload) -> bool:
        if not signed.is_signed():
            return False
        assert signed.signer_id is not None
        assert signed.signature is not None
        pub_raw = self.public_keys.get(signed.signer_id)
        if pub_raw is None:
            return False
        try:
            pub = Ed25519PublicKey.from_public_bytes(pub_raw)
            pub.verify(signed.signature, str(signed.payload).encode("utf-8"))
        except (InvalidSignature, ValueError):
            return False
        return True


@dataclass
class QuarantineEntry:
    event_id: str
    payload: Any
    signer_id: str | None
    quarantined_at: datetime
    promoted_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str = ""
    verified: bool = False


@dataclass
class QuarantinedMemory:
    """隔離 → 検証 → promote/reject のライフサイクル管理.

    Attributes:
        verifier: Ed25519Verifier (注入時) — quarantine() で自動検証.
        auto_promote_verified: True なら検証通過した entry を即時 active
            に昇格 (operator review を経ない). 既定 True.
    """

    verifier: Ed25519Verifier | None = None
    auto_promote_verified: bool = True
    _pending: dict[str, QuarantineEntry] = field(default_factory=dict)
    _active: dict[str, QuarantineEntry] = field(default_factory=dict)
    _rejected: dict[str, QuarantineEntry] = field(default_factory=dict)
    _counter: int = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"qmem-{self._counter:06d}"

    def quarantine(
        self,
        signed: SignedPayload | Any,
        now: datetime | None = None,
    ) -> QuarantineEntry:
        """1 件 ingest を隔離領域に積む.

        SignedPayload 以外は signature 無し扱い (signer_id=None, signature=None).
        verifier 設定済かつ auto_promote_verified=True なら、検証通過した entry
        は即時 active に移動.
        """
        if now is None:
            now = datetime.now()
        if isinstance(signed, SignedPayload):
            payload = signed.payload
            signer_id = signed.signer_id
        else:
            payload = signed
            signed = SignedPayload(payload=payload)
            signer_id = None
        entry = QuarantineEntry(
            event_id=self._next_id(),
            payload=payload,
            signer_id=signer_id,
            quarantined_at=now,
        )
        # 検証
        if self.verifier is not None and signed.is_signed():
            entry.verified = self.verifier.verify(signed)
        # 配置
        if entry.verified and self.auto_promote_verified:
            entry.promoted_at = now
            self._active[entry.event_id] = entry
        elif self.verifier is None:
            # backward compat: verifier 未設定なら全件 active へ
            entry.promoted_at = now
            self._active[entry.event_id] = entry
        else:
            # 未検証 / 検証失敗 → pending
            self._pending[entry.event_id] = entry
        return entry

    def promote(self, event_id: str, now: datetime | None = None) -> QuarantineEntry:
        """operator 判断で pending → active に昇格 (検証通過してなくても可)."""
        if event_id not in self._pending:
            raise KeyError(f"unknown pending event_id: {event_id!r}")
        if now is None:
            now = datetime.now()
        entry = self._pending.pop(event_id)
        entry.promoted_at = now
        self._active[event_id] = entry
        return entry

    def reject(
        self, event_id: str, *, reason: str = "", now: datetime | None = None
    ) -> QuarantineEntry:
        """operator 判断で pending → rejected に移動."""
        if event_id not in self._pending:
            raise KeyError(f"unknown pending event_id: {event_id!r}")
        if now is None:
            now = datetime.now()
        entry = self._pending.pop(event_id)
        entry.rejected_at = now
        entry.rejection_reason = reason
        self._rejected[event_id] = entry
        return entry

    def active_items(self) -> list[QuarantineEntry]:
        return list(self._active.values())

    def pending(self) -> list[QuarantineEntry]:
        return list(self._pending.values())

    def rejected(self) -> list[QuarantineEntry]:
        return list(self._rejected.values())

    def __len__(self) -> int:
        return len(self._active) + len(self._pending) + len(self._rejected)

    def __contains__(self, event_id: str) -> bool:
        return (
            event_id in self._active
            or event_id in self._pending
            or event_id in self._rejected
        )

    def iter_all(self) -> Iterable[QuarantineEntry]:
        yield from self._active.values()
        yield from self._pending.values()
        yield from self._rejected.values()


__all__ = [
    "Ed25519Verifier",
    "QuarantineEntry",
    "QuarantinedMemory",
    "SignedPayload",
]
