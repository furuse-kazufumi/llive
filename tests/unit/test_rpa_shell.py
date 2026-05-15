# SPDX-License-Identifier: Apache-2.0
"""RPAR ShellDriver の単体テスト."""

from __future__ import annotations

import sys

from llive.approval.bus import ApprovalBus
from llive.rpa.drivers.shell import ShellDriver


def test_silence_denies_command() -> None:
    """§AB4: bus に何も response しなければ実行されない."""
    bus = ApprovalBus()
    driver = ShellDriver(bus)
    result = driver.run([sys.executable, "-c", "print('hi')"])
    assert result.approved is False
    assert "approval verdict" in result.skipped_reason


def test_approved_command_executes() -> None:
    bus = ApprovalBus()
    driver = ShellDriver(bus)
    # bus の auto-approve hook を模擬: request 時点で immediately approve
    # 実 RPA では別 thread / 別 process で approve が来る。
    # ここでは monkeypatch 風に request を override する。
    orig_request = bus.request

    def auto_approve_request(*a, **kw):
        req = orig_request(*a, **kw)
        bus.approve(req.request_id, by="test-auto")
        return req

    bus.request = auto_approve_request  # type: ignore[assignment]

    result = driver.run([sys.executable, "-c", "print('hi')"])
    assert result.approved is True
    assert result.returncode == 0
    assert "hi" in result.stdout


def test_forbidden_command_is_rejected_unconditionally() -> None:
    """§I4 forbidden zone — Approval があっても通さない."""
    bus = ApprovalBus()
    # forbidden token がコマンド文字列に出る形にする
    driver = ShellDriver(bus)
    result = driver.run("rm -rf /")
    assert result.approved is False
    assert "forbidden" in result.skipped_reason


def test_string_command_split_via_shlex() -> None:
    """文字列入力は shlex で分割される. Windows path のバックスラッシュ問題を
    避けるため、ここでは plain な文字列のみで検証する."""
    bus = ApprovalBus()
    driver = ShellDriver(bus)
    # 未 approve なので skip されるが、cmd の parsing は確認できる
    result = driver.run('echo hello world')
    assert result.cmd == ["echo", "hello", "world"]


def test_denied_command_does_not_execute() -> None:
    bus = ApprovalBus()
    driver = ShellDriver(bus)
    orig_request = bus.request

    def auto_deny_request(*a, **kw):
        req = orig_request(*a, **kw)
        bus.deny(req.request_id, by="policy")
        return req

    bus.request = auto_deny_request  # type: ignore[assignment]
    result = driver.run([sys.executable, "-c", "print('should not run')"])
    assert result.approved is False
    assert "denied" in result.skipped_reason
