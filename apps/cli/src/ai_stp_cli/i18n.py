"""Human CLI strings, keyed by the English source message.

Machine help, JSON field names and registry summaries stay English: they are
the agent contract. Human `CliFailure` text is looked up here. Locale comes
from `AI_STP_LOCALE` (`en` or `ru`, default `en`) so existing tests and the
agent path keep English unless a person asks for Russian.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from importlib.resources import files
from typing import Final, cast

LOCALES: Final[tuple[str, ...]] = ("en", "ru")
DEFAULT_LOCALE: Final[str] = "en"
ENV_NAME: Final[str] = "AI_STP_LOCALE"


def active_locale() -> str:
    raw = os.environ.get(ENV_NAME, DEFAULT_LOCALE).strip().lower()
    return raw if raw in LOCALES else DEFAULT_LOCALE


@lru_cache(maxsize=4)
def _catalog(locale: str) -> dict[str, str]:
    payload = files("ai_stp_cli").joinpath("messages", f"{locale}.json").read_text(encoding="utf-8")
    parsed: object = json.loads(payload)
    if not isinstance(parsed, dict):
        return {}
    catalog: dict[str, str] = {}
    for raw_key, raw_value in cast(dict[object, object], parsed).items():
        if isinstance(raw_key, str) and isinstance(raw_value, str):
            catalog[raw_key] = raw_value
    return catalog


def localize(message: str) -> str:
    """Return the catalog text for `message`, or the source string if absent."""
    locale = active_locale()
    table = _catalog(locale)
    found = table.get(message)
    if found is not None:
        return found
    if locale != DEFAULT_LOCALE:
        return _catalog(DEFAULT_LOCALE).get(message, message)
    return message
