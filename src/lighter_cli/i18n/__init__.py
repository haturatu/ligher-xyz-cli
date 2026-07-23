"""gettext-backed localisation for all Lighter CLI presentation layers."""
from __future__ import annotations

import gettext as _gettext
import os
from collections.abc import Sequence
from pathlib import Path

DOMAIN = "lighter_cli"
LOCALE_DIR = Path(__file__).parent.parent / "locale"
DEFAULT_LANGUAGE = "en"
_translator: _gettext.NullTranslations = _gettext.NullTranslations()
_language = DEFAULT_LANGUAGE


def _normalise(value: str | None) -> str:
    return (value or DEFAULT_LANGUAGE).split(":", 1)[0].split(".", 1)[0].split("_", 1)[0].lower()


def language_from_argv(argv: Sequence[str] | None = None) -> str:
    tokens = list(argv or [])
    for index, token in enumerate(tokens):
        if token == "--lang" and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith("--lang="):
            return token.split("=", 1)[1]
    for variable in ("LIGHTER_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        if value := os.getenv(variable):
            return value
    return DEFAULT_LANGUAGE


def install_language(language: str | None = None) -> str:
    global _translator, _language
    chosen = _normalise(language)
    _translator = _gettext.translation(DOMAIN, LOCALE_DIR, languages=[chosen], fallback=True)
    _language = chosen
    return chosen


def current_language() -> str:
    return _language


def _(message: str) -> str:
    return _translator.gettext(message)
