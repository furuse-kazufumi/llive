"""Minimal i18n for demo narration.

``LLIVE_DEMO_LANG`` で言語を選択 (``ja`` 既定):

* ``ja`` — 日本語 (既定)
* ``en`` / ``en-US`` — 英語
* ``zh`` / ``zh-CN`` — 简体中文
* ``ko`` / ``ko-KR`` — 한국어

辞書は scenario モジュールが個別に持ち、``translate(key, **kwargs)`` で取得する。
未登録キーは ``ja`` にフォールバック、それも無ければ key 自身を返す。

意図して軽量に: gettext 等は使わず、純 Python dict で済ませる。
"""

from __future__ import annotations

import os
from typing import Any

SUPPORTED_LANGS = ("ja", "en", "zh", "ko")


def current_lang() -> str:
    raw = (os.environ.get("LLIVE_DEMO_LANG") or "ja").lower().replace("_", "-")
    # Map locale-style codes (en-US, zh-CN) to bare 2-letter
    short = raw.split("-")[0]
    if short in SUPPORTED_LANGS:
        return short
    return "ja"


def translate(catalog: dict[str, dict[str, str]], key: str, /, **kwargs: Any) -> str:
    """Look up ``key`` in ``catalog[lang]``, fall back to ja, then to the key itself."""
    lang = current_lang()
    lang_table = catalog.get(lang) or {}
    text = lang_table.get(key) or catalog.get("ja", {}).get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (IndexError, KeyError):
            return text
    return text
