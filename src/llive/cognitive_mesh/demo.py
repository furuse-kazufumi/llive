# SPDX-License-Identifier: Apache-2.0
"""COG-MESH 統合 demo CLI.

requirements_v0.8_cognitive_mesh.md §3 / project_proactive_llive_demo
Phase 0 の統合版。Quiet Hours / Proactive Loop / Idle Training /
Tonic Risk / Title Recall の 5 サブシステムが連動して動くことを示す。

実行:

    py -3.11 -m llive.cognitive_mesh.demo

env で挙動を制御:
- LLIVE_TZ / LLIVE_QUIET_HOURS_START / LLIVE_QUIET_HOURS_END /
  LLIVE_QUIET_HOURS_ENABLED — Quiet Hours
- LLIVE_DEMO_FORCE_TIME — "now" を `2026-05-19T10:00:00+09:00` で固定
  (発話 / ingest / risk alert を見る用)

これは普及 PR 用の **動きで魅せる demo**。本格的な ProactiveLoop full
demo は Phase 5 M8.1 で完成予定。
"""

from __future__ import annotations

import os
from datetime import datetime

from llive.approval.bus import ApprovalBus
from llive.cognitive_mesh.brief_runner_bridge import BriefDequeRunnerBridge
from llive.cognitive_mesh.gift_value import GiftValueEstimator
from llive.cognitive_mesh.idle_training import (
    IdleTrainingScheduler,
    InfoSource,
)
from llive.cognitive_mesh.intervention import RiskInterventionAdapter
from llive.cognitive_mesh.mesh_5w1h import Mesh5W1HNode
from llive.cognitive_mesh.mesh_annotator import Mesh5W1HAnnotator
from llive.cognitive_mesh.proactive import (
    ConsistencyViolation,
    ProactiveEvent,
    ProactiveLoop,
)
from llive.cognitive_mesh.quarantined_memory import (
    Ed25519Verifier,
    QuarantinedMemory,
)
from llive.cognitive_mesh.quiet_hours import QuietHoursGuard
from llive.cognitive_mesh.title_recall import TitleRecallPlanner
from llive.cognitive_mesh.tonic_risk import RiskModel, TonicRiskMonitor


def _resolve_now(guard: QuietHoursGuard) -> datetime | None:
    forced = os.environ.get("LLIVE_DEMO_FORCE_TIME")
    if forced:
        try:
            return datetime.fromisoformat(forced)
        except ValueError:
            print(f"[warn] LLIVE_DEMO_FORCE_TIME parse failed: {forced!r}")
    cfg = guard._config
    if cfg.fail_closed:
        return None
    return datetime.now(cfg.tz)


def _section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def main() -> int:
    # Windows cp932 でも動くよう、stdout を UTF-8 に強制
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    guard = QuietHoursGuard()
    cfg = guard._config

    print("=" * 60)
    print("llive Cognitive Mesh - Integrated Demo (COG-MESH-01..10)")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Quiet Hours
    # ------------------------------------------------------------------
    _section("1. Quiet Hours (COG-MESH-07)")
    print(f"  TZ: {os.environ.get('LLIVE_TZ', '(not set)')}")
    if cfg.fail_closed:
        print("  Status: fail-closed (always Quiet)")
    else:
        print(f"  Window: {cfg.start_hour:02d}:00 - {cfg.end_hour:02d}:00")
        print(f"  Enabled: {cfg.enabled}")

    now = _resolve_now(guard)
    if now is None:
        print("  -> Cannot resolve current time, demo halted")
        return 0
    is_quiet = guard.in_quiet_hours(now=now)
    print(f"  Now: {now.isoformat()}")
    print(f"  in_quiet_hours: {is_quiet}")

    # ------------------------------------------------------------------
    # 2. Proactive Loop + Gift Value
    # ------------------------------------------------------------------
    _section("2. Proactive Loop + Gift Value (COG-MESH-05, 06)")
    estimator = GiftValueEstimator()
    loop = ProactiveLoop(
        quiet_hours=guard,
        gift_value=estimator,
        stimulus_source=lambda: "build が完了しました",
    )
    listener_state = {
        "current_topic": "build",
        "risk_score": 0.7,
        "focus_level": 0.3,
        "in_quiet_hours": is_quiet,
    }
    utterance = loop.tick(now=now, listener_state=listener_state)
    if utterance is None:
        print("  Result: silent (Quiet Hours or low Gift Value)")
        suppressed = loop.latest_suppressed(n=1)
        if suppressed:
            s = suppressed[0]
            print(f"  Suppressed: {s.content!r} (gift_value={s.gift_value:.2f})")
    else:
        print(f"  Spoke: {utterance.content!r}")
        print(f"  gift_value: {utterance.gift_value:.2f}")

    # ------------------------------------------------------------------
    # 3. Idle Training Scheduler
    # ------------------------------------------------------------------
    _section("3. Idle Training Scheduler (COG-MESH-04)")
    sched = IdleTrainingScheduler(quiet_hours=guard, idle_threshold_seconds=10)
    sched.register(InfoSource(name="rss-arxiv", fetch=lambda: {"title": "新しい論文"}))
    sched.register(InfoSource(name="gh-trending", fetch=lambda: {"repo": "x/y"}))
    event = sched.tick(now=now)
    if event is None:
        print("  Result: no ingest (Quiet Hours or threshold)")
    else:
        print(f"  Ingested: {event.source_name} -> {event.payload}")

    # ------------------------------------------------------------------
    # 4. Tonic Risk Monitor
    # ------------------------------------------------------------------
    _section("4. Tonic Risk Monitor (COG-MESH-03)")
    # ApprovalBus + RiskInterventionAdapter (M8.5) を配線
    bus = ApprovalBus()
    adapter = RiskInterventionAdapter(bus=bus)
    monitor = TonicRiskMonitor(interrupt_threshold=0.7, on_alert=adapter)
    monitor.register(
        RiskModel(name="high_load", score_fn=lambda s: float(s.get("cpu_load", 0.0)))
    )
    monitor.register(
        RiskModel(name="critical_logs", score_fn=lambda s: float(s.get("error_rate", 0.0)))
    )
    state = {"cpu_load": 0.5, "error_rate": 0.85}
    alert = monitor.tick(state=state, now=now)
    print(f"  State: {state}")
    if alert is None:
        print("  Result: no alert (below threshold or cooldown)")
    else:
        print(f"  ALERT: model={alert.model_name} score={alert.score:.2f}")
        latest_req = adapter.latest_request()
        if latest_req is not None:
            print(
                f"  -> ApprovalBus.intervene emitted: action={latest_req.action!r}, "
                f"principal={latest_req.principal!r}"
            )
            print(f"     pending count = {len(bus.pending())}")

    # ------------------------------------------------------------------
    # 5. Title Recall Planner
    # ------------------------------------------------------------------
    _section("5. Title Recall Planner (COG-MESH-02)")
    planner = TitleRecallPlanner()
    planner.setup("build success", tag="build", weight=1.0)
    planner.setup("test pass", tag="test", weight=1.0)
    planner.setup("deploy live", tag="deploy", weight=2.0)
    final_text = "Today we shipped: build success, test pass, but deploy was missed"
    report = planner.evaluate(final_text, now=now)
    print("  Foreshadows set: build / test / deploy (weights 1/1/2)")
    print(f"  Final text: {final_text!r}")
    print(f"  recall_rate: {report.recall_rate:.2f}")
    print(f"  Unrecovered: {[f.tag for f in report.unrecovered]}")

    # ------------------------------------------------------------------
    # まとめ
    # ------------------------------------------------------------------
    _section("Summary")
    print("  See requirements_v0.8_cognitive_mesh.md for the architecture.")
    print("  Phase 5 で全 sub-system を tick loop で常時駆動予定。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
