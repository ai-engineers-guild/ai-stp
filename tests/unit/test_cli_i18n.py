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
            arg = node.args[1]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.add(arg.value)
    return found


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
