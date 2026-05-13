"""Rule-based router (RTR-01) — YAML-declared routes with feature predicates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from llive.router.explanation import (
    CandidateExplanation,
    RouterDecision,
    RouterExplanation,
    append_explanation,
)


@dataclass
class _Route:
    container: str
    when: dict[str, Any]
    raw_rule: str  # human-readable label

    def matches(self, features: dict[str, Any]) -> tuple[bool, str]:
        if not self.when:
            return True, "default"  # fallback rule
        for key, expected in self.when.items():
            ok, why = _eval_predicate(key, expected, features)
            if not ok:
                return False, why
        return True, "all_conditions_met"


def _eval_predicate(key: str, expected: Any, features: dict[str, Any]) -> tuple[bool, str]:
    if key == "prompt_length_lt":
        length = int(features.get("prompt_length", 0))
        thr = int(expected)
        return length < thr, f"prompt_length={length} {'<' if length < thr else '>='} {thr}"
    if key == "prompt_length_gte":
        length = int(features.get("prompt_length", 0))
        thr = int(expected)
        return length >= thr, f"prompt_length={length} {'>=' if length >= thr else '<'} {thr}"
    if key == "task_tag":
        tag = features.get("task_tag")
        return tag == expected, f"task_tag={tag!r} {'==' if tag == expected else '!='} {expected!r}"
    if key == "has_tag":
        tags = set(features.get("tags") or [])
        return expected in tags, f"tag {expected!r} {'in' if expected in tags else 'not in'} {sorted(tags)}"
    if key == "always":
        return bool(expected), "always"
    return False, f"unknown_predicate:{key}"


class RouterEngine:
    """Loads a YAML route file and selects a container per request."""

    def __init__(self, spec_path: Path | str | dict[str, Any] | None = None) -> None:
        spec = self._load(spec_path) if not isinstance(spec_path, dict) else spec_path
        self._validate(spec)
        self.schema_version: int = int(spec["schema_version"])
        self.routes: list[_Route] = [
            _Route(
                container=r["container"],
                when=dict(r.get("when") or {}),
                raw_rule=self._rule_repr(r.get("when") or {}),
            )
            for r in spec["routes"]
        ]

    # -- load --------------------------------------------------------------

    @staticmethod
    def _load(spec_path: Path | str | None) -> dict[str, Any]:
        if spec_path is None:
            # 1) prefer the packaged default at llive/_specs/routes/default.yaml
            here = Path(__file__).resolve()
            packaged = here.parent.parent / "_specs" / "routes" / "default.yaml"
            spec_path = packaged if packaged.exists() else Path("specs/routes/default.yaml")
        path = Path(spec_path)
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"route file must be a mapping: {path}")
        return data

    @staticmethod
    def _validate(spec: dict[str, Any]) -> None:
        if spec.get("schema_version") != 1:
            raise ValueError("router schema_version must be 1")
        routes = spec.get("routes")
        if not isinstance(routes, list) or not routes:
            raise ValueError("router routes must be a non-empty list")
        for r in routes:
            if "container" not in r:
                raise ValueError(f"route entry missing container: {r}")

    @staticmethod
    def _rule_repr(when: dict[str, Any]) -> str:
        if not when:
            return "<default>"
        return ", ".join(f"{k}={v}" for k, v in when.items())

    # -- main --------------------------------------------------------------

    def features_from_prompt(self, prompt: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        features: dict[str, Any] = {
            "prompt_length": len(prompt),
            "prompt_token_count_approx": max(1, len(prompt.split())),
        }
        if extra:
            features.update(extra)
        return features

    def select(
        self,
        prompt: str,
        *,
        features: dict[str, Any] | None = None,
        request_id: str | None = None,
        log_path: Path | str | None = None,
    ) -> RouterDecision:
        feats = features or self.features_from_prompt(prompt)
        candidates: list[CandidateExplanation] = []
        selected: _Route | None = None
        matched_rule = "<none>"
        for route in self.routes:
            ok, reason = route.matches(feats)
            candidates.append(
                CandidateExplanation(container=route.container, matched=ok, reason=reason)
            )
            if ok and selected is None:
                selected = route
                matched_rule = route.raw_rule
        if selected is None:
            # router specs always include a fallback; if missing, raise
            raise RuntimeError("no route matched and no fallback (empty when:) provided")

        kwargs = {
            "selected_container": selected.container,
            "matched_rule": matched_rule,
            "candidates": candidates,
            "prompt_features": feats,
        }
        if request_id is not None:
            kwargs["request_id"] = request_id
        explanation = RouterExplanation(**kwargs)
        append_explanation(explanation, log_path)
        return RouterDecision(container=selected.container, explanation=explanation)
