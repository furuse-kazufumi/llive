# SPDX-License-Identifier: Apache-2.0
"""Tests for migration.encryption (C-6 AES-GCM bundle encryption)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from llive.migration import export_state
from llive.migration.encryption import (
    KEY_BYTES,
    MAGIC,
    SALT_BYTES,
    BundleCryptoError,
    decrypt_bundle,
    decrypt_bundle_with_password,
    derive_key,
    encrypt_bundle,
    encrypt_bundle_with_password,
    key_fingerprint,
)


def _make_bundle(tmp_path: Path) -> Path:
    out = tmp_path / "bundle.tar.gz"
    export_state(
        ledger_path=None, sandbox=None, production_bus=None, out_path=out
    )
    return out


# ---------------------------------------------------------------------------
# Direct-key path
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_round_trip(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    original = out.read_bytes()

    key = os.urandom(KEY_BYTES)
    enc_path = encrypt_bundle(out, key)
    assert enc_path.exists()
    assert enc_path.read_bytes().startswith(MAGIC)

    dec_path = decrypt_bundle(enc_path, key, out_path=tmp_path / "restored.tar.gz")
    assert dec_path.read_bytes() == original


def test_encrypt_rejects_short_key(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    with pytest.raises(BundleCryptoError, match=r"key must be"):
        encrypt_bundle(out, b"\x00" * 31)


def test_decrypt_rejects_wrong_key(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    key = os.urandom(KEY_BYTES)
    enc = encrypt_bundle(out, key)
    with pytest.raises(BundleCryptoError, match="authentication failed"):
        decrypt_bundle(enc, os.urandom(KEY_BYTES))


def test_decrypt_rejects_tampered_ciphertext(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    key = os.urandom(KEY_BYTES)
    enc = encrypt_bundle(out, key)
    blob = bytearray(enc.read_bytes())
    blob[-1] ^= 0x01  # flip a byte in the GCM tag region
    enc.write_bytes(bytes(blob))
    with pytest.raises(BundleCryptoError, match="authentication failed"):
        decrypt_bundle(enc, key)


def test_decrypt_rejects_missing_magic(tmp_path: Path) -> None:
    fake = tmp_path / "fake.enc"
    fake.write_bytes(b"NOPE" + os.urandom(64))
    with pytest.raises(BundleCryptoError, match="missing magic header"):
        decrypt_bundle(fake, os.urandom(KEY_BYTES))


def test_each_encryption_produces_distinct_ciphertext(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    key = os.urandom(KEY_BYTES)
    a = encrypt_bundle(out, key, out_path=tmp_path / "a.enc").read_bytes()
    b = encrypt_bundle(out, key, out_path=tmp_path / "b.enc").read_bytes()
    # Same key, same plaintext, but a fresh random nonce → ciphertext differs.
    assert a != b


# ---------------------------------------------------------------------------
# Password / scrypt path
# ---------------------------------------------------------------------------


def test_derive_key_is_deterministic_for_same_inputs() -> None:
    salt = b"\x00" * SALT_BYTES
    k1 = derive_key("correct horse", salt)
    k2 = derive_key("correct horse", salt)
    assert k1 == k2
    assert len(k1) == KEY_BYTES


def test_derive_key_rejects_empty_password() -> None:
    with pytest.raises(BundleCryptoError, match="non-empty"):
        derive_key("", b"\x00" * SALT_BYTES)


def test_derive_key_rejects_short_salt() -> None:
    with pytest.raises(BundleCryptoError, match="salt"):
        derive_key("x", b"\x00")


def test_password_round_trip(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    original = out.read_bytes()
    enc_path, salt = encrypt_bundle_with_password(out, "p@ssw0rd")
    dec_path = decrypt_bundle_with_password(
        enc_path, "p@ssw0rd", salt, out_path=tmp_path / "restored.tar.gz"
    )
    assert dec_path.read_bytes() == original


def test_password_round_trip_rejects_wrong_password(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    enc_path, salt = encrypt_bundle_with_password(out, "right")
    with pytest.raises(BundleCryptoError, match="authentication failed"):
        decrypt_bundle_with_password(enc_path, "wrong", salt)


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def test_key_fingerprint_is_short_hex() -> None:
    key = os.urandom(KEY_BYTES)
    fp = key_fingerprint(key)
    assert len(fp) == 16
    int(fp, 16)


def test_key_fingerprint_rejects_short_key() -> None:
    with pytest.raises(BundleCryptoError):
        key_fingerprint(b"\x00" * 16)
