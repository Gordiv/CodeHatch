"""Translations for every text the bot shows on Discord.

Texts live in locales/<language>.json (flat "key": "text" pairs) and the setup guide in
locales/guide_<language>.json. Code always uses English keys; the server language is chosen in /setup.
"""
import json
import logging
import os

import discord
from discord import app_commands

from utils import config_store

LANGUAGES = {"en": "English", "pl": "Polski", "es": "Español"}
DEFAULT_LANGUAGE = "en"
LOCALES_DIR = os.path.join(config_store.ROOT, "locales")
# Discord's limits for translated slash command texts
NAME_LIMIT = 32
TEXT_LIMIT = 100

log = logging.getLogger("i18n")
_texts = {}
_guides = {}


def _read(name: str):
    """Parsed locales/<name>.json, or None. A damaged file is reported once (the bot then falls back to English)."""
    path = os.path.join(LOCALES_DIR, name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        log.error("locales/%s can't be read (%s): English texts are used instead. Put back the file from the bot "
                  "package or the last update.", name, e)
        return None


def _load(language: str) -> dict:
    if language not in _texts:
        data = _read(f"{language}.json")
        _texts[language] = data if isinstance(data, dict) else {}
    return _texts[language]


def language() -> str:
    """Current server language from config.json (cached by config_store)."""
    try:
        value = config_store.get("bot_settings").get("language", DEFAULT_LANGUAGE)
    except config_store.ConfigError:
        return DEFAULT_LANGUAGE
    return value if value in LANGUAGES else DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    if code not in LANGUAGES:
        raise ValueError(f"Unsupported language: {code}")
    config_store.set_values([("bot_settings", "language", code)])


def _format(text: str, kwargs: dict):
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError, AttributeError):
        return None


def t(key: str, lang: str = None, **kwargs) -> str:
    """Text for the given key in the server language, falling back to English and then to the key itself.
    A translation with a broken {placeholder} never breaks the command: the English text is used instead."""
    text = _load(lang or language()).get(key) or _load(DEFAULT_LANGUAGE).get(key) or key
    if not kwargs:
        return text
    result = _format(text, kwargs)
    if result is None:
        log.warning("Translation %s has a placeholder that doesn't fit; the English text is used.", key)
        result = _format(_load(DEFAULT_LANGUAGE).get(key) or key, kwargs)
    return result if result is not None else text


def raw(key: str, lang: str = None) -> str:
    """The text exactly as written, never formatted: for texts with literal { } (e.g. Luau code in catalog.ai_prompt)."""
    return _load(lang or language()).get(key) or _load(DEFAULT_LANGUAGE).get(key) or key


def has_key(key: str, lang: str) -> bool:
    return key in _load(lang)


def guide(lang: str = None) -> list:
    """Topics of /setup-guide in this language (English when the file is missing or damaged)."""
    lang = lang or language()
    if lang not in _guides:
        data = _read(f"guide_{lang}.json")
        _guides[lang] = data if isinstance(data, list) else None
    if _guides[lang]:
        return _guides[lang]
    if lang != DEFAULT_LANGUAGE:
        return guide(DEFAULT_LANGUAGE)
    return []


def L(key: str) -> app_commands.locale_str:
    """Slash command text: English default, translated by Discord for Polish and Spanish users."""
    return app_commands.locale_str(_load(DEFAULT_LANGUAGE).get(key, key), key=key)


class Translator(app_commands.Translator):
    LOCALES = {
        discord.Locale.polish: "pl",
        discord.Locale.spain_spanish: "es",
        discord.Locale.latin_american_spanish: "es",
    }
    NAMES = {app_commands.TranslationContextLocation.command_name, app_commands.TranslationContextLocation.group_name,
             app_commands.TranslationContextLocation.parameter_name}

    async def translate(self, string: app_commands.locale_str, locale: discord.Locale, context) -> str:
        lang = self.LOCALES.get(locale)
        key = string.extras.get("key")
        if not lang or not key:
            return None
        text = _load(lang).get(key)
        if not text:
            return None
        # A translation Discord would refuse would stop ALL commands from syncing: use the English text instead
        limit = NAME_LIMIT if getattr(context, "location", None) in self.NAMES else TEXT_LIMIT
        if len(text) > limit:
            log.warning("Translation %s [%s] is longer than %s characters; the English text is used.", key, lang, limit)
            return None
        return text
