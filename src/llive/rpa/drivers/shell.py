"""ShellDriver — subprocess wrapper. ApprovalBus 越しでなければ実行しない.

Spec §I4: forbidden / requires-approval / permitted の 3 区分.
本 MVP では「明示禁止リスト」+「ApprovalBus approve」必須で安全側に倒す。
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass

from llive.approval.bus import ApprovalBus, Verdict


_FORBIDDEN_TOKENS: frozenset[str] = frozenset(
    {
        "rm -rf /",
        "rm -rf /*",
        "format c:",
        "format d:",
        "shutdown -h now",
        "shutdown /s",
        "mkfs",
        "dd if=",
        ":(){:|:&};:",  # fork bomb
        "del /f /s /q c:\\",
        "rm -rf ~",
    }
)


@dataclass
class ShellResult:
    """subprocess の結果."""

    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str
    approved: bool
    skipped_reason: str = ""


class ShellDriver:
    """Approval 越しで shell command を実行する driver.

    禁止トークンを含むコマンドは Approval 関係なく無条件 reject (§I4 forbidden).
    """

    def __init__(self, bus: ApprovalBus, *, principal: str = "rpa-shell") -> None:
        self.bus = bus
        self.principal = principal

    def _is_forbidden(self, cmd_str: str) -> bool:
        low = cmd_str.lower()
        return any(tok in low for tok in _FORBIDDEN_TOKENS)

    def run(
        self,
        cmd: list[str] | str,
        *,
        cwd: str | None = None,
        timeout_s: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> ShellResult:
        cmd_list: list[str] = list(cmd) if isinstance(cmd, list) else shlex.split(cmd)
        cmd_str = " ".join(cmd_list)

        # §I4 forbidden zone: 無条件 reject
        if self._is_forbidden(cmd_str):
            return ShellResult(
                cmd=cmd_list,
                returncode=-1,
                stdout="",
                stderr="",
                approved=False,
                skipped_reason=f"forbidden token in command: {cmd_str!r}",
            )

        # Approval Bus request
        req = self.bus.request(
            action=f"shell:{cmd_list[0]}",
            payload={"cmd": cmd_list, "cwd": cwd},
            principal=self.principal,
            timeout_s=timeout_s,
        )
        verdict = self.bus.current_verdict(req.request_id)
        if verdict is not Verdict.APPROVED:
            return ShellResult(
                cmd=cmd_list,
                returncode=-1,
                stdout="",
                stderr="",
                approved=False,
                skipped_reason=f"approval verdict = {verdict.value}",
            )

        # safe env: 環境変数を sanitize (シェル評価される変数は剥がす)
        safe_env = dict(os.environ if env is None else env)
        for v in ("TERMINAL", "EDITOR", "VISUAL", "BROWSER", "PAGER"):
            safe_env.pop(v, None)

        try:
            out = subprocess.run(
                cmd_list,
                cwd=cwd,
                env=safe_env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            return ShellResult(
                cmd=cmd_list,
                returncode=out.returncode,
                stdout=out.stdout,
                stderr=out.stderr,
                approved=True,
            )
        except subprocess.TimeoutExpired as e:
            return ShellResult(
                cmd=cmd_list,
                returncode=-1,
                stdout=e.stdout or "",
                stderr=f"timeout after {timeout_s}s",
                approved=True,
                skipped_reason="timeout",
            )


__all__ = ["ShellDriver", "ShellResult"]
