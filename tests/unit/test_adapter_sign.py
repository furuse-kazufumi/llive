"""SEC-02 Signed Adapter tests."""

from __future__ import annotations

import pytest

from llive.memory.parameter import AdapterProfile
from llive.security.adapter_sign import (
    generate_keypair,
    load_private_key,
    load_public_key,
    sign_adapter,
    verify_adapter,
)


def _profile(adapter_id: str = "adapter_x", target_modules: tuple[str, ...] = ("q_proj",)) -> AdapterProfile:
    return AdapterProfile(
        id=adapter_id,
        name="x",
        base_model="Qwen/Qwen2.5-0.5B",
        format="lora",
        target_modules=list(target_modules),
    )


@pytest.fixture
def keypair(tmp_path):
    priv_path, pub_path = generate_keypair("alice", key_dir=tmp_path)
    return load_private_key(priv_path), load_public_key(pub_path), priv_path, pub_path


def test_generate_keypair_writes_pem_files(tmp_path):
    priv, pub = generate_keypair("bob", key_dir=tmp_path)
    assert priv.exists()
    assert pub.exists()
    assert b"BEGIN PRIVATE KEY" in priv.read_bytes()
    assert b"BEGIN PUBLIC KEY" in pub.read_bytes()


def test_generate_keypair_refuses_overwrite(tmp_path):
    generate_keypair("alice", key_dir=tmp_path)
    with pytest.raises(FileExistsError):
        generate_keypair("alice", key_dir=tmp_path)


def test_generate_keypair_overwrite_flag(tmp_path):
    p1, _ = generate_keypair("alice", key_dir=tmp_path)
    body1 = p1.read_bytes()
    generate_keypair("alice", key_dir=tmp_path, overwrite=True)
    assert p1.read_bytes() != body1


def test_sign_and_verify_round_trip(keypair, tmp_path):
    sk, pk, _, _ = keypair
    weight = tmp_path / "adapter.safetensors"
    weight.write_bytes(b"x" * 1024)
    profile = _profile()
    signed = sign_adapter(profile, weight, sk, publisher="alice")
    assert signed.publisher == "alice"
    assert len(signed.sha256_hex) == 64
    assert verify_adapter(profile, weight, signed, pk)


def test_verify_fails_when_weights_tampered(keypair, tmp_path):
    sk, pk, _, _ = keypair
    weight = tmp_path / "adapter.safetensors"
    weight.write_bytes(b"x" * 1024)
    profile = _profile()
    signed = sign_adapter(profile, weight, sk, publisher="alice")
    # Tamper
    weight.write_bytes(b"x" * 1024 + b"junk")
    assert not verify_adapter(profile, weight, signed, pk)


def test_verify_fails_when_profile_drifts(keypair, tmp_path):
    sk, pk, _, _ = keypair
    weight = tmp_path / "adapter.safetensors"
    weight.write_bytes(b"x" * 1024)
    profile = _profile(target_modules=("q_proj",))
    signed = sign_adapter(profile, weight, sk, publisher="alice")
    # Drift profile identity
    drifted = _profile(target_modules=("v_proj",))
    assert not verify_adapter(drifted, weight, signed, pk)


def test_verify_fails_with_wrong_public_key(keypair, tmp_path):
    sk, _, _, _ = keypair
    _, other_pub_path = generate_keypair("eve", key_dir=tmp_path)
    other_pk = load_public_key(other_pub_path)
    weight = tmp_path / "adapter.safetensors"
    weight.write_bytes(b"x" * 1024)
    profile = _profile()
    signed = sign_adapter(profile, weight, sk, publisher="alice")
    assert not verify_adapter(profile, weight, signed, other_pk)


def test_load_private_key_type_check(tmp_path):
    # Write a non-Ed25519 key file
    from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
    from cryptography.hazmat.primitives import serialization
    rsa = generate_private_key(public_exponent=65537, key_size=2048)
    p = tmp_path / "rsa.pem"
    p.write_bytes(
        rsa.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    with pytest.raises(TypeError):
        load_private_key(p)


def test_load_public_key_type_check(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
    from cryptography.hazmat.primitives import serialization
    rsa = generate_private_key(public_exponent=65537, key_size=2048)
    p = tmp_path / "rsa.pub.pem"
    p.write_bytes(
        rsa.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    with pytest.raises(TypeError):
        load_public_key(p)


def test_signed_adapter_to_dict(keypair, tmp_path):
    sk, _, _, _ = keypair
    weight = tmp_path / "adapter.safetensors"
    weight.write_bytes(b"x")
    profile = _profile()
    signed = sign_adapter(profile, weight, sk, publisher="alice")
    d = signed.to_dict()
    assert d["adapter_id"] == profile.id
    assert d["publisher"] == "alice"
