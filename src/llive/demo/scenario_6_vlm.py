"""Scenario 6: VLM describe-image with optional RAD grounding.

Generates a minimal 1x1 PNG on-the-fly, runs ``tool_vlm_describe_image``
twice (with and without a ``domain_hint``), and contrasts the assembled
prompts. Uses the MockBackend which reports the image count + media type,
so the demo works offline without a real VLM.

TRIZ #15 動的化 + #24 仲介 — RAD が VLM の知識仲介になり、ドメイン用語に
意識を集中させる効果を可視化。
"""

from __future__ import annotations

from typing import Any, ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext
from llive.llm.backend import GenerateRequest, GenerateResponse, LLMBackend
from llive.mcp.tools import tool_vlm_describe_image
from llive.memory.rad import RadCorpusIndex

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "1x1 の合成 PNG を渡し、VLM describe を 2 通り (RAD 無し / 有り) で実行。",
        "build_img": "1x1 PNG をメモリ上で生成中...",
        "seed_rad": "vision_corpus を予約準備 (synthetic)...",
        "plain": "RAD 無しの VLM describe:",
        "with_rad": "RAD 有り (domain_hint=vision_corpus) の VLM describe:",
        "reply": "  応答:",
        "hints": "  注入されたヒント: {n} 件 / {paths}",
        "summary": "RAD 有りで {n} 件のヒントが system に注入。同じ画像でも応答の方向付けが変わります。",
    },
    "en": {
        "intro": "Send a 1x1 synthetic PNG to VLM describe twice (without / with RAD).",
        "build_img": "Generating a 1x1 PNG in-memory...",
        "seed_rad": "Seeding vision_corpus (synthetic)...",
        "plain": "VLM describe without RAD:",
        "with_rad": "VLM describe with RAD (domain_hint=vision_corpus):",
        "reply": "  reply:",
        "hints": "  Hints injected: {n} via {paths}",
        "summary": "{n} hints injected with RAD on. Same image, different prompt grounding.",
    },
    "zh": {
        "intro": "向 VLM describe 传入 1x1 合成 PNG,分别在 RAD 关闭 / 开启下各调用一次。",
        "build_img": "在内存中生成 1x1 PNG...",
        "seed_rad": "准备 vision_corpus (synthetic)...",
        "plain": "VLM describe (RAD 关闭):",
        "with_rad": "VLM describe (RAD 开启: domain_hint=vision_corpus):",
        "reply": "  回复:",
        "hints": "  注入提示: {n} 条 / {paths}",
        "summary": "开启 RAD 注入 {n} 条提示。同一图像但 prompt 走向不同。",
    },
    "ko": {
        "intro": "1x1 합성 PNG 를 VLM describe 에 두 번 (RAD 없이 / 있음) 보냅니다.",
        "build_img": "1x1 PNG 를 메모리에서 생성 중...",
        "seed_rad": "vision_corpus 준비 (synthetic)...",
        "plain": "RAD 없는 VLM describe:",
        "with_rad": "RAD 있는 VLM describe (domain_hint=vision_corpus):",
        "reply": "  응답:",
        "hints": "  주입된 힌트: {n}건 / {paths}",
        "summary": "RAD 켜면 {n}건 힌트 주입. 같은 이미지라도 prompt 의 방향이 달라집니다.",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


# Minimal 1x1 PNG (red pixel) -- 67 bytes, valid PNG magic + IHDR + IDAT + IEND
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\x99c\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01"
    b"\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _RecordingBackend(LLMBackend):
    name = "recording-vlm-mock"

    def __init__(self) -> None:
        self.last: GenerateRequest | None = None

    @property
    def supports_vlm(self) -> bool:
        return True

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.last = request
        n_img = len(request.images)
        text = f"[vlm-mock] saw {n_img} image; prompt = {request.prompt[:60]}"
        return GenerateResponse(
            text=text,
            finish_reason="stop",
            backend=self.name,
            model="mock-vlm",
            raw={"images_seen": n_img},
        )


def _seed_vision_rad(root) -> None:  # type: ignore[no-untyped-def]
    base = root / "vision_corpus"
    base.mkdir(parents=True, exist_ok=True)
    (base / "color_terminology.md").write_text(
        "When asked to 'describe an image', VLMs benefit from explicit colour "
        "terminology. Prefer named hues (vermilion, cerulean) over generic "
        "labels for fine-grained discrimination tasks.",
        encoding="utf-8",
    )
    (base / "small_image_pitfalls.md").write_text(
        "Single-pixel and very small images mostly carry hue information; "
        "do not over-interpret structure or composition that cannot exist "
        "at that resolution.",
        encoding="utf-8",
    )


class VlmDescribeScenario(Scenario):
    id = "vlm-describe"
    titles: ClassVar[dict[str, str]] = {
        "ja": "VLM describe + RAD ヒント (画像 + 知識基盤)",
        "en": "VLM describe + RAD hint (image + knowledge grounding)",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, Any]:
        ctx.say("  " + _t("intro"))
        ctx.say("  " + _t("build_img"))
        img_path = ctx.tmp_path / "tiny.png"
        img_path.write_bytes(_PNG_1X1)

        ctx.say("  " + _t("seed_rad"))
        rad_root = ctx.tmp_path / "rad"
        _seed_vision_rad(rad_root)
        idx = RadCorpusIndex(root=rad_root)
        backend = _RecordingBackend()

        ctx.step(1, 2, _t("plain"))
        result_off = tool_vlm_describe_image(
            img_path,
            prompt="What is in this image? Describe colour and content.",
            backend=backend,
            index=idx,
        )
        ctx.say(_t("reply"))
        ctx.say(f"    {result_off['text']}")
        ctx.say(_t("hints", n=len(result_off.get("rad_hints_used") or []), paths="-"))

        ctx.step(2, 2, _t("with_rad"))
        result_on = tool_vlm_describe_image(
            img_path,
            prompt="What is in this image? Describe colour and content.",
            domain_hint="vision_corpus",
            backend=backend,
            index=idx,
        )
        ctx.say(_t("reply"))
        ctx.say(f"    {result_on['text']}")
        hints = result_on.get("rad_hints_used") or []
        ctx.say(_t(
            "hints",
            n=len(hints),
            paths=", ".join(h.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for h in hints) or "-",
        ))
        if backend.last and backend.last.system:
            ctx.say("  system prompt (head):")
            for line in backend.last.system.splitlines()[:6]:
                ctx.say(f"    | {line}")

        ctx.hr()
        ctx.say("  " + _t("summary", n=len(hints)))
        return {
            "hints_off": len(result_off.get("rad_hints_used") or []),
            "hints_on": len(hints),
            "image_path": str(img_path),
        }
