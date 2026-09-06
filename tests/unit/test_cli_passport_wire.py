"""Stored passport bytes stay the published document; the model does not invent fields."""

from __future__ import annotations

from contextlib import closing

from tests.unit.test_cli_setup_recast import (
    CLAUDE_BYTES,
    _release_component,  # pyright: ignore[reportPrivateUsage]
)

from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_passports.versions import ComponentVersionPassport


def test_current_component_passport_round_trips_its_digest() -> None:
    from ai_stp_cli.local import cache, component_passports

    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="instruction",
            harness_id="claude-code",
            payload=CLAUDE_BYTES,
            managed_path="CLAUDE.md",
        )
        passport = component_passports.version_passport(connection, member[0], member[1])
        dumped = passport.model_dump(mode="json")
        again = ComponentVersionPassport.model_validate(dumped)
        assert cache.digest_of(passport.model_dump(mode="json")) == cache.digest_of(
            again.model_dump(mode="json")
        )


def test_a_legacy_flat_passport_is_kept_as_stored_bytes() -> None:
    """HTTP overlays stored bytes; the CLI parser must not fabricate adaptations."""
    stored = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": "component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "name": "legacy",
        "component_type": "instruction",
    }
    # A legacy document is not a current ComponentVersionPassport. The stored
    # overlay keeps the original keys instead of filling later defaults.
    assert "adaptations" not in stored
    assert stored["component_type"] == "instruction"
