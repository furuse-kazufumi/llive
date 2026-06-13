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
        # Quiet Hours が fail-closed の時点で demo を halt させると、デモの
        # 90% を占める残 9 sections が実演されない. security stance は維持
        # しつつ、env 設定方法を案内した上で mock time で続行する.
        print("  -> Quiet Hours fail-closed (LLIVE_TZ not set is the secure default).")
        print("     Hint: export LLIVE_TZ=Asia/Tokyo to demo Quiet-Hours time evaluation.")
        print("     Falling back to mock time 2026-05-23T12:00:00+09:00 for demo continuity.")
        now = datetime.fromisoformat("2026-05-23T12:00:00+09:00")
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
    # 6. Mesh5W1H Annotator (M8.6)
    # ------------------------------------------------------------------
    _section("6. Mesh5W1H Annotator (COG-MESH-10 完成配線)")
    annotator = Mesh5W1HAnnotator()
    sample_text = "Why did Alice deploy today? Because the build was ready."
    annotator.emit_from_text(sample_text)
    annotator.emit_node(Mesh5W1HNode.WHEN, "iso", now.isoformat())
    bundle = annotator.freeze()
    print(f"  Text: {sample_text!r}")
    print(f"  Annotations: {len(bundle.items)} 件")
    for a in bundle.items:
        print(f"    - {a.namespace}: {a.key}={a.value}")

    # ------------------------------------------------------------------
    # 7. Quarantined Memory + Ed25519 (M8.2)
    # ------------------------------------------------------------------
    _section("7. Quarantined Memory + Ed25519 (COG-MESH-04 SEC-01/02)")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, PublicFormat,
    )
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        encoding=Encoding.Raw, format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw,
    )
    verifier = Ed25519Verifier()
    verifier.register("trusted-rss", pub_raw)
    qmem = QuarantinedMemory(verifier=verifier)
    sched_q = IdleTrainingScheduler(
        quiet_hours=guard, idle_threshold_seconds=10, quarantine=qmem
    )

    def _signed_fetch() -> object:
        return IdleTrainingScheduler.sign_payload(
            {"title": "trusted news"}, "trusted-rss", priv_raw
        )

    sched_q.register(InfoSource(name="rss-trusted", fetch=_signed_fetch))
    sched_q.register(InfoSource(name="rss-unsigned", fetch=lambda: {"title": "unsigned"}))
    sched_q.tick(now=now)
    # 連続 tick は cooldown で 1 件のみ通る — 別 tick 用に時刻を進める
    from datetime import timedelta as _td
    sched_q.tick(now=(now + _td(seconds=60)) if now else None)
    print(f"  Quarantine: active={len(qmem.active_items())}, "
          f"pending={len(qmem.pending())}")
    for entry in qmem.iter_all():
        signed = "signed" if entry.signer_id else "unsigned"
        verified = "verified" if entry.verified else "unverified"
        status = "active" if entry.promoted_at else ("pending" if entry.rejected_at is None else "rejected")
        print(f"    - {entry.event_id} [{signed}/{verified}/{status}] "
              f"signer={entry.signer_id} payload={entry.payload}")

    # ------------------------------------------------------------------
    # 8. Proactive event / consistency mode (M8.7)
    # ------------------------------------------------------------------
    _section("8. Proactive Event / Consistency Modes (COG-MESH-06 拡張)")
    loop_ext = ProactiveLoop(
        quiet_hours=guard,
        mode="event",
    )
    event_obj = ProactiveEvent(
        topic="build", note="ビルド成功 (signed by CI)", severity=0.9,
    )
    out_ev = loop_ext.tick_event(
        event=event_obj, now=now, listener_state=listener_state
    )
    if out_ev is None:
        print("  event tick: silent (quiet hours or low value)")
    else:
        print(f"  event tick fired: {out_ev.content!r}")

    loop_cons = ProactiveLoop(quiet_hours=guard, mode="consistency")
    violation = ConsistencyViolation(
        layer_a="semantic", layer_b="episodic",
        conflict_type="fact_mismatch",
        evidence="semantic says 'on-prem only' but episodic logs cloud call",
        severity=0.8,
    )
    listener_cons = dict(listener_state, current_topic="semantic")
    out_cons = loop_cons.tick_consistency(
        violation=violation, now=now, listener_state=listener_cons
    )
    if out_cons is None:
        print("  consistency tick: silent")
    else:
        print(f"  consistency tick fired: {out_cons.content!r}")

    # ------------------------------------------------------------------
    # 9. BriefDeque ↔ BriefRunner Bridge (M8.3) — fake runner で動作確認
    # ------------------------------------------------------------------
    _section("9. BriefDeque ↔ BriefRunner Bridge (COG-MESH-08 完成配線)")
    try:
        from llive.brief.types import Brief, BriefResult, BriefStatus

        class _DemoRunner:
            """submit を観測する fake runner."""
            def submit(self, brief):
                return BriefResult(
                    brief_id=brief.brief_id, status=BriefStatus.COMPLETED,
                    rationale=f"demo processed: {brief.goal}",
                )

        bridge = BriefDequeRunnerBridge(runner=_DemoRunner())
        bridge.enqueue(Brief(brief_id="demo-001", goal="run nightly bench"))
        bridge.enqueue(Brief(brief_id="demo-002", goal="rotate keys"))
        bridge.enqueue_front(Brief(brief_id="demo-urgent", goal="halt build"))
        results = bridge.submit_all()
        print(f"  Processed {len(results)} brief(s):")
        for r in results:
            print(f"    - {r.brief_id}: {r.status.value} ({r.rationale})")
    except Exception as exc:  # noqa: BLE001 — demo は壊れない方が良い
        print(f"  Bridge demo skipped: {exc}")

    # ------------------------------------------------------------------
    # 10. Timeline emit bridge (M8.1 skeleton) — llive ↔ llmesh ↔ llove 契約
    # ------------------------------------------------------------------
    _section("10. Timeline Emit Bridge (M8.1 skeleton: llive → llmesh → llove)")
    from llive.cognitive_mesh.timeline_emitter import (
        CognitiveMeshTimelineEmitter,
        InMemoryTimelineSink,
    )
    sink = InMemoryTimelineSink()
    emitter = CognitiveMeshTimelineEmitter(sink=sink, task_id="demo", node_id="local")
    # 各サブシステムの emit を Timeline event dict に変換
    if utterance is not None:
        emitter.emit_proactive(utterance)
    if alert is not None:
        emitter.emit_risk(alert)
    for entry in qmem.iter_all():
        emitter.emit_quarantine(entry)
    print(f"  Emitted: {len(emitter.buffer)} event(s) to InMemoryTimelineSink")
    print(f"  Sink received: {len(sink.received)} event(s) (schema = llove CogEntry 互換)")
    for ev in emitter.buffer:
        md = ev["metadata"]
        # 各 event の最小サマリ (llove CogEntry.from_event() が読む key を覗き見)
        et = ev["event_type"]
        if et == "cog_proactive_utterance":
            tail = f"mode={md['mode']!r} gv={md['gift_value']:.2f}"
        elif et == "cog_risk_alert":
            tail = f"model={md['model_name']!r} score={md['score']:.2f}"
        else:
            tail = f"signer={md.get('signer_id')!r} verified={md['verified']}"
        print(f"    - {et}  {tail}")
    print("  実 HTTP/MCP push 配線は Phase 6 (llive/clients/llmesh_timeline.py)")

    # ------------------------------------------------------------------
    # まとめ
    # ------------------------------------------------------------------
    _section("Summary")
    print("  See requirements_v0.8_cognitive_mesh.md for the architecture.")
    print("  M8.2/3/4/5/6/7/8/9 本実装完了 + M8.1 skeleton 配備済 (2026-05-19).")
    print("  asciinema 録画推奨: Active (10:00) / Quiet (02:00) 切替で動きを確認.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
