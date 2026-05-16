# SPDX-License-Identifier: Apache-2.0
"""Bundle integrity + Ed25519 signature (C-5).

The C-3 / C-4 bundle format is plain tar.gz: anyone holding the file can
read its contents. C-5 adds *detection* of tampering and *attribution*
of the export to a known publisher, without changing the bundle layout
itself (backward-compatible with v1 bundles).

Two layers:

* **Integrity hash** — ``compute_bundle_sha256(bundle_path)`` returns the
  SHA-256 hex digest of the bundle bytes. Stored alongside the bundle as
  ``<bundle>.sha256`` (text). Verified by
  ``verify_bundle_sha256(bundle_path, hash_path=None)``.

* **Ed25519 signature** — ``sign_bundle(bundle_path, private_key, sig_out=None)``
  signs the SHA-256 digest (not the full file body) with an Ed25519 key
  and writes the signature hex to ``<bundle>.sig``.
  ``verify_bundle_signature(bundle_path, public_key, sig_path=None)``
  reproduces the digest and validates the signature; raises
  ``BundleIntegrityError`` on failure.

The signature lives **outside** the tar so the bundle format never has to
break a hash cycle. Hashes can be re-computed by anyone, signatures
require the corresponding public key — which is the right trust split
for cross-substrate migration.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

_CHUNK = 64 * 1024


class BundleIntegrityError(RuntimeError):
    """Raised when a hash or signature check fails."""


def compute_bundle_sha256(bundle_path: Path | str) -> str:
    """SHA-256 hex digest of the bundle bytes (streaming, constant memory)."""
    h = hashlib.sha256()
    with Path(bundle_path).open("rb") as fh:
        while True:
            block = fh.read(_CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def write_bundle_sha256(
    bundle_path: Path | str, *, hash_path: Path | str | None = None
) -> Path:
    """Compute and store the bundle hash. Default location: ``<bundle>.sha256``."""
    digest = compute_bundle_sha256(bundle_path)
    target = Path(hash_path) if hash_path else Path(str(bundle_path) + ".sha256")
    target.write_text(digest + "\n", encoding="utf-8")
    return target


def verify_bundle_sha256(
    bundle_path: Path | str, *, hash_path: Path | str | None = None
) -> str:
    """Verify the bundle matches its recorded SHA-256. Returns the digest.

    Raises:
        BundleIntegrityError: digest mismatch or hash file missing.
    """
    target = Path(hash_path) if hash_path else Path(str(bundle_path) + ".sha256")
    if not target.exists():
        raise BundleIntegrityError(f"hash file missing: {target!r}")
    expected = target.read_text(encoding="utf-8").strip().split()[0]
    actual = compute_bundle_sha256(bundle_path)
    if expected != actual:
        raise BundleIntegrityError(
            f"bundle sha256 mismatch (expected {expected!r}, got {actual!r})"
        )
    return actual


def sign_bundle(
    bundle_path: Path | str,
    private_key: Ed25519PrivateKey,
    *,
    sig_out: Path | str | None = None,
) -> Path:
    """Sign the bundle's SHA-256 digest with an Ed25519 key.

    Returns the path of the signature file (default ``<bundle>.sig``).
    The signature payload is the raw 32-byte digest (not the hex form) —
    same convention as ``llive.security.adapter_sign``.
    """
    digest_hex = compute_bundle_sha256(bundle_path)
    sig = private_key.sign(bytes.fromhex(digest_hex))
    target = Path(sig_out) if sig_out else Path(str(bundle_path) + ".sig")
    target.write_text(sig.hex() + "\n", encoding="utf-8")
    return target


def verify_bundle_signature(
    bundle_path: Path | str,
    public_key: Ed25519PublicKey,
    *,
    sig_path: Path | str | None = None,
) -> None:
    """Verify the signature attached to a bundle. Raises on failure."""
    sig_file = Path(sig_path) if sig_path else Path(str(bundle_path) + ".sig")
    if not sig_file.exists():
        raise BundleIntegrityError(f"signature file missing: {sig_file!r}")
    sig_hex = sig_file.read_text(encoding="utf-8").strip().split()[0]
    try:
        signature = bytes.fromhex(sig_hex)
    except ValueError as exc:
        raise BundleIntegrityError(f"signature not hex: {sig_file!r}") from exc
    digest_hex = compute_bundle_sha256(bundle_path)
    try:
        public_key.verify(signature, bytes.fromhex(digest_hex))
    except InvalidSignature as exc:
        raise BundleIntegrityError(
            f"Ed25519 signature verification failed for {bundle_path!r}"
        ) from exc


__all__ = [
    "BundleIntegrityError",
    "compute_bundle_sha256",
    "sign_bundle",
    "verify_bundle_sha256",
    "verify_bundle_signature",
    "write_bundle_sha256",
]
