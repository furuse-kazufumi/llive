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


def test_list_scenarios_has_five() -> None:
    scenarios = list_scenarios()
    assert len(scenarios) == 5
    ids = [s.id for s in scenarios]
    assert ids == [
        "rad-quick-tour",
        "append-roundtrip",
        "code-review",
        "mcp-roundtrip",
        "openai-http",
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
    assert len(results) == 5
    for r in results:
        assert "ok" in r
        # Either succeeded, or recorded an error string — never raised
        if not r.get("ok"):
            assert "error" in r
