"""Recast a complete setup onto another harness (SPEC-062)."""

from __future__ import annotations

from contextlib import closing
from typing import cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, component_passports, content, revisions, setup_recast, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.setup_versions import MemberRef, passport_content
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_passports import SetupVersionPassport, adaptation_for

CREATED = "2026-09-05T12:00:00.000Z"
COMMIT = "a" * 40
CLAUDE_BYTES = b"# Claude instruction\n"
CODEX_BYTES = b"# Codex instruction\n"
SETTING_BYTES = b'{"permissions":{"defaultMode":"acceptEdits"}}\n'
CURSOR_MCP = b'{"mcpServers":{"docs":{"command":"npx","args":["docs-mcp"]}}}\n'
CODEX_MCP = b'[docs]\ncommand = "npx"\nargs = ["docs-mcp"]\n'
DEVICE = "device_test"
OWNER = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _fact(value: JsonValue) -> dict[str, JsonValue]:
    return {
        "value": value,
        "origin": "observed",
        "confirmation": "none",
        "observed_at": CREATED,
    }


def _release_component(
    connection: object,
    *,
    component_type: str,
    harness_id: str,
    payload: bytes,
    managed_path: str,
    extra_adaptations: list[dict[str, JsonValue]] | None = None,
    declared_key: str = "",
) -> tuple[str, str, str]:
    digest = digest_bytes("ai-stp:artifact:v1", payload)
    content.put(connection, payload, at=CREATED)  # type: ignore[arg-type]
    stable_id = new_id("component")
    sources: list[JsonValue] = [
        {
            "harness_id": harness_id,
            "content_digest": digest,
            "content_format": "ai-stp-component-file/1",
            "managed_paths": [managed_path],
            "scope": "global",
            "projection_kind": "native_files",
            "declared_key": declared_key,
            "source_locator": f"{managed_path}#{declared_key}" if declared_key else "",
        }
    ]
    if extra_adaptations:
        sources.extend(extra_adaptations)
    facts: dict[str, JsonValue] = {
        "name": _fact("review-kit"),
        "description": _fact("A completed review component."),
        "tags": _fact(["quality"]),
        "source": _fact(
            {
                "repository": "https://github.com/example/review-kit",
                "commit": COMMIT,
                "path": "instructions/review-kit",
            }
        ),
        "harness_id": _fact(harness_id),
        "component_type": _fact(component_type),
        "projection_kind": _fact("native_files"),
        "scope": _fact("global"),
        "license": _fact({"spdx_id": "MIT", "redistribution_allowed": True}),
        "content_format": _fact("ai-stp-component-file/1"),
        "content_digest": _fact(digest),
        "byte_length": _fact(len(payload)),
        "managed_paths": _fact([managed_path]),
        "adaptation_contents": _fact(sources),
    }
    stored = revisions.commit(
        connection,  # type: ignore[arg-type]
        {
            "schema_version": 1,
            "kind": "component",
            "stable_id": stable_id,
            "owner_id": OWNER,
            "created_at": CREATED,
            "visibility": "private",
            "parent_revision_ids": [],
            "facts": facts,
        },
        device_id=DEVICE,
    )
    passport, revision_id = component_passports.materialize_version_passport(
        connection,  # type: ignore[arg-type]
        stored.stable_id,
        "1.0",
        device_id=DEVICE,
        at=CREATED,
    )
    passport_digest = digest_canonical(
        "ai-stp:passport:v1", cast(JsonValue, passport.model_dump(mode="json"))
    )
    versions.record(
        connection,  # type: ignore[arg-type]
        stable_id=stored.stable_id,
        version="1.0",
        passport_digest=passport_digest,
        revision_id=revision_id,
        at=CREATED,
    )
    return stored.stable_id, "1.0", passport_digest


def _record_setup(
    connection: object,
    *,
    harness_id: str,
    member: tuple[str, str, str],
) -> tuple[str, str]:
    setup_id = new_id("setup")
    passport = passport_content(
        connection,  # type: ignore[arg-type]
        stable_id=setup_id,
        version="1.0",
        owner_id=OWNER,
        project_id=new_id("project"),
        harness_id=harness_id,
        snapshot="sha256:" + "b" * 64,
        members=(MemberRef(*member),),
        at=CREATED,
    )
    stored = revisions.commit(connection, passport, device_id=DEVICE)  # type: ignore[arg-type]
    digest = cache.digest_of(cast(JsonValue, stored.envelope.model_dump(mode="json")))
    versions.record(
        connection,  # type: ignore[arg-type]
        stable_id=setup_id,
        version="1.0",
        passport_digest=digest,
        revision_id=stored.revision_id,
        at=CREATED,
    )
    return setup_id, digest


def test_recast_derives_an_instruction_and_records_provenance() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="instruction",
            harness_id="claude-code",
            payload=CLAUDE_BYTES,
            managed_path="CLAUDE.md",
        )
        source_id, source_digest = _record_setup(
            connection, harness_id="claude-code", member=member
        )
        setup_id = new_id("setup")
        preview = setup_recast.plan(
            connection,
            source_id=source_id,
            source_version="1.0",
            target_harness="codex",
            setup_id=setup_id,
            created_at=CREATED,
        )
        assert preview.complete
        assert preview.members[0].disposition == "derive"
        result = setup_recast.apply(
            connection,
            source_id=source_id,
            source_version="1.0",
            target_harness="codex",
            setup_id=setup_id,
            created_at=CREATED,
            expected_plan_digest=preview.plan_digest,
            device_id=DEVICE,
            owner_id=OWNER,
        )
        recorded = versions.held(connection, result.setup_id, "1.0")
        assert recorded is not None
        stored = revisions.get(connection, recorded.revision_id)
        assert stored is not None
        passport = SetupVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
        assert passport.harness_id == "codex"
        assert passport.ported_from is not None
        assert passport.ported_from.stable_id == source_id
        assert passport.ported_from.version == "1.0"
        assert source_id in passport.related_setup_ids
        source_held = versions.held(connection, source_id, "1.0")
        assert source_held is not None
        assert source_held.passport_digest == source_digest
        derived = component_passports.version_passport(
            connection, member[0], preview.members[0].target_version
        )
        assert {item.harness_id for item in derived.adaptations} == {"claude-code", "codex"}
        codex_paths = {
            item.path for item in adaptation_for(derived, "codex").scope_adaptations[0].members
        }
        assert codex_paths == {"AGENTS.md"}


def test_same_harness_recast_is_refused() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="instruction",
            harness_id="claude-code",
            payload=CLAUDE_BYTES,
            managed_path="CLAUDE.md",
        )
        source_id, _digest = _record_setup(connection, harness_id="claude-code", member=member)
        try:
            setup_recast.plan(
                connection,
                source_id=source_id,
                source_version="1.0",
                target_harness="claude-code",
                setup_id=new_id("setup"),
                created_at=CREATED,
            )
        except CliFailure as error:
            assert error.code == "AI_STP_VALIDATION_ERROR"
        else:
            raise AssertionError("same-harness recast was accepted")


def test_a_setting_blocks_recast_apply() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="setting",
            harness_id="claude-code",
            payload=SETTING_BYTES,
            managed_path="settings.json",
        )
        source_id, _digest = _record_setup(connection, harness_id="claude-code", member=member)
        setup_id = new_id("setup")
        preview = setup_recast.plan(
            connection,
            source_id=source_id,
            source_version="1.0",
            target_harness="codex",
            setup_id=setup_id,
            created_at=CREATED,
        )
        assert not preview.complete
        assert preview.members[0].disposition == "blocked"
        try:
            setup_recast.apply(
                connection,
                source_id=source_id,
                source_version="1.0",
                target_harness="codex",
                setup_id=setup_id,
                created_at=CREATED,
                expected_plan_digest=preview.plan_digest,
                device_id=DEVICE,
                owner_id=OWNER,
            )
        except CliFailure as error:
            assert error.code == "AI_STP_CONFLICT"
        else:
            raise AssertionError("incomplete recast was applied")


def test_an_existing_target_adaptation_is_reused() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        codex_digest = digest_bytes("ai-stp:artifact:v1", CODEX_BYTES)
        content.put(connection, CODEX_BYTES, at=CREATED)
        member = _release_component(
            connection,
            component_type="instruction",
            harness_id="claude-code",
            payload=CLAUDE_BYTES,
            managed_path="CLAUDE.md",
            extra_adaptations=[
                {
                    "harness_id": "codex",
                    "content_digest": codex_digest,
                    "content_format": "ai-stp-component-file/1",
                    "managed_paths": ["AGENTS.md"],
                    "scope": "global",
                    "projection_kind": "native_files",
                }
            ],
        )
        source_id, _digest = _record_setup(connection, harness_id="claude-code", member=member)
        preview = setup_recast.plan(
            connection,
            source_id=source_id,
            source_version="1.0",
            target_harness="codex",
            setup_id=new_id("setup"),
            created_at=CREATED,
        )
        assert preview.complete
        assert preview.members[0].disposition == "reuse"
        assert preview.members[0].target_version == "1.0"


def test_recast_derives_a_codex_mcp_setting_contribution() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="mcp",
            harness_id="cursor",
            payload=CURSOR_MCP,
            managed_path="mcp.json",
        )
        source_id, _digest = _record_setup(connection, harness_id="cursor", member=member)
        setup_id = new_id("setup")
        preview = setup_recast.plan(
            connection,
            source_id=source_id,
            source_version="1.0",
            target_harness="codex",
            setup_id=setup_id,
            created_at=CREATED,
        )
        assert preview.complete
        assert preview.members[0].disposition == "derive"
        result = setup_recast.apply(
            connection,
            source_id=source_id,
            source_version="1.0",
            target_harness="codex",
            setup_id=setup_id,
            created_at=CREATED,
            expected_plan_digest=preview.plan_digest,
            device_id=DEVICE,
            owner_id=OWNER,
        )
        derived = component_passports.version_passport(
            connection, member[0], preview.members[0].target_version
        )
        assert {item.harness_id for item in derived.adaptations} == {"cursor", "codex"}
        scope = adaptation_for(derived, "codex").scope_adaptations[0]
        assert scope.provider_component_kind == "setting"
        owned = scope.members[0]
        assert owned.path == "config.toml"
        assert owned.ownership == "contribution"
        assert owned.ownership_key == "mcp_servers"
        assert owned.content_artifact is not None
        payload = content.get(connection, owned.content_artifact.digest)
        assert b"docs" in payload
        assert b"npx" in payload
        assert result.setup_id == setup_id


def test_recast_derives_a_cursor_mcp_file_from_a_codex_contribution() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="mcp",
            harness_id="codex",
            payload=CODEX_MCP,
            managed_path="config.toml",
            declared_key="mcp_servers",
        )
        source_id, _digest = _record_setup(connection, harness_id="codex", member=member)
        setup_id = new_id("setup")
        preview = setup_recast.plan(
            connection,
            source_id=source_id,
            source_version="1.0",
            target_harness="cursor",
            setup_id=setup_id,
            created_at=CREATED,
        )
        assert preview.complete
        assert preview.members[0].disposition == "derive"
        setup_recast.apply(
            connection,
            source_id=source_id,
            source_version="1.0",
            target_harness="cursor",
            setup_id=setup_id,
            created_at=CREATED,
            expected_plan_digest=preview.plan_digest,
            device_id=DEVICE,
            owner_id=OWNER,
        )
        derived = component_passports.version_passport(
            connection, member[0], preview.members[0].target_version
        )
        scope = adaptation_for(derived, "cursor").scope_adaptations[0]
        owned = scope.members[0]
        assert owned.path == "mcp.json"
        assert owned.ownership == "whole"
        assert owned.content_artifact is not None
        payload = content.get(connection, owned.content_artifact.digest)
        assert b"mcpServers" in payload
        assert b"docs" in payload


def test_a_pi_mcp_plugin_package_blocks_recast() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="mcp",
            harness_id="cursor",
            payload=CURSOR_MCP,
            managed_path="mcp.json",
        )
        source_id, _digest = _record_setup(connection, harness_id="cursor", member=member)
        preview = setup_recast.plan(
            connection,
            source_id=source_id,
            source_version="1.0",
            target_harness="pi",
            setup_id=new_id("setup"),
            created_at=CREATED,
        )
        assert not preview.complete
        assert preview.members[0].disposition == "blocked"
        assert "plugin package" in preview.members[0].reason
