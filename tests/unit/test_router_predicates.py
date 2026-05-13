"""Extra coverage for router/engine.py predicate paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.router.engine import RouterEngine, _eval_predicate


def _spec(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "routes.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_eval_predicate_prompt_length_lt():
    ok, _ = _eval_predicate("prompt_length_lt", 10, {"prompt_length": 5})
    assert ok
    ok, _ = _eval_predicate("prompt_length_lt", 10, {"prompt_length": 15})
    assert not ok


def test_eval_predicate_prompt_length_gte():
    ok, _ = _eval_predicate("prompt_length_gte", 10, {"prompt_length": 10})
    assert ok
    ok, _ = _eval_predicate("prompt_length_gte", 10, {"prompt_length": 9})
    assert not ok


def test_eval_predicate_task_tag():
    ok, _ = _eval_predicate("task_tag", "math", {"task_tag": "math"})
    assert ok
    ok, _ = _eval_predicate("task_tag", "math", {"task_tag": "code"})
    assert not ok


def test_eval_predicate_has_tag():
    ok, _ = _eval_predicate("has_tag", "memory", {"tags": ["routing", "memory"]})
    assert ok
    ok, _ = _eval_predicate("has_tag", "memory", {"tags": []})
    assert not ok


def test_eval_predicate_always_truthy():
    ok, _ = _eval_predicate("always", True, {})
    assert ok


def test_eval_predicate_unknown_key():
    ok, msg = _eval_predicate("totally_made_up", 42, {})
    assert not ok
    assert "unknown_predicate" in msg


def test_router_no_routes_rejects(tmp_path):
    with pytest.raises(ValueError):
        RouterEngine(_spec(tmp_path, "schema_version: 1\nroutes: []\n"))


def test_router_wrong_schema_version(tmp_path):
    with pytest.raises(ValueError):
        RouterEngine(_spec(tmp_path, "schema_version: 2\nroutes:\n  - container: x\n"))


def test_router_missing_container_field(tmp_path):
    with pytest.raises(ValueError):
        RouterEngine(_spec(tmp_path, "schema_version: 1\nroutes:\n  - when: {prompt_length_lt: 10}\n"))


def test_router_route_with_task_tag_features(tmp_path):
    spec = _spec(
        tmp_path,
        """\
schema_version: 1
routes:
  - container: math_path
    when: {task_tag: math}
  - container: default_v1
""",
    )
    eng = RouterEngine(spec)
    d = eng.select("x", features={"prompt_length": 1, "task_tag": "math"}, log_path=tmp_path / "log.jsonl")
    assert d.container == "math_path"


def test_router_features_from_prompt_with_extras():
    eng = RouterEngine(_spec(Path("specs/routes/default.yaml"), ""))  # use packaged default
    # actually we want from the existing default
    from llive.router.engine import RouterEngine as RE

    eng = RE()
    feats = eng.features_from_prompt("hello there", extra={"task_tag": "qa"})
    assert feats["task_tag"] == "qa"
    assert feats["prompt_length"] == 11


def test_router_load_non_dict(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(ValueError):
        RouterEngine(p)
