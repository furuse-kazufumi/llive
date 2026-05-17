#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cloud LLM comparison — llive (qwen2.5:14b) vs Anthropic Claude Haiku vs Perplexity Sonar.

per feedback_llive_measurement_purity:
- 「llive 単体 (on-prem LLM 経由) vs 他社 cloud API 直接」の 2 系統分離
- llive 経由 = FullSenseLoop で gating / multi-track filter / governance を通った後の出力
- cloud 直接 = API の生 chat completion

両者を同じ Brief で比較し、Brief の expected_terms を
deterministic に grade する。Cloud API key は D:/api-keys.json から読む。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("LLIVE_DISABLE_RAD_GROUNDING", "1")

# Load keys from canonical location
_KEYS = {}
_KEY_FILE = Path("D:/api-keys.json")
if _KEY_FILE.exists():
    _KEYS = json.loads(_KEY_FILE.read_text(encoding="utf-8"))
    for k, v in _KEYS.items():
        if isinstance(v, str) and v and k not in os.environ:
            os.environ[k] = v


from llive.fullsense.loop import FullSenseLoop
from llive.fullsense.types import EpistemicType, Stimulus


# ---- Briefs (same as bench_vs_other_llms.py for consistency) ---------------

BRIEFS = [
    {
        "id": "B1_math",
        "text": (
            "次の数式の等価性を判断してください: (x+1)^2 と x^2 + 2*x + 1。"
            "結論を 1 文で述べてください。"
        ),
        "expected_terms": ["等価", "等しい", "equal", "equivalent", "一致"],
        "typo_terms": ["lllive"],
    },
    {
        "id": "B2_design",
        "text": (
            "保存量と対称性の関係を 3 行以内で説明してください。"
            "物理学的観点で重要な点を 1 つ挙げてください。"
        ),
        "expected_terms": ["保存", "対称", "Noether", "ネーター"],
        "typo_terms": ["lllive"],
    },
    {
        "id": "B3_spec",
        "text": (
            "次のシステムを設計します。要件: p99 レイテンシ < 100ms、"
            "データロス 0 件。3 つの主要設計判断を列挙してください。"
        ),
        "expected_terms": ["レイテンシ", "p99", "データ", "100ms", "100"],
        "typo_terms": ["lllive"],
    },
]


# ---- Backends --------------------------------------------------------------


def _call_llive_alone(prompt: str) -> tuple[str, float]:
    """llive 単独 (FullSenseLoop, LLM 無し / rule-based template) — baseline."""
    loop = FullSenseLoop(sandbox=True, salience_threshold=0.0, llm_backend=None)
    stim = Stimulus(content=prompt, source="manual", surprise=0.7,
                    epistemic_type=EpistemicType.PRAGMATIC)
    t0 = time.perf_counter()
    result = loop.process(stim)
    elapsed = time.perf_counter() - t0
    thought = getattr(result.plan, "thought", None)
    text = str(getattr(thought, "text", "") or "") if thought else ""
    return text, elapsed


def _call_llive_qwen14b(prompt: str) -> tuple[str, float]:
    """llive 経由 (FullSenseLoop + ollama qwen2.5:14b) — for comparison."""
    from llive.llm import OllamaBackend
    llm = OllamaBackend(model="qwen2.5:14b", timeout=600.0)
    loop = FullSenseLoop(sandbox=True, salience_threshold=0.0, llm_backend=llm)
    stim = Stimulus(content=prompt, source="manual", surprise=0.7,
                    epistemic_type=EpistemicType.PRAGMATIC)
    t0 = time.perf_counter()
    result = loop.process(stim)
    elapsed = time.perf_counter() - t0
    thought = getattr(result.plan, "thought", None)
    text = str(getattr(thought, "text", "") or "") if thought else ""
    return text, elapsed


def _call_anthropic_haiku(prompt: str) -> tuple[str, float]:
    """Anthropic Claude Haiku 4.5 direct."""
    import anthropic
    c = anthropic.Anthropic()
    t0 = time.perf_counter()
    r = c.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.perf_counter() - t0
    text = "".join(b.text for b in r.content if hasattr(b, "text"))
    return text, elapsed


def _call_perplexity_sonar(prompt: str) -> tuple[str, float]:
    """Perplexity Sonar direct (HTTP)."""
    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    body = json.dumps({
        "model": "sonar",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
    }).encode()
    req = urllib.request.Request(
        "https://api.perplexity.ai/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    elapsed = time.perf_counter() - t0
    return data["choices"][0]["message"]["content"], elapsed


BACKENDS = [
    # NOTE: llive_alone (rule-based) は coverage 計測対象から除外推奨
    # (feedback_no_echo_baseline.md): Brief 本文の echo back で偽性能が出るため
    # 品質指標としては誤解を招く。latency / リーク計測なら mock OK。
    # 必要なら次行を有効化:
    # {"name": "llive_alone_no_llm", "fn": _call_llive_alone, "kind": "llive 単独 (rule-based, no LLM)"},
    {"name": "llive_qwen2.5:14b", "fn": _call_llive_qwen14b, "kind": "on-prem (via llive loop)"},
    {"name": "anthropic_haiku_4.5", "fn": _call_anthropic_haiku, "kind": "cloud (direct API)"},
    {"name": "perplexity_sonar", "fn": _call_perplexity_sonar, "kind": "cloud (direct API)"},
]


def _grade(text: str, expected: list[str], typos: list[str]) -> dict:
    hit_e = [t for t in expected if t.lower() in (text or "").lower()]
    hit_t = [t for t in typos if t.lower() in (text or "").lower()]
    return {
        "chars": len(text or ""),
        "words": len(re.findall(r"\S+", text or "")),
        "expected_hit": hit_e,
        "coverage": round(len(hit_e) / max(1, len(expected)), 3),
        "has_typo": bool(hit_t),
    }


def _run_one(backend, brief):
    try:
        text, elapsed = backend["fn"](brief["text"])
        return {
            "ok": True,
            "elapsed_s": round(elapsed, 3),
            "text": text,
            "grade": _grade(text, brief["expected_terms"], brief["typo_terms"]),
        }
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read()[:200].decode(errors='replace')}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def main():
    out_dir = Path("docs/benchmarks/2026-05-17-full-validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "vs_cloud.json"

    grid = {}
    for backend in BACKENDS:
        grid[backend["name"]] = {}
        for brief in BRIEFS:
            print(f"[{backend['name']}] {brief['id']} ...", flush=True)
            r = _run_one(backend, brief)
            grid[backend["name"]][brief["id"]] = r
            if r["ok"]:
                print(f"  -> {r['elapsed_s']}s, coverage={r['grade']['coverage']}, "
                      f"chars={r['grade']['chars']}, typo={r['grade']['has_typo']}")
            else:
                print(f"  -> ERROR: {r['error']}")

    summary = {}
    for name, runs in grid.items():
        ok_runs = [r for r in runs.values() if r["ok"]]
        times = [r["elapsed_s"] for r in ok_runs]
        coverages = [r["grade"]["coverage"] for r in ok_runs]
        chars = [r["grade"]["chars"] for r in ok_runs]
        summary[name] = {
            "ok_count": len(ok_runs),
            "mean_elapsed_s": round(sum(times) / len(times), 3) if times else None,
            "mean_coverage": round(sum(coverages) / len(coverages), 3) if coverages else None,
            "mean_chars": int(sum(chars) / len(chars)) if chars else None,
            "any_typo": any(r["grade"]["has_typo"] for r in ok_runs),
        }

    report = {
        "backends": [{"name": b["name"], "kind": b["kind"]} for b in BACKENDS],
        "briefs": [b["id"] for b in BRIEFS],
        "grid": grid,
        "summary": summary,
        "notes": (
            "Per feedback_llive_measurement_purity: llive 経由 (loop attach) vs "
            "cloud 直接 API の 2 系統分離。grade は deterministic post-check のみ "
            "(human judgement なし)。"
        ),
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")
    print("\n--- summary ---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
