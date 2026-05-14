"""Scenario 3: code_review with RAD hint injection.

Shows how llive's ``tool_code_review`` grounds an LLM-driven review in
``security_corpus_v2`` excerpts. We use a deliberately vulnerable C
snippet and a ``RecordingBackend`` so the demo runs offline yet exposes
the assembled system prompt + injected hints.

This is the differentiated value of llive over a bare-LLM workflow: the
same model gets to read curated security knowledge before it answers.
"""

from __future__ import annotations

from typing import Any, ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext
from llive.llm.backend import GenerateRequest, GenerateResponse, LLMBackend
from llive.mcp.tools import tool_code_review
from llive.memory.rad import RadCorpusIndex

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "security_corpus からヒントを抜き、LLM にレビューさせる流れを示します。",
        "seed": "ミニ security_corpus を生成中...",
        "code": "脆弱コード:",
        "review": "tool_code_review を実行 (mock backend、ネットワーク不要)...",
        "hints": "  注入された RAD ヒント ({n}件):",
        "system_head": "  生成された system prompt の冒頭:",
        "reply": "  LLM 応答:",
        "summary": "ヒント {n} 件が system に注入され、LLM がそれを下敷きに回答。",
    },
    "en": {
        "intro": "Pull hints from security_corpus and let an LLM review the code.",
        "seed": "Seeding a tiny security_corpus...",
        "code": "Vulnerable code:",
        "review": "Running tool_code_review (mock backend, no network)...",
        "hints": "  Injected RAD hints ({n}):",
        "system_head": "  System prompt head:",
        "reply": "  LLM reply:",
        "summary": "{n} hints injected into the system prompt before generation.",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


VULNERABLE_C = (
    "void greet(const char* user) {\n"
    "    char buf[16];\n"
    "    strcpy(buf, user);          /* unchecked length */\n"
    "    printf(buf);                /* untrusted format string */\n"
    "}\n"
)


class _RecordingBackend(LLMBackend):
    """Captures the constructed GenerateRequest so the demo can show it."""

    name = "recording-mock"

    def __init__(self) -> None:
        self.last: GenerateRequest | None = None

    @property
    def supports_vlm(self) -> bool:
        return True

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.last = request
        return GenerateResponse(
            text=(
                "- L3: strcpy() lacks bounds check (CWE-120); use strncpy or snprintf.\n"
                "- L4: printf(buf) is a CWE-134 format-string sink; use printf(\"%s\", buf).\n"
            ),
            finish_reason="stop",
            backend=self.name,
            model="mock-1",
            raw={},
        )


def _seed_security_corpus(root):  # type: ignore[no-untyped-def]
    base = root / "security_corpus_v2"
    base.mkdir(parents=True, exist_ok=True)
    (base / "strcpy_overflow.md").write_text(
        "strcpy() copies until NUL; if source exceeds destination size the "
        "stack adjacent to buf is corrupted. Prefer strncpy / strlcpy / snprintf.",
        encoding="utf-8",
    )
    (base / "format_string.md").write_text(
        "Calling printf with attacker-controlled format specifiers (e.g. %x, %s, %n) "
        "leaks memory or enables arbitrary writes. Always use printf(\"%s\", buf).",
        encoding="utf-8",
    )
    return base


class CodeReviewScenario(Scenario):
    id = "code-review"
    titles: ClassVar[dict[str, str]] = {
        "ja": "RAD ヒント注入つきコードレビュー",
        "en": "Code review with RAD hint injection",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, Any]:
        ctx.say("  " + _t("intro"))
        ctx.say("  " + _t("seed"))
        rad_root = ctx.tmp_path / "rad"
        _seed_security_corpus(rad_root)
        idx = RadCorpusIndex(root=rad_root)
        backend = _RecordingBackend()

        ctx.step(1, 3, _t("code"))
        for line in VULNERABLE_C.splitlines():
            ctx.say(f"    {line}")

        ctx.step(2, 3, _t("review"))
        result = tool_code_review(
            VULNERABLE_C,
            backend=backend,
            index=idx,
            hint_limit=3,
        )

        hints = result.get("rad_hints_used") or []
        ctx.say(_t("hints", n=len(hints)))
        for h in hints:
            ctx.say(f"    - {h}")
        ctx.say(_t("system_head"))
        if backend.last and backend.last.system:
            for line in backend.last.system.splitlines()[:6]:
                ctx.say(f"    | {line}")
        ctx.step(3, 3, _t("reply"))
        for line in str(result.get("text", "")).splitlines():
            ctx.say(f"    {line}")

        ctx.hr()
        ctx.say("  " + _t("summary", n=len(hints)))
        return {"hint_count": len(hints), "domain": result.get("domain")}
