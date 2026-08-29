"""CLI human strings live in locale catalogs, not only at the call site."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.i18n import localize

CLI_ROOT = Path(__file__).resolve().parents[2] / "apps" / "cli" / "src"
MESSAGES = CLI_ROOT / "ai_stp_cli" / "messages"


def _catalog(locale: str) -> dict[str, str]:
    parsed: object = json.loads((MESSAGES / f"{locale}.json").read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise AssertionError(f"{locale} catalog is not an object")
    catalog: dict[str, str] = {}
    for raw_key, raw_value in cast(dict[object, object], parsed).items():
        if isinstance(raw_key, str) and isinstance(raw_value, str):
            catalog[raw_key] = raw_value
    return catalog


def _static_failure_messages() -> set[str]:
    found: set[str] = set()
    for path in CLI_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Name) or func.id != "CliFailure":
                continue
            if len(node.args) < 2:
                continue
            found.update(_message_texts(node.args[1]))
    return found


def _message_texts(node: ast.AST) -> set[str]:
    """English catalog keys that do not depend on a runtime value.

    Interpolated f-strings and names (`INTERNAL_MESSAGE`, a helper's `message`)
    are not keys: each interpolation would be a different catalog entry, and
    the variable belongs in `details`. Both branches of a constant `if` are.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                return set()
        return {"".join(parts)} if parts else set()
    if isinstance(node, ast.IfExp):
        return _message_texts(node.body) | _message_texts(node.orelse)
    return set()


def test_locale_catalogs_share_keys() -> None:
    assert set(_catalog("ru")) == set(_catalog("en"))


def test_static_cli_failures_are_catalogued() -> None:
    en = _catalog("en")
    missing = sorted(_static_failure_messages() - set(en))
    assert missing == []


def test_russian_catalog_is_not_an_english_copy() -> None:
    en = _catalog("en")
    ru = _catalog("ru")
    translated = sum(1 for key, value in ru.items() if value != en[key])
    assert translated == len(en)


def test_localize_respects_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = "no command given"
    monkeypatch.setenv("AI_STP_LOCALE", "ru")
    assert localize(sample) == _catalog("ru")[sample]
    monkeypatch.setenv("AI_STP_LOCALE", "en")
    assert localize(sample) == sample


#: How many `CliFailure` messages are still built by interpolation. Every one of
#: them is invisible to `localize`, which looks up the exact English source
#: string, so `AI_STP_LOCALE=ru` prints English for each. Cataloguing them as
#: rendered would create one key per value and translate nothing.
#:
#: A ceiling rather than a ban, because forty-six conversions in one change
#: would be a worse diff than the debt. It only goes **down**: the variable
#: belongs in `details`, where a caller already reads it, and the sentence
#: belongs in the catalog.
INTERPOLATED_FAILURE_CEILING = 46


def _interpolated_failure_sites() -> list[str]:
    found: list[str] = []
    for path in CLI_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Name) or func.id != "CliFailure" or len(node.args) < 2:
                continue
            message = node.args[1]
            if isinstance(message, ast.JoinedStr) and any(
                isinstance(part, ast.FormattedValue) for part in message.values
            ):
                found.append(f"{path.name}:{node.lineno}")
    return sorted(found)


def test_interpolated_failure_messages_only_shrink() -> None:
    """A message built by interpolation cannot be translated, and there are 46.

    `localize()` looks up the exact English source string, so an f-string
    message is never a catalog key and `AI_STP_LOCALE=ru` prints English for it.
    The four the issue named — the missing option in `attestations`, both
    unknown-configuration-key sites, and the invalid supplied value — now state
    one catalogued sentence and put the variable in `details`.

    This asserts the direction rather than the destination. Lower the ceiling
    with each conversion; never raise it.
    """
    sites = _interpolated_failure_sites()
    assert len(sites) <= INTERPOLATED_FAILURE_CEILING, (
        f"{len(sites)} interpolated CliFailure messages, ceiling is "
        f"{INTERPOLATED_FAILURE_CEILING}: {sites[:8]}"
    )
