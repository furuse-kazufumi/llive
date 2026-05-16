# SPDX-License-Identifier: Apache-2.0
"""Tests for migration.integrity (C-5 bundle hash + signature)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from llive.migration import export_state
from llive.migration.integrity import (
    BundleIntegrityError,
    compute_bundle_sha256,
    sign_bundle,
    verify_bundle_sha256,
    verify_bundle_signature,
    write_bundle_sha256,
)


def _make_bundle(tmp_path: Path) -> Path:
    out = tmp_path / "bundle.tar.gz"
    export_state(
        ledger_path=None, sandbox=None, production_bus=None, out_path=out
    )
    return out


# ---------------------------------------------------------------------------
# SHA-256 integrity
# ---------------------------------------------------------------------------


def test_compute_sha256_is_stable(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    h1 = compute_bundle_sha256(out)
    h2 = compute_bundle_sha256(out)
    assert h1 == h2
    assert len(h1) == 64


def test_write_and_verify_sha256_round_trip(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    hash_path = write_bundle_sha256(out)
    assert hash_path.exists()
    digest = verify_bundle_sha256(out)
    assert len(digest) == 64


def test_verify_sha256_detects_tamper(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    write_bundle_sha256(out)
    # Flip a byte in the bundle
    data = bytearray(out.read_bytes())
    data[-1] ^= 0x01
    out.write_bytes(bytes(data))
    with pytest.raises(BundleIntegrityError, match="mismatch"):
        verify_bundle_sha256(out)


def test_verify_sha256_missing_hash_file(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    with pytest.raises(BundleIntegrityError, match="hash file missing"):
        verify_bundle_sha256(out)


# ---------------------------------------------------------------------------
# Ed25519 signature
# ---------------------------------------------------------------------------


def test_sign_and_verify_round_trip(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    sk = Ed25519PrivateKey.generate()
    sig_path = sign_bundle(out, sk)
    assert sig_path.exists()
    verify_bundle_signature(out, sk.public_key())  # does not raise


def test_verify_signature_detects_tamper(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    sk = Ed25519PrivateKey.generate()
    sign_bundle(out, sk)
    data = bytearray(out.read_bytes())
    data[0] ^= 0x01
    out.write_bytes(bytes(data))
    with pytest.raises(BundleIntegrityError, match="verification failed"):
        verify_bundle_signature(out, sk.public_key())


def test_verify_signature_rejects_wrong_key(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    sign_bundle(out, Ed25519PrivateKey.generate())
    foreign = Ed25519PrivateKey.generate().public_key()
    with pytest.raises(BundleIntegrityError, match="verification failed"):
        verify_bundle_signature(out, foreign)


def test_verify_signature_missing_sig_file(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    pk = Ed25519PrivateKey.generate().public_key()
    with pytest.raises(BundleIntegrityError, match="signature file missing"):
        verify_bundle_signature(out, pk)


def test_signature_payload_is_hex_only(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    sk = Ed25519PrivateKey.generate()
    sig_path = sign_bundle(out, sk)
    text = sig_path.read_text(encoding="utf-8").strip()
    # Ed25519 sig = 64 bytes = 128 hex
    assert len(text) == 128
    int(text, 16)  # not malformed hex


def test_custom_paths_for_hash_and_sig(tmp_path: Path) -> None:
    out = _make_bundle(tmp_path)
    sk = Ed25519PrivateKey.generate()
    custom_hash = tmp_path / "side" / "bundle.hash"
    custom_sig = tmp_path / "side" / "bundle.sig"
    custom_hash.parent.mkdir(parents=True)
    write_bundle_sha256(out, hash_path=custom_hash)
    sign_bundle(out, sk, sig_out=custom_sig)
    verify_bundle_sha256(out, hash_path=custom_hash)
    verify_bundle_signature(out, sk.public_key(), sig_path=custom_sig)
