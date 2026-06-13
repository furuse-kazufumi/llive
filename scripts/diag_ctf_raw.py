# SPDX-License-Identifier: Apache-2.0
"""診断: CTF バッテリの raw モデル出力を見てオラクル false-negative を検査する.

crux probe で qwen7b/llama が base64(易) すら失敗 → モデルが解けたのに flag 形式
不一致でオラクルが取りこぼした可能性。raw 出力 + オラクル判定 + 期待値を並べて
「能力の問題」か「形式/オラクルの問題」かを切り分ける (compute 最小)。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"D:/projects/llive/src")))

from llive.llm.backend import GenerateRequest, OllamaBackend  # noqa: E402

sys.path.insert(0, str(Path(r"D:/projects/llive/scripts")))
from poc_ctf_coverage import BATTERY, PERSONAS  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

# 検査対象: base64(易, 7b 失敗) + caesar(全失敗) の 2 タスク × 2 モデル。
TASK_IDS = ["base64", "caesar"]
MODELS = ["qwen2.5:7b", "llama3.2:latest"]
tasks = {t.tid: t for t in BATTERY}

backend = OllamaBackend(timeout=300.0)
for m in MODELS:
    print(f"\n========== MODEL {m} ==========")
    for tid in TASK_IDS:
        task = tasks[tid]
        try:
            resp = backend.generate(GenerateRequest(
                prompt=task.prompt, system=PERSONAS["analyst"],
                max_tokens=400, temperature=0.0, model=m))
            text = resp.text or ""
        except Exception as exc:  # noqa: BLE001
            text = f"<ERROR {type(exc).__name__}: {exc}>"
        ok = task.oracle(text)
        print(f"\n--- task={tid} expect={task.answer!r} oracle={'PASS' if ok else 'FAIL'} ---")
        print(text[:700])

print("\n[diag] done")
