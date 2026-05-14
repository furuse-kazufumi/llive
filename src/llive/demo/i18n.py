"""Minimal i18n for demo narration.

``LLIVE_DEMO_LANG`` が ``en`` だと英語、それ以外 (既定) は日本語。
辞書は scenario モジュールが個別に持ち、``t(key, **kwargs)`` で取得する。

意図して軽量に: gettext 等は使わず、純 Python dict で済ませる。
"""

from __future__ import annotations

import os
from typing import Any


def current_lang() -> str:
    raw = (os.environ.get("LLIVE_DEMO_LANG") or "ja").lower()
    if raw.startswith("en"):
        return "en"
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
