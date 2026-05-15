# SPDX-License-Identifier: Apache-2.0
"""RPAR — RPA Roadmap.

Spec §6 Action System + §AB Approval Bus に基づく事務作業自動化基盤。
全 RPA action は ApprovalBus 越しでなければ実行されない (§AB4 silence=denial)。
"""

from llive.rpa.drivers.shell import ShellDriver, ShellResult

__all__ = ["ShellDriver", "ShellResult"]
