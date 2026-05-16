# SPDX-License-Identifier: Apache-2.0
"""Optional bundle encryption (C-6).

Wraps a C-3 / C-4 tar.gz bundle in AES-256-GCM. The encrypted form is a
single binary file with the layout::

    magic       (8 bytes)   b"LLIVE1\\x00\\x00"
    nonce       (12 bytes)  random per encryption
    ciphertext  (N bytes)   = AES-GCM(bundle_bytes)
    tag         (16 bytes)  appended by AESGCM API

The tag is part of the ciphertext output of ``AESGCM.encrypt`` so we
just concatenate ``nonce + ciphertext``. Authenticated associated data
is the magic prefix, which forces the file to keep its format.

Two key-derivation paths:

* **Direct key** — caller supplies 32 raw bytes (AES-256).
* **Password** — ``derive_key(password, salt)`` runs scrypt
  (N=2**15, r=8, p=1) and returns 32 bytes. The salt must be stored
  alongside the file (we use the first 16 bytes of the nonce slot when
  password mode is active; see ``encrypt_bundle_with_password``).

Integrity (`BundleIntegrityError` analogue) and confidentiality combine
cleanly: encrypt **first**, then sign the resulting ``.enc`` file with
the Phase 3.5 signature. The verify pipeline runs in the reverse order.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"LLIVE1\x00\x00"
NONCE_BYTES = 12
SALT_BYTES = 16
KEY_BYTES = 32  # AES-256
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1


class BundleCryptoError(RuntimeError):
    """Raised when encryption inputs are invalid or decryption fails."""


def derive_key(password: str | bytes, salt: bytes) -> bytes:
    """Scrypt-derive a 32-byte AES-256 key from a password + salt."""
    if not password:
        raise BundleCryptoError("password must be non-empty")
    if len(salt) != SALT_BYTES:
        raise BundleCryptoError(f"salt must be {SALT_BYTES} bytes")
    pwd = password.encode("utf-8") if isinstance(password, str) else password
    kdf = Scrypt(salt=salt, length=KEY_BYTES, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return kdf.derive(pwd)


def _validate_key(key: bytes) -> None:
    if len(key) != KEY_BYTES:
        raise BundleCryptoError(f"key must be {KEY_BYTES} bytes (AES-256)")


def encrypt_bundle(
    bundle_path: Path | str,
    key: bytes,
    *,
    out_path: Path | str | None = None,
) -> Path:
    """AES-256-GCM encrypt ``bundle_path`` → ``out_path`` (default ``.enc``).

    Output layout: ``magic || nonce || ciphertext_with_tag``.
    """
    _validate_key(key)
    src = Path(bundle_path)
    target = Path(out_path) if out_path else Path(str(bundle_path) + ".enc")
    plaintext = src.read_bytes()
    nonce = os.urandom(NONCE_BYTES)
    aead = AESGCM(key)
    ct = aead.encrypt(nonce, plaintext, MAGIC)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(MAGIC + nonce + ct)
    return target


def decrypt_bundle(
    enc_path: Path | str,
    key: bytes,
    *,
    out_path: Path | str | None = None,
) -> Path:
    """AES-256-GCM decrypt → ``out_path`` (default strips ``.enc``)."""
    _validate_key(key)
    src = Path(enc_path)
    blob = src.read_bytes()
    if not blob.startswith(MAGIC):
        raise BundleCryptoError(f"missing magic header in {enc_path!r}")
    header_end = len(MAGIC) + NONCE_BYTES
    nonce = blob[len(MAGIC):header_end]
    ct = blob[header_end:]
    aead = AESGCM(key)
    try:
        plaintext = aead.decrypt(nonce, ct, MAGIC)
    except InvalidTag as exc:
        raise BundleCryptoError(
            f"AES-GCM authentication failed for {enc_path!r}"
        ) from exc
    if out_path is None:
        s = str(src)
        target = Path(s[: -len(".enc")]) if s.endswith(".enc") else Path(s + ".dec")
    else:
        target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(plaintext)
    return target


def encrypt_bundle_with_password(
    bundle_path: Path | str,
    password: str | bytes,
    *,
    out_path: Path | str | None = None,
) -> tuple[Path, bytes]:
    """Password-based encryption: scrypt(password, salt) → key.

    Returns ``(enc_path, salt)``. The salt must be stored to enable
    decryption (this function does NOT side-channel the salt into the
    encrypted file because the existing layout is fixed; callers that
    want a self-contained format should switch to ``encrypt_bundle`` and
    derive the key out-of-band, or embed the salt in a sidecar file).
    """
    salt = os.urandom(SALT_BYTES)
    key = derive_key(password, salt)
    enc_path = encrypt_bundle(bundle_path, key, out_path=out_path)
    return enc_path, salt


def decrypt_bundle_with_password(
    enc_path: Path | str,
    password: str | bytes,
    salt: bytes,
    *,
    out_path: Path | str | None = None,
) -> Path:
    """Password counterpart to ``decrypt_bundle``."""
    key = derive_key(password, salt)
    return decrypt_bundle(enc_path, key, out_path=out_path)


def key_fingerprint(key: bytes) -> str:
    """Short SHA-256-based fingerprint for audit logs (NOT a key-recovery hint)."""
    _validate_key(key)
    return hashlib.sha256(key).hexdigest()[:16]


__all__ = [
    "KEY_BYTES",
    "MAGIC",
    "NONCE_BYTES",
    "SALT_BYTES",
    "BundleCryptoError",
    "decrypt_bundle",
    "decrypt_bundle_with_password",
    "derive_key",
    "encrypt_bundle",
    "encrypt_bundle_with_password",
    "key_fingerprint",
]
