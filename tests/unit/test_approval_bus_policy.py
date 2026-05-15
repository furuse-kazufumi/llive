"""ApprovalBus × Policy 結合の単体テスト (in-memory)."""

from __future__ import annotations

from llive.approval import (
    AllowList,
    ApprovalBus,
    DenyList,
    Verdict,
    deny_overrides,
)


def test_policy_auto_approves_request() -> None:
    bus = ApprovalBus(policy=AllowList.of({"shell:ls"}))
    req = bus.request("shell:ls", {})
    # 人手 approve なしで Verdict が確定
    assert bus.current_verdict(req.request_id) is Verdict.APPROVED
    # pending には残らない
    assert bus.pending() == []
    # ledger に policy:auto で記録されている
    led = bus.ledger()
    assert len(led) == 1
    assert led[0].by == "policy:auto"


def test_policy_auto_denies_request() -> None:
    bus = ApprovalBus(policy=DenyList.of({"shell:rm -rf /"}))
    req = bus.request("shell:rm -rf /", {})
    assert bus.current_verdict(req.request_id) is Verdict.DENIED
    assert bus.pending() == []


def test_policy_undecided_keeps_pending() -> None:
    bus = ApprovalBus(policy=AllowList.of({"shell:ls"}))
    req = bus.request("shell:cat", {})  # allowlist に無い
    # 未判定なので silence == denial (§AB4)
    assert bus.current_verdict(req.request_id) is Verdict.DENIED
    # 人手 review に流れる: pending に残る
    pending_ids = [r.request_id for r in bus.pending()]
    assert req.request_id in pending_ids
    # 人手で approve できる
    bus.approve(req.request_id, by="human")
    assert bus.current_verdict(req.request_id) is Verdict.APPROVED


def test_deny_overrides_helper_via_bus() -> None:
    policy = deny_overrides(allow=["shell:ls", "shell:cat"], deny=["shell:cat"])
    bus = ApprovalBus(policy=policy)
    r_ls = bus.request("shell:ls", {})
    r_cat = bus.request("shell:cat", {})
    assert bus.current_verdict(r_ls.request_id) is Verdict.APPROVED
    # cat は両方マッチするが deny 勝ち
    assert bus.current_verdict(r_cat.request_id) is Verdict.DENIED


def test_existing_api_backward_compatible() -> None:
    """policy/ledger 未指定なら既存挙動と完全一致 (回帰防止)."""
    bus = ApprovalBus()
    req = bus.request("shell:ls", {})
    assert bus.current_verdict(req.request_id) is Verdict.DENIED  # silence
    bus.approve(req.request_id, by="human")
    assert bus.current_verdict(req.request_id) is Verdict.APPROVED
