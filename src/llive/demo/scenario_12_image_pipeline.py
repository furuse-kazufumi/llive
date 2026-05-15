# ruff: noqa: RUF001
"""Scenario 12 — 画像処理アルゴリズム提案デモ.

ユーザ意志 (2026-05-15):
> 「画像を読み込ませて画像処理アルゴリズムの提案とか、会社では
> ありきたりなものをやってますが、そのあたりのデモも含めて用意して
> あると助かります。」

会社で日常的に行う「この画像どうしますか」相談を 30 秒で実演する demo:

1. ``image_corpus_v2`` 相当の mini-RAD に noise / edge / segmentation 3 つの
   小さな skill ファイルを書く
2. 軽量 PNG (1x1 グレースケール) を 1 枚読み込み、Mock VLM backend へ渡す
3. VLM が「画像の特徴」を返したという想定で、RAD から関連 skill を grounding
4. 3 アルゴリズム (Gaussian / bilateral / median) の比較表 + 推奨を出力
5. 推奨理由とリスクを併せて表示 (ノイズ種別 × 計算コスト trade-off)

Mock backend を使うのでネットワーク / GPU 不要。ja / en / zh / ko 多言語。
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext
from llive.llm.backend import GenerateRequest, MockBackend
from llive.memory.rad import RadCorpusIndex
from llive.memory.rad.query import query as rad_query

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "会社で日常的にある「この画像どうしますか」相談を 30 秒で実演します。VLM (Mock) + RAD ヒントで画像処理アルゴリズム 3 候補を比較。",
        "step1": "  [1/4] 画像を 1 枚読み込み (1x1 PNG、ネットワーク不要)",
        "step1_size": "    bytes={n} / base64_len={b}",
        "step2": "  [2/4] VLM (Mock) に「特徴抽出してください」依頼",
        "step2_resp": "    response: {r}",
        "step3": "  [3/4] RAD image_corpus_v2 から関連 skill を grounding",
        "step3_hit": "    [{score:.2f}] {path}",
        "step3_excerpt": "        {text}",
        "step4": "  [4/4] アルゴリズム 3 候補の比較表 + 推奨:",
        "row": "    {algo:24s} cost={cost:6s}  noise_class={cls:12s}  edge_pres={edge}",
        "verdict": "  → 推奨: {algo} (理由: {reason})",
        "risk": "  ⚠ リスク: {risk}",
        "outro": "  ✨ 画像 1 枚から 3 候補比較 + 推奨を 30 秒で生成 — 会社デモにも使えるテンプレ",
    },
    "en": {
        "intro": "A daily-life 'what should we do with this image' consultation in 30 seconds. VLM (Mock) + RAD hints compare 3 image-processing algorithms.",
        "step1": "  [1/4] Load 1 image (1x1 PNG, no network)",
        "step1_size": "    bytes={n} / base64_len={b}",
        "step2": "  [2/4] Ask VLM (Mock) to extract features",
        "step2_resp": "    response: {r}",
        "step3": "  [3/4] Ground via RAD image_corpus_v2 skills",
        "step3_hit": "    [{score:.2f}] {path}",
        "step3_excerpt": "        {text}",
        "step4": "  [4/4] Comparison table for 3 candidates + recommendation:",
        "row": "    {algo:24s} cost={cost:6s}  noise_class={cls:12s}  edge_pres={edge}",
        "verdict": "  → Recommendation: {algo} (reason: {reason})",
        "risk": "  ⚠ Risk: {risk}",
        "outro": "  ✨ 1 image → 3-way comparison + recommendation in 30 seconds. Useful as a corporate demo template.",
    },
    "zh": {
        "intro": "用 30 秒模拟公司常见的「这张图怎么处理」咨询。VLM (Mock) + RAD hint 比较 3 种图像处理算法。",
        "step1": "  [1/4] 加载 1 张图像 (1x1 PNG, 不需要网络)",
        "step1_size": "    bytes={n} / base64_len={b}",
        "step2": "  [2/4] 让 VLM (Mock) 提取特征",
        "step2_resp": "    response: {r}",
        "step3": "  [3/4] 用 RAD image_corpus_v2 做 grounding",
        "step3_hit": "    [{score:.2f}] {path}",
        "step3_excerpt": "        {text}",
        "step4": "  [4/4] 3 个候选算法的对比表 + 推荐:",
        "row": "    {algo:24s} cost={cost:6s}  noise_class={cls:12s}  edge_pres={edge}",
        "verdict": "  → 推荐: {algo} (理由: {reason})",
        "risk": "  ⚠ 风险: {risk}",
        "outro": "  ✨ 1 张图 → 3 候选对比 + 推荐 30 秒生成 — 可作为公司演示模板",
    },
    "ko": {
        "intro": "회사에서 일상적인 '이 이미지 어떻게 할까요' 상담을 30 초로 실연. VLM (Mock) + RAD hint 로 이미지 처리 알고리즘 3 후보 비교.",
        "step1": "  [1/4] 이미지 1 장 로드 (1x1 PNG, 네트워크 불필요)",
        "step1_size": "    bytes={n} / base64_len={b}",
        "step2": "  [2/4] VLM (Mock) 에게 특징 추출 의뢰",
        "step2_resp": "    response: {r}",
        "step3": "  [3/4] RAD image_corpus_v2 grounding",
        "step3_hit": "    [{score:.2f}] {path}",
        "step3_excerpt": "        {text}",
        "step4": "  [4/4] 3 후보 알고리즘 비교표 + 추천:",
        "row": "    {algo:24s} cost={cost:6s}  noise_class={cls:12s}  edge_pres={edge}",
        "verdict": "  → 추천: {algo} (이유: {reason})",
        "risk": "  ⚠ 리스크: {risk}",
        "outro": "  ✨ 이미지 1 장 → 3 후보 비교 + 추천 30 초 생성 — 회사 데모 템플릿",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


# 最小 1x1 グレースケール PNG (8 bytes header + 17 bytes IHDR + ... 計 67 bytes)
# 確実に動く最小 PNG signature を base64 で持つ
_PNG_1X1_GRAY_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgAAAAAgABc3UBGAAAAABJRU5ErkJggg=="
)


# 提案する 3 アルゴリズム + メタ
_CANDIDATES = [
    {
        "algo": "Gaussian blur",
        "cost": "low",
        "noise_class": "white",
        "edge_pres": False,
        "reason_short": "Gaussian noise + speed-first",
    },
    {
        "algo": "Bilateral filter",
        "cost": "high",
        "noise_class": "white+edge",
        "edge_pres": True,
        "reason_short": "edge preservation needed",
    },
    {
        "algo": "Median filter",
        "cost": "med",
        "noise_class": "salt-pepper",
        "edge_pres": True,
        "reason_short": "salt-and-pepper / impulse",
    },
]


# Mini RAD content for image_corpus_v2
_RAD_DOCS: dict[str, list[tuple[str, str]]] = {
    "image_corpus_v2": [
        (
            "gaussian_blur.md",
            "Gaussian blur convolves with N(0, sigma^2) kernel. "
            "Fast (separable). Best for white Gaussian noise. Does not preserve edges.",
        ),
        (
            "bilateral_filter.md",
            "Bilateral filter weights by both spatial distance and intensity "
            "distance, preserving edges while smoothing. O(n) per pixel, slower than Gaussian.",
        ),
        (
            "median_filter.md",
            "Median filter replaces each pixel with the median of its "
            "neighborhood. Robust to salt-and-pepper noise. Preserves edges better than mean filter.",
        ),
    ],
}


def _build_mini_rad(root: Path) -> RadCorpusIndex:
    root.mkdir(parents=True, exist_ok=True)
    for dom, docs in _RAD_DOCS.items():
        d = root / dom
        d.mkdir(exist_ok=True)
        for fname, text in docs:
            (d / fname).write_text(text + "\n", encoding="utf-8")
    return RadCorpusIndex(root=root)


def _recommend(noise_hint: str) -> tuple[dict[str, Any], str, str]:
    """noise_hint から 1 候補を選び (algo, reason, risk) を返す.

    ヒューリスティック:
    - 'salt' / 'impulse' を含む → median
    - 'edge' を含む → bilateral
    - その他 → gaussian
    """
    h = (noise_hint or "").lower()
    if "salt" in h or "impulse" in h:
        c = _CANDIDATES[2]
        risk = "median は constant-region で details を消す可能性"
    elif "edge" in h:
        c = _CANDIDATES[1]
        risk = "bilateral は計算コストが高く 4K 画像では遅い"
    else:
        c = _CANDIDATES[0]
        risk = "Gaussian は edge を失う — 構造物 / 文字認識前段では不向き"
    return c, c["reason_short"], risk


class ImageAlgorithmAdvisorScenario(Scenario):
    id = "image-algorithm-advisor"
    titles: ClassVar[dict[str, str]] = {
        "ja": "画像処理アルゴリズム提案 (VLM + RAD で 3 候補比較 + 推奨)",
        "en": "Image-processing algorithm advisor (VLM + RAD, 3-way + verdict)",
        "zh": "图像处理算法推荐 (VLM + RAD 3 候选 + 推荐)",
        "ko": "이미지 처리 알고리즘 추천 (VLM + RAD 3 후보 + 추천)",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, Any]:
        ctx.say("  " + _t("intro"))

        # [1/4] 1x1 PNG を読み込み
        img_bytes = base64.b64decode(_PNG_1X1_GRAY_B64)
        ctx.say(_t("step1"))
        ctx.say(_t("step1_size", n=len(img_bytes), b=len(_PNG_1X1_GRAY_B64)))

        # [2/4] VLM mock 呼出し
        backend = MockBackend(prefix="[vlm-mock]")
        req = GenerateRequest(
            prompt="extract noise characteristics + edge density from the image",
            images=[img_bytes],
            max_tokens=80,
        )
        resp = backend.generate(req)
        ctx.say(_t("step2"))
        ctx.say(_t("step2_resp", r=resp.text[:120]))

        # [3/4] RAD で grounding
        idx = _build_mini_rad(ctx.tmp_path / "rad")
        ctx.say(_t("step3"))
        hits = rad_query(idx, "noise edge filter smoothing", limit=3, include_learned=False)
        hint_paths: list[str] = []
        for h in hits:
            rel = h.doc_path.relative_to(idx.root / h.domain).as_posix()
            ctx.say(_t("step3_hit", score=h.score, path=rel))
            ctx.say(_t("step3_excerpt", text=h.excerpt[:80]))
            hint_paths.append(rel)

        # [4/4] 比較表 + 推奨
        ctx.say(_t("step4"))
        for c in _CANDIDATES:
            ctx.say(
                _t(
                    "row",
                    algo=c["algo"],
                    cost=c["cost"],
                    cls=c["noise_class"],
                    edge=("yes" if c["edge_pres"] else "no"),
                )
            )
        # VLM が「edge preservation needed」を返したと想定
        chosen, reason, risk = _recommend("edge preservation needed")
        ctx.say(_t("verdict", algo=chosen["algo"], reason=reason))
        ctx.say(_t("risk", risk=risk))
        ctx.hr()
        ctx.say(_t("outro"))

        return {
            "image_bytes": len(img_bytes),
            "vlm_response_head": resp.text[:80],
            "rad_hints": hint_paths,
            "candidates": [c["algo"] for c in _CANDIDATES],
            "recommended": chosen["algo"],
            "reason": reason,
            "risk_summary": risk,
        }
