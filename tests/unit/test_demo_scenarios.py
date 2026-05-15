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


def test_list_scenarios_has_eight() -> None:
    scenarios = list_scenarios()
    assert len(scenarios) == 8
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


def test_run_one_unknown_raises() -> None:
    with pytest.raises(SystemExit):
        run_one("ghost-scenario", quiet=True)


def test_run_all_completes(capsys: pytest.CaptureFixture[str]) -> None:
    # MCP scenario will skip if mcp not installed; we don't require it here
    results = run_all(quiet=True)
    assert len(results) == 7
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
