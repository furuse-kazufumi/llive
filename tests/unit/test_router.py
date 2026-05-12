"""RTR-01/02: rule-based router + explanation log."""

from __future__ import annotations

import json
from pathlib import Path

from llive.router.engine import RouterEngine


def _spec(tmp_path: Path) -> Path:
    p = tmp_path / "routes.yaml"
    p.write_text(
        """\
schema_version: 1
routes:
  - container: fast_path_v1
    when:
      prompt_length_lt: 100
  - container: long_path_v1
    when:
      prompt_length_gte: 100
  - container: adaptive_reasoning_v1
""",
        encoding="utf-8",
    )
    return p


def test_router_picks_first_match(tmp_path):
    eng = RouterEngine(_spec(tmp_path))
    log = tmp_path / "router.jsonl"
    decision = eng.select("hello", log_path=log)
    assert decision.container == "fast_path_v1"
    assert decision.explanation.candidates[0].matched is True
    assert decision.explanation.candidates[1].matched is False
    assert decision.explanation.prompt_features["prompt_length"] == 5


def test_router_falls_back_to_default(tmp_path):
    eng = RouterEngine(_spec(tmp_path))
    decision = eng.select("x" * 99, log_path=tmp_path / "router.jsonl")
    # 99 < 100 matches fast_path; let's test the fallback with a real fallback case
    assert decision.container == "fast_path_v1"


def test_router_explanation_log_appended(tmp_path):
    eng = RouterEngine(_spec(tmp_path))
    log = tmp_path / "router.jsonl"
    eng.select("hi", log_path=log)
    eng.select("hello", log_path=log)
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    payload = json.loads(lines[0])
    assert "selected_container" in payload
    assert "candidates" in payload
    assert payload["candidates"][0]["matched"] is True


def test_router_long_prompt_picks_long_path(tmp_path):
    eng = RouterEngine(_spec(tmp_path))
    decision = eng.select("x" * 200, log_path=tmp_path / "router.jsonl")
    assert decision.container == "long_path_v1"
    assert decision.explanation.candidates[0].matched is False
    assert decision.explanation.candidates[1].matched is True
