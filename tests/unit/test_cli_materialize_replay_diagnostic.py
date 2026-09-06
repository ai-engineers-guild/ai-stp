"""Locate replay differences by field path, never by fixture payload."""

from contextlib import closing
from typing import cast

import pytest
from tests.unit.test_cli_materialize_identity import (
    _apply,  # pyright: ignore[reportPrivateUsage]
    _plan,  # pyright: ignore[reportPrivateUsage]
    _source,  # pyright: ignore[reportPrivateUsage]
)

from ai_stp_cli.local import cache, component_materialize, revisions, versions
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


def test_exact_replay_matches_the_stored_passport(monkeypatch: pytest.MonkeyPatch) -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        preview = _plan(connection, _source(connection), "codex")
        first = _apply(connection, preview)

        def observe(body: dict[str, JsonValue]) -> PassportEnvelope:
            sealed = seal_envelope(body)
            record = versions.held(connection, first.stable_id, first.version)
            assert record is not None
            held = revisions.get(connection, record.revision_id)
            assert held is not None
            actual = cast(JsonValue, sealed.model_dump(mode="json"))
            stored = cast(JsonValue, held.envelope.model_dump(mode="json"))
            assert stored == actual, "replay mismatch fields: " + ",".join(_different(stored, actual))
            assert cache.digest_of(actual) == record.passport_digest, "version record digest"
            assert held.revision_id == sealed.revision_id, "version record revision"
            return sealed

        monkeypatch.setattr(component_materialize, "seal_envelope", observe)
        again = _apply(connection, preview)
        assert not again.created
        assert again.passport_digest == first.passport_digest
