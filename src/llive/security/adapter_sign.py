# SPDX-License-Identifier: Apache-2.0
"""Signed Adapter Marketplace (SEC-02 / FR-18).

Ed25519 signing + verification for adapter weight files. The signing key
**signs the SHA-256 digest of the weight file plus a deterministic
profile fingerprint**; the verifier reproduces the digest+fingerprint and
checks the signature.

Two operating modes:

* **Local key store** — `~/.config/llive/keys/<publisher>.{pem,pub.pem}`
  files. Convenient for development.
* **Caller-provided keys** — pass `bytes` private/public keys directly.

The module never auto-loads private keys without an explicit path.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from llive.memory.parameter import AdapterProfile


@dataclass
class SignedAdapter:
    """A `(SHA-256, signature)` pair carrying provenance for one adapter file."""

    adapter_id: str
    sha256_hex: str
    signature_hex: str
    publisher: str

    def to_dict(self) -> dict[str, str]:
        return {
            "adapter_id": self.adapter_id,
            "sha256_hex": self.sha256_hex,
            "signature_hex": self.signature_hex,
            "publisher": self.publisher,
        }


def _default_key_dir() -> Path:
    home = Path(os.environ.get("LLIVE_KEY_DIR") or (Path.home() / ".config" / "llive" / "keys"))
    return home


def generate_keypair(
    publisher: str,
    *,
    key_dir: Path | str | None = None,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Create a fresh Ed25519 keypair on disk; return (private, public) paths."""
    out = Path(key_dir) if key_dir else _default_key_dir()
    out.mkdir(parents=True, exist_ok=True)
    priv_path = out / f"{publisher}.pem"
    pub_path = out / f"{publisher}.pub.pem"
    if priv_path.exists() and not overwrite:
        raise FileExistsError(f"private key already exists: {priv_path}")
    sk = Ed25519PrivateKey.generate()
    priv_bytes = sk.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = sk.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_path.write_bytes(priv_bytes)
    pub_path.write_bytes(pub_bytes)
    # owner-only read for private key (best-effort on Windows)
    try:
        priv_path.chmod(0o600)
    except (OSError, NotImplementedError):  # pragma: no cover - Windows
        pass
    return priv_path, pub_path


def load_private_key(path: Path | str) -> Ed25519PrivateKey:
    data = Path(path).read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("not an Ed25519 private key")
    return key


def load_public_key(path: Path | str) -> Ed25519PublicKey:
    data = Path(path).read_bytes()
    key = serialization.load_pem_public_key(data)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("not an Ed25519 public key")
    return key


def _fingerprint(profile: AdapterProfile) -> bytes:
    """Deterministic identity-string for the adapter (excludes sha256/signature)."""
    payload = {
        "id": profile.id,
        "name": profile.name,
        "base_model": profile.base_model,
        "format": profile.format,
        "target_modules": sorted(profile.target_modules),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _sha256_bytes(path: Path) -> bytes:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.digest()


def sign_adapter(
    profile: AdapterProfile,
    weight_path: Path | str,
    private_key: Ed25519PrivateKey,
    *,
    publisher: str,
) -> SignedAdapter:
    """Sign `(sha256 || fingerprint)` with ``private_key``."""
    digest = _sha256_bytes(Path(weight_path))
    payload = digest + b"|" + _fingerprint(profile)
    signature = private_key.sign(payload)
    return SignedAdapter(
        adapter_id=profile.id,
        sha256_hex=digest.hex(),
        signature_hex=signature.hex(),
        publisher=publisher,
    )


def verify_adapter(
    profile: AdapterProfile,
    weight_path: Path | str,
    signed: SignedAdapter,
    public_key: Ed25519PublicKey,
) -> bool:
    """Return True iff signature is valid for the current weight + profile."""
    digest = _sha256_bytes(Path(weight_path))
    if digest.hex() != signed.sha256_hex:
        return False
    payload = digest + b"|" + _fingerprint(profile)
    try:
        public_key.verify(bytes.fromhex(signed.signature_hex), payload)
    except InvalidSignature:
        return False
    return True


__all__ = [
    "SignedAdapter",
    "generate_keypair",
    "load_private_key",
    "load_public_key",
    "sign_adapter",
    "verify_adapter",
]
