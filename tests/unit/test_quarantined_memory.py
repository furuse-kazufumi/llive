# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-04 SEC-01/SEC-02 テスト — Quarantined Memory + Ed25519."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from llive.cognitive_mesh.idle_training import (
    IdleTrainingScheduler,
    InfoSource,
)
from llive.cognitive_mesh.quarantined_memory import (
    Ed25519Verifier,
    QuarantinedMemory,
    SignedPayload,
)
from llive.cognitive_mesh.quiet_hours import QuietHoursGuard


def _make_keypair() -> tuple[bytes, bytes]:
    """新しい Ed25519 keypair を生成. (private_bytes, public_bytes)."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    priv_raw = priv.private_bytes(
        encoding=Encoding.Raw, format=PrivateFormat.Raw, encryption_algorithm=NoEncryption()
    )
    pub_raw = pub.public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return priv_raw, pub_raw


def _active_guard(monkeypatch: pytest.MonkeyPatch) -> QuietHoursGuard:
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    return QuietHoursGuard()


# ---------------------------------------------------------------------------
# Ed25519Verifier
# ---------------------------------------------------------------------------


def test_verifier_register_rejects_wrong_key_length() -> None:
    v = Ed25519Verifier()
    with pytest.raises(ValueError, match="32 bytes"):
        v.register("alice", b"\x00" * 31)


def test_verifier_register_rejects_duplicate_signer_id() -> None:
    v = Ed25519Verifier()
    v.register("alice", b"\x00" * 32)
    with pytest.raises(ValueError, match="already registered"):
        v.register("alice", b"\x00" * 32)


def test_verifier_verify_passes_for_valid_signature() -> None:
    priv_raw, pub_raw = _make_keypair()
    priv = Ed25519PrivateKey.from_private_bytes(priv_raw)
    payload = "hello world"
    sig = priv.sign(payload.encode("utf-8"))
    signed = SignedPayload(payload=payload, signer_id="alice", signature=sig)

    v = Ed25519Verifier()
    v.register("alice", pub_raw)
    assert v.verify(signed) is True


def test_verifier_verify_fails_for_tampered_payload() -> None:
    priv_raw, pub_raw = _make_keypair()
    priv = Ed25519PrivateKey.from_private_bytes(priv_raw)
    sig = priv.sign(b"original")
    signed = SignedPayload(payload="tampered", signer_id="alice", signature=sig)

    v = Ed25519Verifier()
    v.register("alice", pub_raw)
    assert v.verify(signed) is False


def test_verifier_verify_fails_for_unknown_signer() -> None:
    priv_raw, pub_raw = _make_keypair()
    priv = Ed25519PrivateKey.from_private_bytes(priv_raw)
    sig = priv.sign(b"hello")
    signed = SignedPayload(payload="hello", signer_id="unknown", signature=sig)

    v = Ed25519Verifier()
    v.register("alice", pub_raw)
    assert v.verify(signed) is False


def test_verifier_verify_fails_for_unsigned_payload() -> None:
    v = Ed25519Verifier()
    assert v.verify(SignedPayload(payload="hi")) is False


# ---------------------------------------------------------------------------
# QuarantinedMemory lifecycle
# ---------------------------------------------------------------------------


def test_quarantine_without_verifier_auto_promotes() -> None:
    """backward compat: verifier 未設定なら全件 active."""
    mem = QuarantinedMemory()
    e = mem.quarantine("payload-a")
    assert mem.active_items() == [e]
    assert mem.pending() == []


def test_quarantine_with_verifier_pends_unsigned() -> None:
    mem = QuarantinedMemory(verifier=Ed25519Verifier())
    e = mem.quarantine("unsigned")
    assert mem.pending() == [e]
    assert mem.active_items() == []
    assert e.verified is False


def test_quarantine_with_valid_signature_auto_promotes() -> None:
    priv_raw, pub_raw = _make_keypair()
    verifier = Ed25519Verifier()
    verifier.register("alice", pub_raw)
    mem = QuarantinedMemory(verifier=verifier)
    signed = IdleTrainingScheduler.sign_payload("hello", "alice", priv_raw)
    e = mem.quarantine(signed)
    assert e.verified is True
    assert mem.active_items() == [e]


def test_quarantine_with_invalid_signature_stays_pending() -> None:
    _priv_raw, pub_raw = _make_keypair()
    bad_priv_raw, _ = _make_keypair()  # 異なる鍵で署名
    verifier = Ed25519Verifier()
    verifier.register("alice", pub_raw)
    mem = QuarantinedMemory(verifier=verifier)
    signed = IdleTrainingScheduler.sign_payload("hello", "alice", bad_priv_raw)
    e = mem.quarantine(signed)
    assert e.verified is False
    assert mem.pending() == [e]


def test_quarantine_operator_promote_and_reject() -> None:
    mem = QuarantinedMemory(verifier=Ed25519Verifier())
    e1 = mem.quarantine("a")
    e2 = mem.quarantine("b")
    mem.promote(e1.event_id)
    mem.reject(e2.event_id, reason="suspect")
    assert [x.event_id for x in mem.active_items()] == [e1.event_id]
    assert [x.event_id for x in mem.rejected()] == [e2.event_id]
    assert mem.rejected()[0].rejection_reason == "suspect"


def test_quarantine_promote_unknown_raises() -> None:
    mem = QuarantinedMemory(verifier=Ed25519Verifier())
    with pytest.raises(KeyError):
        mem.promote("does-not-exist")


def test_quarantine_no_auto_promote_when_disabled() -> None:
    priv_raw, pub_raw = _make_keypair()
    verifier = Ed25519Verifier()
    verifier.register("alice", pub_raw)
    mem = QuarantinedMemory(verifier=verifier, auto_promote_verified=False)
    signed = IdleTrainingScheduler.sign_payload("x", "alice", priv_raw)
    e = mem.quarantine(signed)
    # 検証通過したが auto_promote=False → pending
    assert e.verified is True
    assert mem.pending() == [e]


# ---------------------------------------------------------------------------
# IdleTrainingScheduler integration
# ---------------------------------------------------------------------------


def test_scheduler_without_quarantine_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """backward compat: quarantine 未注入は従来通り."""
    sched = IdleTrainingScheduler(quiet_hours=_active_guard(monkeypatch))
    sched.register(InfoSource(name="rss", fetch=lambda: "feed-data"))
    # idle_threshold は最初 0 (history 無し)
    from datetime import datetime

    event = sched.tick(now=datetime(2026, 5, 19, 10, 0, 0))
    assert event is not None
    assert event.payload == "feed-data"
    assert sched.latest_quarantine_entries() == []


def test_scheduler_with_quarantine_routes_through_signed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    priv_raw, pub_raw = _make_keypair()
    verifier = Ed25519Verifier()
    verifier.register("trusted-rss", pub_raw)
    qmem = QuarantinedMemory(verifier=verifier)

    sched = IdleTrainingScheduler(
        quiet_hours=_active_guard(monkeypatch), quarantine=qmem
    )

    # 信頼 source: 署名つき payload を返す
    def fetch_signed() -> SignedPayload:
        return IdleTrainingScheduler.sign_payload(
            "trusted-news", "trusted-rss", priv_raw
        )

    sched.register(InfoSource(name="rss", fetch=fetch_signed))
    from datetime import datetime

    event = sched.tick(now=datetime(2026, 5, 19, 10, 0, 0))
    assert event is not None
    # quarantine entry が active に居る
    assert len(qmem.active_items()) == 1
    assert qmem.active_items()[0].verified is True
    assert len(sched.latest_quarantine_entries()) == 1


def test_scheduler_with_quarantine_unsigned_source_pends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qmem = QuarantinedMemory(verifier=Ed25519Verifier())
    sched = IdleTrainingScheduler(
        quiet_hours=_active_guard(monkeypatch), quarantine=qmem
    )
    sched.register(InfoSource(name="unsigned", fetch=lambda: "raw"))
    from datetime import datetime

    sched.tick(now=datetime(2026, 5, 19, 10, 0, 0))
    # 署名無し → pending に
    assert len(qmem.pending()) == 1
    assert len(qmem.active_items()) == 0
