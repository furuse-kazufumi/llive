# SPDX-License-Identifier: Apache-2.0
"""FrozenGene + FrozenGeneRegistry (v0.I EV-34 skeleton) — unit tests.

ユーザー指示 (2026-05-22) "v0.I 案 D Frozen Ethics Gene" 着地検証.

カバー範囲:

1. FrozenGene 各 reason の構築
2. FrozenGene バリデーション (空 path / signature 短い / invalid expiry / note 型)
3. serialization round-trip (hex / bytes / list 入力)
4. kolmogorov_proxy
5. is_expired (期限内 / 期限切れ / 境界 / now_iso 引数化)
6. Registry register / is_frozen / list_active
7. Registry violates (完全一致 / prefix [ / prefix . / 期限切れ無視)
8. Registry prune_expired
9. Registry serialization round-trip
10. Registry __len__ / __contains__ / unregister

実 Approval Bus 統合 + Ed25519 verify は v0.I.4 次フェーズ.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from llive.perf.evolutionary.frozen_gene import (
    MIN_SIGNATURE_BYTES,
    FreezeReason,
    FrozenGene,
)
from llive.perf.evolutionary.experimental.frozen_registry import FrozenGeneRegistry

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


SIG_OK: bytes = b"\xab" * MIN_SIGNATURE_BYTES          # 32 bytes
SIG_LONG: bytes = b"\xcd" * (MIN_SIGNATURE_BYTES * 2)  # 64 bytes (Ed25519 想定)

FUTURE_ISO = "2099-12-31T00:00:00Z"
PAST_ISO = "2000-01-01T00:00:00Z"


def _make_gene(
    path: str = "C-prompt.persona_set[0]",
    reason: FreezeReason = FreezeReason.ETHICS,
    expiry: str = FUTURE_ISO,
    note: str = "",
    signature: bytes = SIG_OK,
) -> FrozenGene:
    return FrozenGene(
        gene_path=path,
        reason=reason,
        signature=signature,
        expiry_iso=expiry,
        note=note,
    )


# ===========================================================================
# 1. FrozenGene — 各 reason の構築
# ===========================================================================


@pytest.mark.parametrize(
    "reason",
    [
        FreezeReason.ETHICS,
        FreezeReason.SECURITY,
        FreezeReason.REGULATION,
        FreezeReason.IP,
        FreezeReason.SAFETY,
    ],
)
def test_frozen_gene_constructs_for_each_reason(reason: FreezeReason) -> None:
    g = _make_gene(reason=reason)
    assert g.reason is reason
    assert g.gene_path == "C-prompt.persona_set[0]"


def test_default_factory_is_valid() -> None:
    g = FrozenGene.default()
    assert isinstance(g, FrozenGene)
    assert g.reason is FreezeReason.ETHICS


# ===========================================================================
# 2. FrozenGene — バリデーション
# ===========================================================================


def test_rejects_empty_gene_path() -> None:
    with pytest.raises(ValueError, match="gene_path"):
        _make_gene(path="")


def test_rejects_whitespace_gene_path() -> None:
    with pytest.raises(ValueError, match="gene_path"):
        _make_gene(path="   ")


def test_rejects_non_str_gene_path() -> None:
    with pytest.raises(ValueError, match="gene_path"):
        FrozenGene(
            gene_path=123,  # type: ignore[arg-type]
            reason=FreezeReason.ETHICS,
            signature=SIG_OK,
            expiry_iso=FUTURE_ISO,
        )


def test_rejects_non_enum_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        FrozenGene(
            gene_path="C-impl.foo",
            reason="ETHICS",  # type: ignore[arg-type]
            signature=SIG_OK,
            expiry_iso=FUTURE_ISO,
        )


def test_rejects_short_signature() -> None:
    with pytest.raises(ValueError, match="signature"):
        _make_gene(signature=b"\x00" * (MIN_SIGNATURE_BYTES - 1))


def test_rejects_non_bytes_signature() -> None:
    with pytest.raises(ValueError, match="signature"):
        FrozenGene(
            gene_path="C-impl.foo",
            reason=FreezeReason.ETHICS,
            signature="not-bytes",  # type: ignore[arg-type]
            expiry_iso=FUTURE_ISO,
        )


def test_accepts_bytearray_signature() -> None:
    g = _make_gene(signature=bytearray(b"\x00" * MIN_SIGNATURE_BYTES))
    assert len(g.signature) == MIN_SIGNATURE_BYTES


def test_rejects_invalid_expiry_iso() -> None:
    with pytest.raises(ValueError, match="expiry_iso"):
        _make_gene(expiry="not-an-iso-date")


def test_rejects_empty_expiry_iso() -> None:
    with pytest.raises(ValueError, match="expiry_iso"):
        _make_gene(expiry="")


def test_accepts_iso_with_offset() -> None:
    g = _make_gene(expiry="2030-06-15T12:00:00+09:00")
    assert g.expiry_iso == "2030-06-15T12:00:00+09:00"


def test_accepts_iso_with_z_suffix() -> None:
    g = _make_gene(expiry="2030-06-15T12:00:00Z")
    assert g.expiry_iso.endswith("Z")


def test_rejects_non_str_note() -> None:
    with pytest.raises(ValueError, match="note"):
        FrozenGene(
            gene_path="C-impl.foo",
            reason=FreezeReason.ETHICS,
            signature=SIG_OK,
            expiry_iso=FUTURE_ISO,
            note=123,  # type: ignore[arg-type]
        )


# ===========================================================================
# 3. serialization round-trip
# ===========================================================================


def test_serialization_round_trip_basic() -> None:
    g = _make_gene(note="EU AI Act Art. 5 (a)")
    restored = FrozenGene.from_dict(g.to_dict())
    assert restored == g


def test_serialization_signature_is_hex_str() -> None:
    g = _make_gene(signature=SIG_LONG)
    d = g.to_dict()
    assert isinstance(d["signature"], str)
    assert d["signature"] == SIG_LONG.hex()


def test_from_dict_accepts_bytes_signature() -> None:
    g = _make_gene()
    raw = {**g.to_dict(), "signature": g.signature}  # raw bytes
    restored = FrozenGene.from_dict(raw)
    assert restored == g


def test_from_dict_accepts_list_signature() -> None:
    g = _make_gene()
    raw = {**g.to_dict(), "signature": list(g.signature)}
    restored = FrozenGene.from_dict(raw)
    assert restored == g


def test_from_dict_rejects_unsupported_signature_type() -> None:
    g = _make_gene()
    raw = {**g.to_dict(), "signature": 12345}
    with pytest.raises(ValueError, match="signature"):
        FrozenGene.from_dict(raw)


def test_from_dict_default_note_empty() -> None:
    g = _make_gene()
    d = g.to_dict()
    d.pop("note")
    restored = FrozenGene.from_dict(d)
    assert restored.note == ""


# ===========================================================================
# 4. Kolmogorov complexity proxy
# ===========================================================================


def test_kolmogorov_proxy_positive() -> None:
    g = _make_gene()
    assert g.kolmogorov_proxy() > 20


def test_kolmogorov_proxy_grows_with_note_size() -> None:
    short = _make_gene(note="x")
    long = _make_gene(note="x" * 500)
    assert long.kolmogorov_proxy() > short.kolmogorov_proxy()


# ===========================================================================
# 5. is_expired
# ===========================================================================


def test_is_expired_future_returns_false() -> None:
    assert _make_gene(expiry=FUTURE_ISO).is_expired() is False


def test_is_expired_past_returns_true() -> None:
    assert _make_gene(expiry=PAST_ISO).is_expired() is True


def test_is_expired_now_iso_override() -> None:
    g = _make_gene(expiry="2030-01-01T00:00:00Z")
    # 2029 → not expired
    assert g.is_expired(now_iso="2029-12-31T23:59:59Z") is False
    # 2031 → expired
    assert g.is_expired(now_iso="2031-01-01T00:00:00Z") is True


def test_is_expired_boundary_inclusive_not_expired() -> None:
    """期限 == 現在時刻 → 切れていない (boundary inclusive)."""
    expiry = "2030-01-01T00:00:00Z"
    g = _make_gene(expiry=expiry)
    assert g.is_expired(now_iso=expiry) is False


def test_is_expired_uses_current_time_by_default() -> None:
    near_past = (
        datetime.now(UTC) - timedelta(days=1)
    ).isoformat()
    g = _make_gene(expiry=near_past)
    assert g.is_expired() is True


# ===========================================================================
# 6. Registry register / is_frozen / list_active
# ===========================================================================


def test_registry_empty_initial_state() -> None:
    reg = FrozenGeneRegistry()
    assert len(reg) == 0
    assert reg.is_frozen("anything") is False
    assert reg.list_active() == []


def test_registry_register_and_is_frozen() -> None:
    reg = FrozenGeneRegistry()
    g = _make_gene(path="C-impl.judge_model")
    reg.register(g)
    assert reg.is_frozen("C-impl.judge_model") is True
    assert reg.is_frozen("C-impl.other") is False
    assert "C-impl.judge_model" in reg


def test_registry_register_rejects_non_gene() -> None:
    reg = FrozenGeneRegistry()
    with pytest.raises(ValueError, match="FrozenGene"):
        reg.register("not-a-gene")  # type: ignore[arg-type]


def test_registry_register_overwrites_same_path() -> None:
    reg = FrozenGeneRegistry()
    g1 = _make_gene(path="C-impl.judge_model", note="v1")
    g2 = _make_gene(path="C-impl.judge_model", note="v2 — extended")
    reg.register(g1)
    reg.register(g2)
    assert len(reg) == 1
    active = reg.list_active()
    assert active[0].note == "v2 — extended"


def test_registry_unregister() -> None:
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="C-impl.judge_model"))
    assert reg.unregister("C-impl.judge_model") is True
    assert reg.unregister("C-impl.judge_model") is False
    assert len(reg) == 0


def test_registry_list_active_excludes_expired() -> None:
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="active", expiry=FUTURE_ISO))
    reg.register(_make_gene(path="expired", expiry=PAST_ISO))
    active = reg.list_active()
    assert len(active) == 1
    assert active[0].gene_path == "active"


def test_registry_list_active_sorted_by_path() -> None:
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="zz"))
    reg.register(_make_gene(path="aa"))
    reg.register(_make_gene(path="mm"))
    paths = [g.gene_path for g in reg.list_active()]
    assert paths == ["aa", "mm", "zz"]


# ===========================================================================
# 7. Registry violates
# ===========================================================================


def test_violates_exact_match() -> None:
    reg = FrozenGeneRegistry()
    g = _make_gene(path="C-impl.judge_model")
    reg.register(g)
    hit = reg.violates("C-impl.judge_model")
    assert hit is g


def test_violates_returns_none_when_no_match() -> None:
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="C-impl.judge_model"))
    assert reg.violates("C-impl.other") is None


def test_violates_prefix_with_bracket() -> None:
    """'C-prompt.persona_set' を凍結すると '[7]' index も違反."""
    reg = FrozenGeneRegistry()
    g = _make_gene(path="C-prompt.persona_set")
    reg.register(g)
    assert reg.violates("C-prompt.persona_set[7]") is g
    assert reg.violates("C-prompt.persona_set[99]") is g


def test_violates_prefix_with_dot() -> None:
    """'C-impl' を凍結すると下位 field も違反."""
    reg = FrozenGeneRegistry()
    g = _make_gene(path="C-impl")
    reg.register(g)
    assert reg.violates("C-impl.judge_model") is g
    assert reg.violates("C-impl.foo") is g


def test_violates_prefix_does_not_match_partial_word() -> None:
    """'persona_set' に対し 'persona_set_v2' は誤マッチしない."""
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="C-prompt.persona_set"))
    # _v2 は次の文字が `_` で `[` / `.` でない → match しない
    assert reg.violates("C-prompt.persona_set_v2") is None


def test_violates_individual_index_does_not_block_others() -> None:
    """個別 index '[7]' を凍結しても他の index は許可."""
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="C-prompt.persona_set[7]"))
    assert reg.violates("C-prompt.persona_set[7]") is not None
    assert reg.violates("C-prompt.persona_set[8]") is None


def test_violates_skips_expired_genes() -> None:
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="C-impl.judge_model", expiry=PAST_ISO))
    # 期限切れは無視
    assert reg.violates("C-impl.judge_model") is None


def test_violates_handles_empty_input() -> None:
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="C-impl.judge_model"))
    assert reg.violates("") is None
    assert reg.violates(None) is None  # type: ignore[arg-type]


# ===========================================================================
# 8. Registry prune_expired
# ===========================================================================


def test_prune_expired_removes_only_expired() -> None:
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="a", expiry=FUTURE_ISO))
    reg.register(_make_gene(path="b", expiry=PAST_ISO))
    reg.register(_make_gene(path="c", expiry=PAST_ISO))
    removed = reg.prune_expired()
    assert removed == 2
    assert len(reg) == 1
    assert "a" in reg
    assert "b" not in reg


def test_prune_expired_zero_when_all_active() -> None:
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="a", expiry=FUTURE_ISO))
    reg.register(_make_gene(path="b", expiry=FUTURE_ISO))
    removed = reg.prune_expired()
    assert removed == 0
    assert len(reg) == 2


def test_prune_expired_now_iso_override() -> None:
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="a", expiry="2030-01-01T00:00:00Z"))
    reg.register(_make_gene(path="b", expiry="2040-01-01T00:00:00Z"))
    # 仮に 2035 → a だけ expired
    removed = reg.prune_expired(now_iso="2035-01-01T00:00:00Z")
    assert removed == 1
    assert "b" in reg
    assert "a" not in reg


# ===========================================================================
# 9. Registry serialization round-trip
# ===========================================================================


def test_registry_serialization_round_trip_empty() -> None:
    reg = FrozenGeneRegistry()
    restored = FrozenGeneRegistry.from_dict(reg.to_dict())
    assert len(restored) == 0


def test_registry_serialization_round_trip_with_genes() -> None:
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="a", reason=FreezeReason.ETHICS))
    reg.register(
        _make_gene(
            path="b",
            reason=FreezeReason.REGULATION,
            note="EU AI Act Art. 5",
        )
    )
    reg.register(_make_gene(path="c", reason=FreezeReason.IP))

    restored = FrozenGeneRegistry.from_dict(reg.to_dict())
    assert len(restored) == 3
    assert restored.is_frozen("a")
    assert restored.is_frozen("b")
    assert restored.is_frozen("c")
    # note も保たれる
    active_b = next(g for g in restored.list_active() if g.gene_path == "b")
    assert active_b.note == "EU AI Act Art. 5"
    assert active_b.reason is FreezeReason.REGULATION


def test_registry_to_dict_keys_sorted() -> None:
    reg = FrozenGeneRegistry()
    reg.register(_make_gene(path="zz"))
    reg.register(_make_gene(path="aa"))
    reg.register(_make_gene(path="mm"))
    d = reg.to_dict()
    paths = [entry["gene_path"] for entry in d["genes"]]
    assert paths == ["aa", "mm", "zz"]


# ===========================================================================
# 10. Re-export from package
# ===========================================================================


def test_package_reexports_frozen_symbols() -> None:
    from llive.perf.evolutionary import (
        MIN_SIGNATURE_BYTES as REEXPORT_MIN_SIG,
    )
    from llive.perf.evolutionary import (
        FreezeReason as REEXPORT_REASON,
    )
    from llive.perf.evolutionary import (
        FrozenGene as REEXPORT_GENE,
    )
    from llive.perf.evolutionary import (
        FrozenGeneRegistry as REEXPORT_REGISTRY,
    )

    assert REEXPORT_MIN_SIG == MIN_SIGNATURE_BYTES
    assert REEXPORT_REASON is FreezeReason
    assert REEXPORT_GENE is FrozenGene
    assert REEXPORT_REGISTRY is FrozenGeneRegistry
