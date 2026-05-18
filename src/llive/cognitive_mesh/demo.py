# SPDX-License-Identifier: Apache-2.0
"""COG-MESH demo CLI — Quiet Hours の現在状態を表示する最小デモ.

requirements_v0.8_cognitive_mesh.md §3 / project_proactive_llive_demo
Phase 0 の **最小** 実装。

実行:

    py -3.11 -m llive.cognitive_mesh.demo

出力例 (active 中):

    Quiet Hours Guard
    =================
    TZ: Asia/Tokyo
    Quiet window: 22:00 - 08:00
    Current time: 2026-05-19 00:15 JST
    Status: Active (can speak)
    Next quiet at: 2026-05-19 22:00 JST

出力例 (quiet 中):

    Status: Quiet Hours (silent)
    Next active at: 2026-05-19 08:00 JST

これは ProactiveLoop の full demo ではなく、Quiet Hours の動作確認用。
full proactive demo は Phase 5 M8.1 で `project_proactive_llive_demo`
Phase 0 として配備予定。
"""

from __future__ import annotations

import os
from datetime import datetime

from llive.cognitive_mesh.quiet_hours import QuietHoursGuard


def _format_now(guard: QuietHoursGuard) -> str:
    cfg = guard._config  # noqa: SLF001 — demo 用、Phase 5 で public API 化
    tz_label = os.environ.get("LLIVE_TZ", "(fail-closed)")
    now = datetime.now(cfg.tz)
    return now.strftime(f"%Y-%m-%d %H:%M {tz_label}")


def main() -> int:
    guard = QuietHoursGuard()
    cfg = guard._config  # noqa: SLF001

    print("Quiet Hours Guard")
    print("=================")
    print(f"TZ: {os.environ.get('LLIVE_TZ', '(not set)')}")
    if cfg.fail_closed:
        print("Config: fail-closed (env 欠落 / TZ 不明 / parse 失敗)")
        print("Status: Quiet Hours (fail-closed silent)")
        return 0
    if not cfg.enabled:
        print("Config: disabled (LLIVE_QUIET_HOURS_ENABLED=0)")
        print("Status: Active (Quiet Hours globally disabled)")
        return 0
    print(f"Quiet window: {cfg.start_hour:02d}:00 - {cfg.end_hour:02d}:00")
    print(f"Current time: {_format_now(guard)}")
    if guard.in_quiet_hours():
        try:
            start, _ = guard.next_active_window()
            print("Status: Quiet Hours (silent)")
            print(f"Next active at: {start.strftime('%Y-%m-%d %H:%M %Z')}")
        except RuntimeError as exc:
            print(f"Status: Quiet Hours ({exc})")
    else:
        print("Status: Active (can speak)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
