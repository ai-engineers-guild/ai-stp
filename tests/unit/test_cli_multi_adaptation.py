"""One logical component can freeze two native adaptations (A12 / ADR-0143)."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import authoring, component_passports, content, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_passports.versions import adaptation_for

CREATED = "2026-09-05T12:00:00.000Z"
COMMIT = "a" * 40
CLAUDE_BYTES = b"# Claude instruction\n"
CODEX_BYTES = b"# Codex instruction\n"


def _fact(value: JsonValue) -> dict[str, JsonValue]:
    return {
        "value": value,
        "origin": "observed",
        "confirmation": "none",
        "observed_at": CREATED,
    }


def test_add_adaptation_renders_a_second_native_projection(tmp_path: Path) -> None:
    output = tmp_path / "review-kit"
    plan, files = authoring.scaffold_plan(
        component_type="instruction",
        name="review-kit",
        language="none",
        harness_variant="claude-code",
        output=output,
    )
    authoring.apply_scaffold(plan, files, expected_digest=plan.plan_digest)
    assert (output / "projections" / "claude-code" / "CLAUDE.md").is_file()
    assert not (output / "projections" / "codex").exists()

    written = authoring.add_adaptation(output, "codex")
    assert any(path.startswith("projections/codex/") for path in written)
    assert (output / "projections" / "codex" / "AGENTS.md").is_file()
    claude = (output / "projections" / "claude-code" / "CLAUDE.md").read_bytes()
    codex = (output / "projections" / "codex" / "AGENTS.md").read_bytes()
    assert claude != b""
    assert codex != b""
    descriptor = json.loads((output / ".ai-stp-template.json").read_text(encoding="utf-8"))
    assert descriptor["harness_variant"] == "claude-code"
    assert "codex" in descriptor["additional_harnesses"]
    patch = json.loads((output / "component-passport.json").read_text(encoding="utf-8"))
    assert "claude-code" in patch["harness_variants"]
    assert "codex" in patch["harness_variants"]


def test_add_adaptation_refuses_a_duplicate_or_unsupported_harness(tmp_path: Path) -> None:
    output = tmp_path / "review-kit"
    plan, files = authoring.scaffold_plan(
        component_type="instruction",
        name="review-kit",
        language="none",
        harness_variant="claude-code",
        output=output,
    )
    authoring.apply_scaffold(plan, files, expected_digest=plan.plan_digest)
    try:
        authoring.add_adaptation(output, "claude-code")
        raise AssertionError("duplicate harness was accepted")
    except CliFailure as error:
        assert "already" in error.message
    try:
        authoring.add_adaptation(output, "portable")
        raise AssertionError("portable was accepted as an adaptation")
    except CliFailure as error:
        assert "concrete" in error.message


def test_release_freezes_two_adaptations_and_keeps_the_previous_version(tmp_path: Path) -> None:
    claude_digest = digest_bytes("ai-stp:artifact:v1", CLAUDE_BYTES)
    codex_digest = digest_bytes("ai-stp:artifact:v1", CODEX_BYTES)
    with closing(open_registry(configured_path(), create=True)) as connection:
        content.put(connection, CLAUDE_BYTES, at=CREATED)
        content.put(connection, CODEX_BYTES, at=CREATED)
        stable_id = new_id("component")
        facts: dict[str, JsonValue] = {
            "name": _fact("review-kit"),
            "description": _fact("A completed review instruction."),
            "tags": _fact(["quality"]),
            "source": _fact(
                {
                    "repository": "https://github.com/example/review-kit",
                    "commit": COMMIT,
                    "path": "instructions/review-kit",
                }
            ),
            "harness_id": _fact("claude-code"),
            "component_type": _fact("instruction"),
            "projection_kind": _fact("native_files"),
            "scope": _fact("global"),
            "license": _fact({"spdx_id": "MIT", "redistribution_allowed": True}),
            "content_format": _fact("ai-stp-component-file/1"),
            "content_digest": _fact(claude_digest),
            "byte_length": _fact(len(CLAUDE_BYTES)),
            "managed_paths": _fact(["CLAUDE.md"]),
            "harness_variants": _fact(["claude-code", "codex"]),
            "adaptation_contents": _fact(
                [
                    {
                        "harness_id": "claude-code",
                        "content_digest": claude_digest,
                        "content_format": "ai-stp-component-file/1",
                        "managed_paths": ["CLAUDE.md"],
                        "scope": "global",
                        "projection_kind": "native_files",
                    },
                    {
                        "harness_id": "codex",
                        "content_digest": codex_digest,
                        "content_format": "ai-stp-component-file/1",
                        "managed_paths": ["AGENTS.md"],
                        "scope": "global",
                        "projection_kind": "native_files",
                    },
                ]
            ),
        }
        from ai_stp_cli.local import revisions

        stored = revisions.commit(
            connection,
            {
                "schema_version": 1,
                "kind": "component",
                "stable_id": stable_id,
                "owner_id": new_id("account"),
                "created_at": CREATED,
                "visibility": "private",
                "parent_revision_ids": [],
                "facts": facts,
            },
            device_id="device_test",
            operation_id="op_test",
        )
        first, first_revision = component_passports.materialize_version_passport(
            connection, stored.stable_id, "1.0", device_id="device_test", at=CREATED
        )
        first_digest = digest_canonical(
            "ai-stp:passport:v1", cast(JsonValue, first.model_dump(mode="json"))
        )
        versions.record(
            connection,
            stable_id=stored.stable_id,
            version="1.0",
            passport_digest=first_digest,
            revision_id=first_revision,
            at=CREATED,
        )
        harnesses = {item.harness_id for item in first.adaptations}
        assert harnesses == {"claude-code", "codex"}
        claude = adaptation_for(first, "claude-code")
        codex = adaptation_for(first, "codex")
        assert {member.path for member in claude.scope_adaptations[0].members} == {"CLAUDE.md"}
        assert {member.path for member in codex.scope_adaptations[0].members} == {"AGENTS.md"}
        assert claude.adaptation_id != codex.adaptation_id

        changed = b"# Codex instruction changed\n"
        content.put(connection, changed, at=CREATED)
        changed_digest = digest_bytes("ai-stp:artifact:v1", changed)
        head = revisions.head(connection, stored.stable_id)
        assert head is not None
        dumped = cast(dict[str, JsonValue], head.envelope.model_dump(mode="json"))
        facts = cast(dict[str, JsonValue], dumped["facts"])
        contents = cast(dict[str, JsonValue], facts["adaptation_contents"])
        sources = cast(list[JsonValue], contents["value"])
        sources[1] = {
            "harness_id": "codex",
            "content_digest": changed_digest,
            "content_format": "ai-stp-component-file/1",
            "managed_paths": ["AGENTS.md"],
            "scope": "global",
            "projection_kind": "native_files",
        }
        child: dict[str, JsonValue] = {
            "schema_version": 1,
            "kind": "component",
            "stable_id": stored.stable_id,
            "owner_id": head.envelope.owner_id,
            "created_at": CREATED,
            "visibility": "private",
            "parent_revision_ids": [head.revision_id],
            "facts": facts,
        }
        revisions.commit(connection, child, device_id="device_test")
        second, second_revision = component_passports.materialize_version_passport(
            connection, stored.stable_id, "1.1", device_id="device_test", at=CREATED
        )
        versions.record(
            connection,
            stable_id=stored.stable_id,
            version="1.1",
            passport_digest=digest_canonical(
                "ai-stp:passport:v1", cast(JsonValue, second.model_dump(mode="json"))
            ),
            revision_id=second_revision,
            at=CREATED,
        )
        reloaded = component_passports.version_passport(connection, stored.stable_id, "1.0")
        assert (
            digest_canonical(
                "ai-stp:passport:v1", cast(JsonValue, reloaded.model_dump(mode="json"))
            )
            == first_digest
        )
        assert adaptation_for(second, "claude-code").adaptation_id == claude.adaptation_id
        assert adaptation_for(second, "codex").adaptation_id != codex.adaptation_id
        assert second.version == "1.1"
        assert reloaded.version == "1.0"
