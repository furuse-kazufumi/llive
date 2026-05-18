#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""llive v0.8 Cognitive Mesh - 自律 tick 動作確認 demo.

requirements_v0.8 M8.1 (ProactiveLoop) + M8.5 (TonicRiskMonitor) の
本実装動作を **start()/stop() で実機 N 秒走らせ**、発話 / 抑制 / alert
履歴を出力する。

実行:

    $env:LLIVE_TZ = "Asia/Tokyo"
    $env:LLIVE_QUIET_HOURS_ENABLED = "0"   # Quiet Hours 無効化 (常に Active)
    py -3.11 scripts/demo_autonomous_tick.py

env で挙動を変える:
- LLIVE_QUIET_HOURS_ENABLED=1 + LLIVE_QUIET_HOURS_START/END で Quiet Hours
  に入った場合の自律抑止動作を確認可能
- DURATION_SEC (default 2.0)
- TICK_INTERVAL (default 0.2)
"""

from __future__ import annotations

import os
import sys
import time
from datetime import timedelta

# Windows cp932 対策
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

from llive.cognitive_mesh.proactive import ProactiveLoop
from llive.cognitive_mesh.quiet_hours import QuietHoursGuard
from llive.cognitive_mesh.tonic_risk import RiskAlert, RiskModel, TonicRiskMonitor


def main() -> int:
    duration = float(os.environ.get("DURATION_SEC", "2.0"))
    tick_interval = float(os.environ.get("TICK_INTERVAL", "0.2"))

    print("=" * 60)
    print("llive Cognitive Mesh - 自律 tick 実機検証")
    print("=" * 60)
    print(f"Duration       : {duration}s")
    print(f"Tick interval  : {tick_interval}s")
    print(f"LLIVE_TZ       : {os.environ.get('LLIVE_TZ', '(not set)')}")
    print(f"Quiet hours    : {os.environ.get('LLIVE_QUIET_HOURS_ENABLED', '?')}")
    print()

    # ------------------------------------------------------------------
    # ProactiveLoop (timer mode + 動的 stimulus)
    # ------------------------------------------------------------------
    print("[1] ProactiveLoop start...")
    guard = QuietHoursGuard()
    proactive_count = {"n": 0}

    def make_stimulus() -> str:
        proactive_count["n"] += 1
        return f"進捗 #{proactive_count['n']}: build 状況を共有します"

    loop = ProactiveLoop(
        quiet_hours=guard,
        tick_interval_seconds=tick_interval,
        stimulus_source=make_stimulus,
    )
    loop.start()

    # ------------------------------------------------------------------
    # TonicRiskMonitor (state source は乱数 0..1)
    # ------------------------------------------------------------------
    print("[2] TonicRiskMonitor start...")
    import random
    received_alerts: list[RiskAlert] = []
    risk_state = {"score": 0.3}

    def state_source() -> dict:
        # 50ms 毎に更新される擬似 state
        risk_state["score"] = random.uniform(0.0, 1.0)
        return dict(risk_state)

    monitor = TonicRiskMonitor(
        interrupt_threshold=0.7,
        cooldown=timedelta(seconds=0),
        state_source=state_source,
        tick_interval_seconds=tick_interval / 2,  # proactive より速く
        on_alert=lambda a: received_alerts.append(a),
    )
    monitor.register(
        RiskModel(name="random_kyt", score_fn=lambda s: float(s.get("score", 0.0)))
    )
    monitor.start()

    print(f"[3] Running for {duration}s...")
    time.sleep(duration)

    print()
    print("[4] Stopping...")
    loop.stop()
    monitor.stop()

    # ------------------------------------------------------------------
    # 結果
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("結果")
    print("=" * 60)

    utts = loop.latest_utterances(n=100)
    supp = loop.latest_suppressed(n=100)
    print(f"ProactiveLoop stimulus 呼び出し: {proactive_count['n']}")
    print(f"  - 発話   : {len(utts)} 件")
    print(f"  - 抑制   : {len(supp)} 件")
    if utts:
        print(f"  - 最後の発話: {utts[-1].content!r} (gift={utts[-1].gift_value:.2f})")
    if supp:
        print(f"  - 最後の抑制: {supp[-1].content!r} (reason={supp[-1].reason})")

    print()
    print(f"TonicRiskMonitor alerts: {len(received_alerts)} 件")
    if received_alerts:
        print(f"  - 最後の alert: score={received_alerts[-1].score:.2f} "
              f"state={received_alerts[-1].state_snapshot}")
    print()

    if len(utts) + len(supp) == 0:
        print("[WARN] ProactiveLoop は 1 回も tick していません")
        return 1
    print("[OK] 自律 tick が動作 — start()/stop() の本実装は正しく機能")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
