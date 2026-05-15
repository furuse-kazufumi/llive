# SPDX-License-Identifier: Apache-2.0
"""ApprovalPolicy (AllowList / DenyList / Composite) の単体テスト."""

from __future__ import annotations

from llive.approval import (
    AllowList,
    ApprovalRequest,
    CompositePolicy,
    DenyList,
    Verdict,
    deny_overrides,
)


def _req(action: str) -> ApprovalRequest:
    return ApprovalRequest(request_id="r", action=action, payload={})


def test_allowlist_exact_match_approves() -> None:
    pol = AllowList.of({"shell:ls", "shell:cat"})
    assert pol.evaluate(_req("shell:ls")) is Verdict.APPROVED
    assert pol.evaluate(_req("shell:cat")) is Verdict.APPROVED
    # 一致しないものは None (未判定)
    assert pol.evaluate(_req("shell:rm")) is None


def test_allowlist_prefix_approves() -> None:
    pol = AllowList.of({}, prefixes=("read:",))
    assert pol.evaluate(_req("read:file")) is Verdict.APPROVED
    assert pol.evaluate(_req("read:dir")) is Verdict.APPROVED
    assert pol.evaluate(_req("write:file")) is None


def test_denylist_exact_match_denies() -> None:
    pol = DenyList.of({"shell:rm -rf /", "shell:dd"})
    assert pol.evaluate(_req("shell:rm -rf /")) is Verdict.DENIED
    assert pol.evaluate(_req("shell:ls")) is None


def test_denylist_prefix_denies() -> None:
    pol = DenyList.of({}, prefixes=("net:",))
    assert pol.evaluate(_req("net:exfiltrate")) is Verdict.DENIED
    assert pol.evaluate(_req("read:net:safe")) is None


def test_composite_first_match_wins() -> None:
    # deny を先に置く: deny-overrides
    composite = CompositePolicy.of(
        DenyList.of({"shell:rm"}),
        AllowList.of({"shell:rm", "shell:ls"}),
    )
    # 両方マッチするが先頭の DenyList が勝つ
    assert composite.evaluate(_req("shell:rm")) is Verdict.DENIED
    # AllowList だけマッチ
    assert composite.evaluate(_req("shell:ls")) is Verdict.APPROVED
    # どちらにもマッチしない
    assert composite.evaluate(_req("shell:cat")) is None


def test_deny_overrides_helper() -> None:
    pol = deny_overrides(allow=["shell:ls"], deny=["shell:ls"])  # 同一でも deny 勝ち
    assert pol.evaluate(_req("shell:ls")) is Verdict.DENIED


def test_empty_composite_returns_none() -> None:
    pol = CompositePolicy.of()
    assert pol.evaluate(_req("anything")) is None
