"""Phase D (demo) — smoke tests for each demo scenario.

Each scenario must:

1. Be listed by ``list_scenarios()``.
2. Run end-to-end without raising for both ``ja`` and ``en`` narration.
3. Return a JSON-serialisable summary dict.

We intentionally let stdout flow so a test failure shows the scenario
trace, but capture it via capsys to keep CI output reasonable.
"""

from __future__ import annotations

import json

import pytest

from llive.demo import list_scenarios, run_all, run_one
from llive.demo.i18n import current_lang
from llive.demo.runner import _scoped_lang
from llive.llm.backend import reset_default_backend
from llive.mcp.tools import reset_default_index


@pytest.fixture(autouse=True)
def _force_mock_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLIVE_LLM_BACKEND", "mock")
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OLLAMA_HOST", "LLIVE_RAD_DIR"):
        monkeypatch.delenv(var, raising=False)
    reset_default_backend()
    reset_default_index()


def test_list_scenarios_has_nine() -> None:
    scenarios = list_scenarios()
    assert len(scenarios) == 9
    ids = [s.id for s in scenarios]
    assert ids == [
        "rad-quick-tour",
        "append-roundtrip",
        "code-review",
        "mcp-roundtrip",
        "openai-http",
        "vlm-describe",
        "consolidation-mirror",
        "resident-cognition",
        "multi-track",
    ]


def test_scoped_lang_restores_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLIVE_DEMO_LANG", raising=False)
    assert current_lang() == "ja"
    with _scoped_lang("en"):
        assert current_lang() == "en"
    assert current_lang() == "ja"


def test_scoped_lang_inside_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLIVE_DEMO_LANG", "en")
    with _scoped_lang("ja"):
        assert current_lang() == "ja"
    assert current_lang() == "en"


@pytest.mark.parametrize("idx", [1, 2, 3])
def test_run_one_offline_scenarios(idx: int, capsys: pytest.CaptureFixture[str]) -> None:
    out = run_one(idx, quiet=True)
    assert out["ok"] is True
    # Every scenario must produce a JSON-serialisable summary
    json.dumps(out)


def test_run_scenario_1_outputs_hits_in_ja(capsys: pytest.CaptureFixture[str]) -> None:
    out = run_one(1, lang="ja", quiet=False)
    captured = capsys.readouterr()
    assert "RAD 読み API のクイックツアー" in captured.out
    assert "buffer_overflow.md" in captured.out
    summary = out["summary"]
    assert isinstance(summary, dict)
    assert summary.get("queries") == 3


def test_run_scenario_1_outputs_hits_in_en(capsys: pytest.CaptureFixture[str]) -> None:
    out = run_one(1, lang="en", quiet=False)
    captured = capsys.readouterr()
    assert "RAD read-API quick tour" in captured.out
    assert "buffer_overflow.md" in captured.out
    assert out["ok"] is True


def test_run_scenario_1_outputs_in_zh(capsys: pytest.CaptureFixture[str]) -> None:
    out = run_one(1, lang="zh", quiet=False)
    captured = capsys.readouterr()
    assert "RAD 读取 API 速览" in captured.out
    assert "迷你语料" in captured.out
    assert out["ok"] is True


def test_run_scenario_1_outputs_in_ko(capsys: pytest.CaptureFixture[str]) -> None:
    out = run_one(1, lang="ko", quiet=False)
    captured = capsys.readouterr()
    assert "빠른 둘러보기" in captured.out
    assert "코퍼스" in captured.out
    assert out["ok"] is True


def test_current_lang_handles_locale_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    from llive.demo.i18n import current_lang

    monkeypatch.setenv("LLIVE_DEMO_LANG", "zh-CN")
    assert current_lang() == "zh"
    monkeypatch.setenv("LLIVE_DEMO_LANG", "ko_KR")
    assert current_lang() == "ko"
    monkeypatch.setenv("LLIVE_DEMO_LANG", "fr")
    # Unsupported language falls back to ja
    assert current_lang() == "ja"


def test_run_scenario_3_injects_rad_hints(capsys: pytest.CaptureFixture[str]) -> None:
    out = run_one(3, quiet=False)
    captured = capsys.readouterr()
    assert "RAD hints" in captured.out or "RAD ヒント" in captured.out
    assert "strcpy" in captured.out
    summary = out["summary"]
    assert isinstance(summary, dict)
    assert summary.get("hint_count", 0) >= 1
    assert summary.get("domain") == "security_corpus_v2"


def test_run_scenario_5_distinguishes_rag_on_off(capsys: pytest.CaptureFixture[str]) -> None:
    out = run_one(5, quiet=False)
    captured = capsys.readouterr()
    assert "RAD" in captured.out
    summary = out["summary"]
    assert isinstance(summary, dict)
    assert summary.get("hints_off", -1) == 0
    assert summary.get("hints_on", -1) >= 1


def test_run_scenario_6_vlm_with_synthetic_png(capsys: pytest.CaptureFixture[str]) -> None:
    out = run_one(6, quiet=False)
    captured = capsys.readouterr()
    assert "vlm-mock" in captured.out
    assert "saw 1 image" in captured.out
    summary = out["summary"]
    assert isinstance(summary, dict)
    assert summary.get("hints_off") == 0
    assert summary.get("hints_on", 0) >= 1


def test_run_scenario_7_consolidation_creates_learned_files(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = run_one(7, quiet=False)
    captured = capsys.readouterr()
    assert "derived_from" in captured.out
    assert "heap-spray" in captured.out
    summary = out["summary"]
    assert isinstance(summary, dict)
    assert summary.get("pages_created", 0) >= 1
    assert summary.get("learned_files", 0) >= 1


def test_run_one_by_id() -> None:
    out = run_one("rad-quick-tour", quiet=True)
    assert out["ok"] is True
    assert out["id"] == "rad-quick-tour"


# ---------------------------------------------------------------------------
# Scenario 8: resident-cognition (A-5)
# ---------------------------------------------------------------------------


def test_scenario_8_resident_cognition_runs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A-5: ResidentRunner デモが 2 秒で完了し、summary を返す."""
    monkeypatch.setenv("LLIVE_RESIDENT_DURATION", "2")
    monkeypatch.setenv("LLIVE_DEMO_SEED", "42")
    monkeypatch.setenv("LLIVE_DEMO_NO_COLOR", "1")
    out = run_one("resident-cognition", quiet=False)
    captured = capsys.readouterr()
    assert out["ok"] is True
    assert "ResidentRunner" in captured.out or "常駐" in captured.out
    summary = out["summary"]
    assert isinstance(summary, dict)
    assert summary["duration_s"] == 2.0
    counts = summary["cycle_counts"]
    assert isinstance(counts, dict)
    # 2 秒で fast tier は必ず複数 cycle 回るはず
    assert counts["fast"] >= 2
    assert isinstance(summary["phases_seen"], list)


def test_scenario_8_phase_transitions_in_2s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """phase_schedule で 2 秒間に AWAKE/REST/DREAM 全部に触れる."""
    monkeypatch.setenv("LLIVE_RESIDENT_DURATION", "2")
    monkeypatch.setenv("LLIVE_DEMO_SEED", "42")
    monkeypatch.setenv("LLIVE_DEMO_NO_COLOR", "1")
    out = run_one("resident-cognition", quiet=True)
    summary = out["summary"]
    assert set(summary["phases_seen"]) == {"awake", "rest", "dream"}


@pytest.mark.parametrize("lang", ["ja", "en", "zh", "ko"])
def test_scenario_8_multilingual(
    lang: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("LLIVE_RESIDENT_DURATION", "2")
    monkeypatch.setenv("LLIVE_DEMO_SEED", "42")
    monkeypatch.setenv("LLIVE_DEMO_NO_COLOR", "1")
    out = run_one("resident-cognition", lang=lang, quiet=False)
    captured = capsys.readouterr()
    assert out["ok"] is True
    # 各言語の intro 特徴文字列を検査
    needle = {
        "ja": "湧き上がる",
        "en": "spontaneous",
        "zh": "涌现",
        "ko": "솟아오르",
    }[lang]
    assert needle in captured.out, f"expected {needle!r} in {lang} narration"


def test_scenario_8_json_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON シリアライズ可能であること (AI agent 渡し用)."""
    monkeypatch.setenv("LLIVE_RESIDENT_DURATION", "2")
    monkeypatch.setenv("LLIVE_DEMO_SEED", "42")
    monkeypatch.setenv("LLIVE_DEMO_NO_COLOR", "1")
    out = run_one("resident-cognition", quiet=True)
    payload = json.dumps(out, default=str)
    assert "resident-cognition" in payload
    assert "cycle_counts" in payload


# ---------------------------------------------------------------------------
# Scenario 9: multi-track (A-1.5 体験)
# ---------------------------------------------------------------------------


def test_scenario_9_multi_track_runs_all_five_tracks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = run_one("multi-track", quiet=False)
    captured = capsys.readouterr()
    assert out["ok"] is True
    summary = out["summary"]
    assert isinstance(summary, dict)
    assert summary["tracks_passed"] == 5
    per_track = summary["per_track"]
    assert set(per_track.keys()) == {
        "factual",
        "empirical",
        "normative",
        "interpretive",
        "pragmatic",
    }
    # rationale に各 track tag が現れること
    assert "[track:factual]" in captured.out
    assert "[track:pragmatic]" in captured.out
    assert "framed_for=" in captured.out  # PRAGMATIC の audit


@pytest.mark.parametrize("lang", ["ja", "en", "zh", "ko"])
def test_scenario_9_multilingual(
    lang: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = run_one("multi-track", lang=lang, quiet=False)
    captured = capsys.readouterr()
    assert out["ok"] is True
    needle = {
        "ja": "結論不変",
        "en": "invariant",
        "zh": "结论不变",
        "ko": "불변",
    }[lang]
    assert needle in captured.out, f"expected {needle!r} in {lang} narration"


def test_run_one_unknown_raises() -> None:
    with pytest.raises(SystemExit):
        run_one("ghost-scenario", quiet=True)


def test_run_all_completes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # MCP scenario will skip if mcp not installed; we don't require it here
    # scenario 8 (resident-cognition) は時間がかかるため最短設定 (2 秒) にする.
    monkeypatch.setenv("LLIVE_RESIDENT_DURATION", "2")
    monkeypatch.setenv("LLIVE_DEMO_SEED", "42")
    monkeypatch.setenv("LLIVE_DEMO_NO_COLOR", "1")
    results = run_all(quiet=True)
    assert len(results) == 9
    for r in results:
        assert "ok" in r
        # Either succeeded, or recorded an error string — never raised
        if not r.get("ok"):
            assert "error" in r


def test_cli_loop_repeats_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    from llive.demo.runner import main

    rc = main(["--only", "1", "--loop", "2", "--lang", "ja"])
    assert rc == 0
    captured = capsys.readouterr()
    # Iteration banner must appear once for iteration 2/2 (iteration 1 is silent)
    assert "iteration 2/2" in captured.out


def test_cli_list_flag(capsys: pytest.CaptureFixture[str]) -> None:
    from llive.demo.runner import main

    rc = main(["--list"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "rad-quick-tour" in captured.out
    assert "consolidation-mirror" in captured.out
