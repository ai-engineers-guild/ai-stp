"""Locate a replay identity mismatch using field paths, never fixture payloads."""

from contextlib import closing
from typing import cast

import pytest
from tests.unit.test_cli_materialize_identity import (
    _apply,  # pyright: ignore[reportPrivateUsage]
    _plan,  # pyright: ignore[reportPrivateUsage]
    _source,  # pyright: ignore[reportPrivateUsage]
)

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import component_materialize
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports.envelope import PassportEnvelope, seal_envelope


def _different(left: JsonValue, right: JsonValue, path: str = "") -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        return [
            item
            for key in sorted(left.keys() | right.keys())
            for item in _different(left.get(key), right.get(key), f"{path}/{key}")
        ]
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return [
            item
            for index, (a, b) in enumerate(zip(left, right, strict=True))
            for item in _different(a, b, f"{path}/{index}")
        ]
    return [path] if left != right else []


def test_exact_replay_has_no_unexplained_identity_difference(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[JsonValue] = []

    def observe(body: dict[str, JsonValue]) -> PassportEnvelope:
        sealed = seal_envelope(body)
        seen.append(cast(JsonValue, sealed.model_dump(mode="json")))
        return sealed

    monkeypatch.setattr(component_materialize, "seal_envelope", observe)
    with closing(open_registry(configured_path(), create=True)) as connection:
        preview = _plan(connection, _source(connection), "codex")
        _apply(connection, preview)
        try:
            _apply(connection, preview)
        except CliFailure:
            assert len(seen) == 2
            pytest.fail("replay mismatch fields: " + ",".join(_different(seen[0], seen[1])))
