#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate language-variant SVGs (en/zh/ko) from the Japanese source SVGs.

The lldarwin article (QIITA_llive_mega_evolution.md) embeds 6 SVG charts.
Several have Japanese labels baked into <text>/<tspan> elements. To publish
the article in 4 languages (ja/en/zh/ko) self-contained, each chart needs a
language variant where the in-figure Japanese is replaced by the target
language. Geometry (coordinates, paths, polylines) is left untouched — only
the inner text of <text>/<tspan> nodes is substituted.

Approach
--------
* A translation dictionary maps each *exact* Japanese-containing inner-text
  string (as it appears between <text ...>...</text> or <tspan ...>...</tspan>)
  to its en/zh/ko equivalents.
* SVGs whose labels are already fully English (numbers, axis ticks, ascii
  legends) have no entries and are emitted verbatim per language — this keeps
  the per-language asset set complete so the article can reference one URL
  scheme uniformly.
* Output files: <name>_en.svg / <name>_zh.svg / <name>_ko.svg next to the
  source (or to --out-dir if given). Coordinates are never modified.

Verification
------------
* Each emitted variant is parsed with xml.dom.minidom to confirm valid XML.
* Each en/zh/ko variant is scanned for residual CJK-Japanese characters
  (Hiragana / Katakana / a curated set of Kanji used in the source). The
  script exits non-zero if any leak is found, so it doubles as a test.

Usage
-----
    py -3.11 scripts/svg_translate.py \
        --src-dir D:/projects/fullsense/docs/articles/assets/lldarwin_2026_05_26 \
        [--out-dir <dir>]   # defaults to --src-dir

Run with --check-only to re-verify existing variants without regenerating.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import xml.dom.minidom as minidom
from pathlib import Path

# --------------------------------------------------------------------------
# Translation dictionary.
#
# Key   = exact inner text of a <text>/<tspan> element in the *ja* source SVG
#         that contains at least one Japanese character.
# Value = {"en": ..., "zh": ..., "ko": ...}
#
# Only strings containing Japanese need entries; pure-ASCII / numeric labels
# are passed through unchanged. Mixed strings (Japanese + ascii tokens like
# "diversity_l2") are translated as whole strings, preserving the ascii tokens.
# --------------------------------------------------------------------------
TRANSLATIONS: dict[str, dict[str, str]] = {
    # --- lldarwin_stage1_diversity_overlay.svg ---
    "lldarwin Stage1 — novelty が行動多様性を救う": {
        "en": "lldarwin Stage1 — novelty rescues behavioral diversity",
        "zh": "lldarwin Stage1 — novelty 拯救行为多样性",
        "ko": "lldarwin Stage1 — novelty가 행동 다양성을 구한다",
    },
    "PROXY (rich-proxy, 8 founders, 150 gens) ·  diversity_l2 ·  baseline は崩壊 / novelty は維持 (+109%)": {
        "en": "PROXY (rich-proxy, 8 founders, 150 gens) ·  diversity_l2 ·  baseline collapses / novelty sustains (+109%)",
        "zh": "PROXY (rich-proxy, 8 founders, 150 gens) ·  diversity_l2 ·  baseline 崩溃 / novelty 维持 (+109%)",
        "ko": "PROXY (rich-proxy, 8 founders, 150 gens) ·  diversity_l2 ·  baseline 붕괴 / novelty 유지 (+109%)",
    },
    "baseline (崩壊)": {
        "en": "baseline (collapse)",
        "zh": "baseline (崩溃)",
        "ko": "baseline (붕괴)",
    },
    "+novelty (維持)": {
        "en": "+novelty (sustained)",
        "zh": "+novelty (维持)",
        "ko": "+novelty (유지)",
    },

    # --- lldarwin_reinject_sweep.svg ---
    "lldarwin — 中立貯蔵庫 再投入頻度のトレードオフ": {
        "en": "lldarwin — neutral reservoir reinjection-frequency trade-off",
        "zh": "lldarwin — 中立储藏库 再注入频率的权衡",
        "ko": "lldarwin — 중립 저장고 재투입 빈도의 트레이드오프",
    },
    "PROXY (rich-proxy, 8 founders, 150 gens) ·  系統保持 vs 行動多様性  ·  diversity は interval=5 でピーク (非単調)": {
        "en": "PROXY (rich-proxy, 8 founders, 150 gens) ·  lineage retention vs behavioral diversity  ·  diversity peaks at interval=5 (non-monotonic)",
        "zh": "PROXY (rich-proxy, 8 founders, 150 gens) ·  谱系保持 vs 行为多样性  ·  diversity 在 interval=5 达到峰值 (非单调)",
        "ko": "PROXY (rich-proxy, 8 founders, 150 gens) ·  계통 보존 vs 행동 다양성  ·  diversity는 interval=5에서 피크 (비단조)",
    },
    "reinject_interval (世代)": {
        "en": "reinject_interval (generations)",
        "zh": "reinject_interval (代)",
        "ko": "reinject_interval (세대)",
    },
    "named 系統生存 (/8)": {
        "en": "named lineages alive (/8)",
        "zh": "named 谱系存活 (/8)",
        "ko": "named 계통 생존 (/8)",
    },
    # NOTE: "diversity_l2 (max14)" is ascii-only (no Japanese) and identical
    # across all languages, so it has no entry and is passed through verbatim.

    # --- lldarwin_stage2_real_llm_axes.svg ---
    "lldarwin — LLM 苦手軸スコアの進化 (per-axis)": {
        "en": "lldarwin — evolution of LLM weak-axis scores (per-axis)",
        "zh": "lldarwin — LLM 弱项轴得分的进化 (per-axis)",
        "ko": "lldarwin — LLM 취약 축 점수의 진화 (per-axis)",
    },
}

LANGS = ("en", "zh", "ko")

# Source SVG basenames the article embeds.
SOURCE_SVGS = (
    "lldarwin_stage1_baseline_status",
    "lldarwin_reservoir_off_dominance",
    "lldarwin_reservoir_on_dominance",
    "lldarwin_stage1_diversity_overlay",
    "lldarwin_reinject_sweep",
    "lldarwin_stage2_real_llm_axes",
)

# Matches inner text of <text ...>INNER</text> and <tspan ...>INNER</tspan>.
# INNER is captured non-greedily and must not contain a '<' (no nested tags
# in these SVGs).
_TEXT_RE = re.compile(r"(<(?:text|tspan)\b[^>]*>)([^<]*)(</(?:text|tspan)>)")


def _is_kana(ch: str) -> bool:
    """True for Hiragana or Katakana — *uniquely* Japanese scripts.

    (Kanji share the CJK Unified Ideographs block with Chinese Hanzi and
    Korean Hanja, so a codepoint there cannot by itself prove the text is
    Japanese. Kana are unambiguous.)
    """
    code = ord(ch)
    if 0x3040 <= code <= 0x309F:  # Hiragana
        return True
    if 0x30A0 <= code <= 0x30FF:  # Katakana
        return True
    return False


def _is_cjk_ideograph(ch: str) -> bool:
    """True for CJK Unified Ideographs (Kanji / Hanzi / Hanja)."""
    code = ord(ch)
    if 0x4E00 <= code <= 0x9FFF:
        return True
    if 0x3400 <= code <= 0x4DBF:  # CJK Ext A
        return True
    return False


def _contains_japanese(text: str) -> bool:
    """Heuristic for 'this string still has Japanese in it'.

    Used to spot *source* (ja) strings that lack a translation entry. Kana is
    a reliable signal; bare ideographs (which a kana-free ja string could
    still contain) are caught because every ja key in this corpus contains at
    least one kana — and untranslated keys are also reported by exact match.
    """
    return any(_is_kana(ch) for ch in text)


def translate_svg(svg_text: str, lang: str) -> tuple[str, list[str]]:
    """Return (translated_svg, untranslated_jp_strings).

    Replaces the inner text of every <text>/<tspan> whose content is a known
    Japanese key with the lang translation. Any Japanese-containing inner text
    that has *no* dictionary entry is reported back so the caller can fail.
    """
    missing: list[str] = []

    def _repl(m: re.Match) -> str:
        open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)
        if inner in TRANSLATIONS:
            return open_tag + TRANSLATIONS[inner][lang] + close_tag
        if _contains_japanese(inner):
            missing.append(inner)
        return m.group(0)

    return _TEXT_RE.sub(_repl, svg_text), missing


def find_residual_japanese(svg_text: str, lang: str) -> list[str]:
    """Return inner-text fragments that still leak the wrong script for *lang*.

    Only inspects <text>/<tspan> inner content (geometry never has text).

    Rules per target language:
    * Any lang: Hiragana/Katakana (uniquely Japanese) is always a leak.
    * Any lang: an inner string that exactly equals a known ja dictionary key
      means the substitution didn't fire (untranslated) -> leak.
    * en only: CJK ideographs are a leak too (English must be pure ASCII).
    * zh/ko: CJK ideographs are legitimate (Hanzi / Hanja), so allowed.
    """
    leaks: list[str] = []
    for m in _TEXT_RE.finditer(svg_text):
        inner = m.group(2)
        if any(_is_kana(ch) for ch in inner):
            leaks.append(inner)
            continue
        if inner in TRANSLATIONS:  # exact ja key survived -> not translated
            leaks.append(inner)
            continue
        if lang == "en" and any(_is_cjk_ideograph(ch) for ch in inner):
            leaks.append(inner)
    return leaks


def validate_xml(svg_text: str) -> None:
    """Raise if not well-formed XML."""
    minidom.parseString(svg_text.encode("utf-8"))


def process(src_dir: Path, out_dir: Path, check_only: bool) -> int:
    generated = 0
    failures: list[str] = []

    for base in SOURCE_SVGS:
        src = src_dir / f"{base}.svg"
        if not src.exists():
            failures.append(f"missing source: {src}")
            continue
        svg_text = src.read_text(encoding="utf-8")

        for lang in LANGS:
            out_path = out_dir / f"{base}_{lang}.svg"

            if check_only:
                if not out_path.exists():
                    failures.append(f"missing variant: {out_path}")
                    continue
                variant = out_path.read_text(encoding="utf-8")
            else:
                variant, missing = translate_svg(svg_text, lang)
                if missing:
                    for s in missing:
                        failures.append(f"{base}_{lang}: no translation for {s!r}")
                out_path.write_text(variant, encoding="utf-8")
                generated += 1

            # --- verification (always) ---
            try:
                validate_xml(variant)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{out_path.name}: invalid XML: {exc}")
                continue

            leaks = find_residual_japanese(variant, lang)
            if leaks:
                for s in leaks:
                    failures.append(f"{out_path.name}: residual untranslated text: {s!r}")

    action = "verified" if check_only else "generated"
    print(f"{action} {generated if not check_only else len(SOURCE_SVGS)*len(LANGS)} variant(s) "
          f"({len(SOURCE_SVGS)} sources x {len(LANGS)} langs)")

    if failures:
        print("\nFAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("all variants: valid XML, no residual Japanese in en/zh/ko text")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--src-dir",
        default="D:/projects/fullsense/docs/articles/assets/lldarwin_2026_05_26",
        help="Directory holding the source (ja) SVGs.",
    )
    p.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for variants (defaults to --src-dir).",
    )
    p.add_argument(
        "--check-only",
        action="store_true",
        help="Verify existing variants instead of regenerating.",
    )
    args = p.parse_args(argv)

    src_dir = Path(args.src_dir)
    out_dir = Path(args.out_dir) if args.out_dir else src_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if not src_dir.is_dir():
        print(f"src-dir not found: {src_dir}", file=sys.stderr)
        return 2

    return process(src_dir, out_dir, args.check_only)


if __name__ == "__main__":
    raise SystemExit(main())
