"""Local component draft enrichment is safe, causal and publication-aware."""

import json
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from ai_stp_cli.commands import component as command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    component_passports,
    components,
    content,
    impact,
    revisions,
    versions,
)
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.component_passport import ComponentPassportPatch
from ai_stp_contracts.machine_help import ComponentQualityDimension
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_passports import verify_revision_id

CREATED = "2026-08-10T10:00:00.000Z"
COMMIT = "a" * 40


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _fact(value: JsonValue) -> dict[str, JsonValue]:
    return {
        "value": value,
        "origin": "observed",
        "confirmation": "none",
        "observed_at": CREATED,
    }


def _draft(connection: sqlite3.Connection) -> revisions.StoredRevision:
    payload = b"# component\n"
    content.put(connection, payload, at=CREATED)
    stable_id = new_id("component")
    facts: dict[str, JsonValue] = {
        "component_type": _fact("skill"),
        "harness_id": _fact("codex"),
        "scope": _fact("project"),
        "source_path": _fact("skills/component"),
        "source_repository": _fact(""),
        "source_revision": _fact(""),
        "source_subpath": _fact(""),
        "source_package_name": _fact(""),
        "source_package_version": _fact(""),
        "source_name": _fact("component"),
        "content_format": _fact("ai-stp-component-file/1"),
        "content_digest": _fact(digest_bytes("ai-stp:artifact:v1", payload)),
        "byte_length": _fact(len(payload)),
    }
    return revisions.commit(
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
    )


def test_suggestions_copy_only_an_explicit_manifest_section_and_never_write(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    project = tmp_path / "repository"
    skill = project / "skills" / "ai-repo-safety"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# AI repository safety\n", encoding="utf-8")
    (skill / "pyproject.toml").write_text(
        """
[tool.ai-stp.component]
name = "ai-repo-safety"
description = "Checks a repository before an agent changes it."
tags = ["security"]
harness_id = "codex"
component_type = "skill"
projection_kind = "native_files"
entry_points = ["SKILL.md"]
runtime_requirements = ["python>=3.12"]
provides_capabilities = ["repository.safety"]
requires_authorization = "none"
requires_credentials = false

[tool.ai-stp.component.license]
spdx_id = "MIT"
redistribution_allowed = true

[tool.ai-stp.component.permissions]
filesystem = ["repository:read"]
network = []
process = []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    found = next(item for item in components.discover(project=project) if item.absolute == skill)
    stored = components.adopt(registry, found, device_id="device_test")
    before = registry.total_changes

    answer = component_passports.suggest(registry, stored.stable_id)

    assert answer.revision_id == stored.revision_id
    assert registry.total_changes == before
    proposed = {item.field: item for item in answer.facts}
    assert proposed["name"].value == "ai-repo-safety"
    assert proposed["runtime_requirements"].value == ["python>=3.12"]
    assert proposed["provides_capabilities"].value == ["repository.safety"]
    assert proposed["requires_authorization"].value == "none"
    assert proposed["license"].value == {
        "spdx_id": "MIT",
        "redistribution_allowed": True,
    }
    assert proposed["name"].source_refs == ("artifact:pyproject.toml",)
    assert "source" in answer.unresolved_fields
    assert "requires_components" in answer.unresolved_fields


def test_suggestions_use_only_complete_exact_source_provenance(
    registry: sqlite3.Connection,
) -> None:
    stored = _draft(registry)
    document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
    facts = cast(dict[str, JsonValue], document["facts"])
    facts.update(
        {
            "source_repository": _fact("https://github.com/example/component"),
            "source_revision": _fact(COMMIT),
            "source_subpath": _fact("skills/component"),
        }
    )
    document.pop("revision_id")
    document["facts"] = facts
    document["parent_revision_ids"] = [stored.revision_id]
    child = revisions.commit(registry, document, device_id="device_test")

    answer = component_passports.suggest(registry, child.stable_id)

    source = next(item for item in answer.facts if item.field == "source")
    assert source.value == {
        "repository": "https://github.com/example/component",
        "commit": COMMIT,
        "path": "skills/component",
    }
    assert source.source_refs == ("adopted:exact-source",)


def test_suggestions_do_not_infer_component_facts_from_ordinary_package_metadata(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    project = tmp_path / "repository"
    skill = project / "skills" / "ordinary"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Ordinary\n", encoding="utf-8")
    (skill / "package.json").write_text(
        json.dumps(
            {
                "name": "must-not-be-a-passport-name",
                "license": "MIT",
                "dependencies": {"octokit": "1.0.0"},
            }
        ),
        encoding="utf-8",
    )
    found = next(item for item in components.discover(project=project) if item.absolute == skill)
    stored = components.adopt(registry, found, device_id="device_test")

    answer = component_passports.suggest(registry, stored.stable_id)

    assert answer.facts == ()
    assert {"name", "license", "requires_authorization"} <= set(answer.unresolved_fields)


def test_suggestions_refuse_unknown_invalid_and_conflicting_manifest_facts(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    project = tmp_path / "repository"
    skill = project / "skills" / "conflicting"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Conflicting\n", encoding="utf-8")
    pyproject = skill / "pyproject.toml"
    package = skill / "package.json"
    pyproject.write_text(
        '[tool.ai-stp.component]\nname = "first"\n',
        encoding="utf-8",
    )
    package.write_text(
        json.dumps({"ai-stp": {"component": {"name": "second"}}}),
        encoding="utf-8",
    )
    found = next(item for item in components.discover(project=project) if item.absolute == skill)
    stored = components.adopt(registry, found, device_id="device_test")
    with pytest.raises(CliFailure) as conflicting:
        component_passports.suggest(registry, stored.stable_id)
    assert conflicting.value.code == "AI_STP_CONFLICT"

    package.write_text(json.dumps({"ai-stp": {"component": {"unknown": True}}}), encoding="utf-8")
    replacement = components.adopt(
        registry,
        next(item for item in components.discover(project=project) if item.absolute == skill),
        device_id="device_test",
    )
    with pytest.raises(CliFailure) as unknown:
        component_passports.suggest(registry, replacement.stable_id)
    assert unknown.value.code == "AI_STP_VALIDATION_ERROR"
    assert unknown.value.details["fields"] == "unknown"

    package.write_text(json.dumps({"ai-stp": {"component": {"tags": []}}}), encoding="utf-8")
    invalid = components.adopt(
        registry,
        next(item for item in components.discover(project=project) if item.absolute == skill),
        device_id="device_test",
    )
    with pytest.raises(CliFailure) as malformed:
        component_passports.suggest(registry, invalid.stable_id)
    assert malformed.value.code == "AI_STP_VALIDATION_ERROR"
    assert malformed.value.details["field"] == "tags"


def _complete_patch() -> ComponentPassportPatch:
    return ComponentPassportPatch.model_validate(
        {
            "name": "component",
            "description": "A deterministic component.",
            "tags": ["quality"],
            "source": {
                "repository": "https://github.com/example/component",
                "commit": COMMIT,
                "path": "skills/component",
            },
            "harness_id": "codex",
            "component_type": "skill",
            "projection_kind": "native_files",
            "license": {"spdx_id": "MIT", "redistribution_allowed": True},
            "managed_paths": ["skills/component/SKILL.md"],
            "entry_points": ["SKILL.md"],
            "runtime_requirements": ["codex>=1"],
            "harness_variants": ["native"],
            "supported_harness_versions": [">=1"],
        }
    )


@pytest.mark.parametrize(
    ("component_type", "surface"),
    [
        ("instruction", "managed_paths"),
        ("skill", "entry_points"),
        ("mcp", "native_ids"),
        ("hook", "native_ids"),
        ("command", "managed_paths"),
        ("agent", "entry_points"),
        ("plugin", "native_ids"),
        ("setting", "managed_paths"),
    ],
)
def test_quality_profiles_cover_every_component_type_without_changing_the_registry(
    registry: sqlite3.Connection, component_type: str, surface: str
) -> None:
    stored = _draft(registry)
    document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
    facts = cast(dict[str, JsonValue], document["facts"])
    facts.update(
        {
            "component_type": _fact(component_type),
            "name": _fact("quality component"),
            "description": _fact("A deterministic component with an explicit boundary."),
            "source": _fact(
                {
                    "repository": "https://github.com/example/component",
                    "commit": COMMIT,
                    "path": "skills/component",
                }
            ),
            "tags": _fact(["quality"]),
            "license": _fact({"spdx_id": "MIT", "redistribution_allowed": True}),
            "projection_kind": _fact("native_files"),
            "permissions": _fact({"filesystem": [], "network": [], "process": []}),
            "requires_credentials": _fact(False),
            "requires_authorization": _fact("none"),
            surface: _fact(["component-entry"]),
        }
    )
    if component_type == "skill":
        facts.pop("source")
        facts.update(
            {
                "source_repository": _fact("https://github.com/example/component"),
                "source_revision": _fact(COMMIT),
                "source_subpath": _fact("skills/component"),
            }
        )
    document.pop("revision_id")
    document["facts"] = facts
    document["parent_revision_ids"] = [stored.revision_id]
    current = revisions.commit(registry, document, device_id="device_test")
    before = registry.total_changes

    report = component_passports.evaluate_quality(registry, current.stable_id)

    assert registry.total_changes == before
    assert report.component_type == component_type
    assert [item.name for item in report.dimensions] == [
        "safety",
        "clarity",
        "reusability",
        "completeness",
        "actionability",
    ]
    assert all(check.passed for dimension in report.dimensions for check in dimension.checks)


def test_quality_hints_are_informational_and_do_not_hide_publication_blockers(
    registry: sqlite3.Connection,
) -> None:
    stored = _draft(registry)

    answer = command.passport_quality({"id": stored.stable_id}).payload
    readiness = component_passports.validate_for_publication(registry, stored.stable_id)

    assert answer.informational_only is True
    assert answer.affects_publication_readiness is False
    assert answer.affects_component_verified is False
    assert answer.affects_trust_lane is False
    assert answer.component_type == "skill"
    assert any(item.status == "hint" for item in answer.dimensions)
    assert readiness.ready is False
    assert "name" in readiness.missing_fields
    assert all(
        check.status in {"passed", "hint"} for item in answer.dimensions for check in item.checks
    )


def test_quality_dimension_cannot_claim_passed_over_a_hint() -> None:
    with pytest.raises(ValidationError, match="disagrees"):
        ComponentQualityDimension.model_validate(
            {
                "dimension": "safety",
                "status": "passed",
                "checks": [
                    {
                        "code": "declared_permissions",
                        "status": "hint",
                        "fields": ["permissions"],
                        "message": "Declare permissions.",
                    }
                ],
            }
        )


def test_patch_loader_is_closed_bounded_and_never_echoes_secret_values(tmp_path: Path) -> None:
    valid = tmp_path / "passport.json"
    valid.write_text(
        json.dumps(_complete_patch().model_dump(mode="json", exclude_unset=True)),
        encoding="utf-8",
    )
    assert component_passports.load_patch(valid).name == "component"

    secret_value = "must-never-appear"
    valid.write_text(json.dumps({"nested": {"access_token": secret_value}}), encoding="utf-8")
    with pytest.raises(CliFailure) as raised:
        component_passports.load_patch(valid)
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert secret_value not in str(raised.value)

    target = tmp_path / "target.json"
    target.write_text('{"name":"linked"}', encoding="utf-8")
    linked = tmp_path / "linked.json"
    linked.symlink_to(target)
    with pytest.raises(CliFailure, match="bounded regular file"):
        component_passports.load_patch(linked)


def test_the_patch_loader_names_the_exact_refusal_for_every_malformed_document(
    tmp_path: Path,
) -> None:
    """Each way a patch can be wrong has its own answer, not one shared failure."""
    with pytest.raises(CliFailure) as absent:
        component_passports.load_patch(tmp_path / "absent.json")
    assert absent.value.code == "AI_STP_NOT_FOUND"

    directory = tmp_path / "directory.json"
    directory.mkdir()
    with pytest.raises(CliFailure, match="bounded regular file"):
        component_passports.load_patch(directory)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (component_passports.MAX_PATCH_BYTES + 1))
    with pytest.raises(CliFailure, match="bounded regular file"):
        component_passports.load_patch(oversized)

    document = tmp_path / "patch.json"
    document.write_text("{not json", encoding="utf-8")
    with pytest.raises(CliFailure, match="canonical JSON"):
        component_passports.load_patch(document)

    document.write_text('["name"]', encoding="utf-8")
    with pytest.raises(CliFailure, match="must be a JSON object"):
        component_passports.load_patch(document)

    document.write_text('{"harness_id": "not-a-harness"}', encoding="utf-8")
    with pytest.raises(CliFailure) as rejected:
        component_passports.load_patch(document)
    assert rejected.value.code == "AI_STP_VALIDATION_ERROR"
    assert "harness_id" in str(rejected.value.details)

    document.write_text("{}", encoding="utf-8")
    with pytest.raises(CliFailure, match="is empty"):
        component_passports.load_patch(document)


def _load_patch_while(
    document: Path, monkeypatch: pytest.MonkeyPatch, change: Callable[[], None]
) -> CliFailure:
    """Run the loader with `change` applied between its size check and its read."""
    opened = os.open

    def interfere(path: object, flags: int, *rest: int) -> int:
        monkeypatch.undo()
        change()
        return opened(cast(str, path), flags, *rest)

    monkeypatch.setattr("ai_stp_cli.local.component_passports.os.open", interfere)
    with pytest.raises(CliFailure) as raised:
        component_passports.load_patch(document)
    return raised.value


def test_the_patch_loader_refuses_a_document_that_changed_after_it_was_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The size that was accepted has to describe the bytes that are read."""
    document = tmp_path / "patch.json"
    document.write_text('{"name": "component"}', encoding="utf-8")
    replacement = tmp_path / "replacement.json"
    replacement.write_text('{"name": "replaced"}', encoding="utf-8")

    def replace() -> None:
        document.unlink()
        replacement.rename(document)

    assert _load_patch_while(document, monkeypatch, replace).code == "AI_STP_CONFLICT"

    document.write_text('{"name": "component"}', encoding="utf-8")

    def grow() -> None:
        with document.open("ab") as stream:
            stream.write(b" " * (component_passports.MAX_PATCH_BYTES + 1))

    assert "byte limit" in str(_load_patch_while(document, monkeypatch, grow))


def test_the_passport_commands_refuse_before_they_open_the_registry(tmp_path: Path) -> None:
    """A missing identifier or an unnamed precondition never reaches local state."""
    for handler in (command.passport_show, command.passport_update, command.passport_validate):
        with pytest.raises(CliFailure, match="stable id is required"):
            handler({})

    stable_id = new_id("component")
    with pytest.raises(CliFailure, match="revision must be named"):
        command.passport_update({"id": stable_id})
    with pytest.raises(CliFailure, match="patch path is required"):
        command.passport_update({"id": stable_id, "expected-revision": "revision_test"})

    # `--expected-revision` is the confirmation and there is no flag beside it:
    # a child revision leaves its parent standing, so `ADR-0118` leaves the act
    # inside the task's authority while the exact revision still has to be
    # named. Refusal now comes from the patch that is not there, having passed
    # every argument check above.
    with pytest.raises(CliFailure) as refused:
        command.passport_update(
            {
                "id": stable_id,
                "expected-revision": "revision_test",
                "from": str(tmp_path / "patch.json"),
            }
        )
    assert refused.value.code == "AI_STP_NOT_FOUND"

    # `--for-publication` names the only profile and is no longer demanded;
    # the first refusal is the registry that is not there.
    with pytest.raises(CliFailure, match="registry does not exist"):
        command.passport_validate({"id": stable_id})


def test_the_passport_commands_read_the_head_and_report_its_publication_blockers(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Show, update and validate agree on one head across three separate calls."""
    original = _draft(registry)

    missing = command.passport_validate({"id": original.stable_id, "for-publication": True})
    assert not missing.payload.ready
    assert "license" in missing.payload.missing_fields

    patch = tmp_path / "patch.json"
    patch.write_text(
        json.dumps(_complete_patch().model_dump(mode="json", exclude_unset=True)),
        encoding="utf-8",
    )
    updated = command.passport_update(
        {
            "id": original.stable_id,
            "expected-revision": original.revision_id,
            "from": str(patch),
            "confirm": True,
        }
    )
    assert updated.payload.revision_id != original.revision_id

    shown = command.passport_show({"id": original.stable_id})
    assert shown.payload.revision_id == updated.payload.revision_id

    ready = command.passport_validate({"id": original.stable_id, "for-publication": True})
    assert ready.payload.ready
    assert ready.payload.missing_fields == []
    assert ready.payload.invalid_fields == []


def test_impact_loads_a_released_draft_shaped_passport_instead_of_refusing_it(
    registry: sqlite3.Connection,
) -> None:
    """A version released from a draft is loadable by the graph that reads it.

    Two stored shapes exist. A first-party corpus component is stored as a
    complete public passport; a component adopted from a native layout is stored
    as the draft it was adopted into, with its digest, length and source in
    `facts` rather than in an `artifact` block.

    `impact._component` validated the stored document directly, which only ever
    worked for the first shape. On the second it raised `a recorded component
    passport is invalid` carrying no field and no next action, so `select
    impact`, `select blast-radius` and `eval` all refused a setup that had
    already passed propose, confirm, bundle, graph and reports (`#385`).
    """
    original = _draft(registry)
    enriched = component_passports.update(
        registry,
        original.stable_id,
        original.revision_id,
        _complete_patch(),
        device_id="device_test",
    )
    document = cast(dict[str, JsonValue], enriched.envelope.model_dump(mode="json"))
    versions.record(
        registry,
        stable_id=original.stable_id,
        version="1.0",
        passport_digest=digest_canonical("ai-stp:passport:v1", document),
        revision_id=enriched.revision_id,
        at=CREATED,
    )

    # The loader is private and reached directly on purpose: the public entries
    # are `selection_report` and `blast_radius`, and both need a whole setup
    # graph to say anything about one component's passport. Suppressed the way
    # the rest of the suite does it.
    coordinate, facts, _payload = impact._component(  # pyright: ignore[reportPrivateUsage]
        registry, original.stable_id, "1.0", None
    )

    assert coordinate.version == "1.0"
    assert facts.component_type == "skill"
    assert facts.artifact_digest.startswith("sha256:")


def test_a_publication_passport_is_built_from_the_exact_released_revision(
    registry: sqlite3.Connection,
) -> None:
    original = _draft(registry)
    enriched = component_passports.update(
        registry,
        original.stable_id,
        original.revision_id,
        _complete_patch(),
        device_id="device_test",
    )
    document = cast(dict[str, JsonValue], enriched.envelope.model_dump(mode="json"))
    versions.record(
        registry,
        stable_id=original.stable_id,
        version="1.0",
        passport_digest=digest_canonical("ai-stp:passport:v1", document),
        revision_id=enriched.revision_id,
        at=CREATED,
    )
    changed = component_passports.update(
        registry,
        original.stable_id,
        enriched.revision_id,
        ComponentPassportPatch(name="later-draft-name"),
        device_id="device_test",
    )

    passport = component_passports.version_passport(registry, original.stable_id, "1.0")

    assert changed.revision_id != enriched.revision_id
    assert passport.name != "later-draft-name"
    assert passport.version == "1.0"
    assert passport.visibility == "public"
    assert passport.parent_revision_ids == []
    assert passport.artifact.digest == document["facts"]["content_digest"]["value"]  # type: ignore[index]
    # The digest has to describe the passport as the server will see it. The
    # server validates first and then hashes `model_dump(mode="json")`, and
    # validation fills defaults the candidate never carried, so a digest taken
    # before validation describes a document that no longer exists. That was
    # `#381`: `publication plan` answered `400 passport invalid for
    # publication` while the local `validate --for-publication` stayed green,
    # because the two were checking different things.
    assert verify_revision_id(passport)
    with pytest.raises(CliFailure) as absent:
        component_passports.version_passport(registry, original.stable_id, "1.1")
    assert absent.value.code == "AI_STP_NOT_FOUND"


def test_the_passport_commands_separate_an_absent_component_from_a_wrong_kind(
    registry: sqlite3.Connection,
) -> None:
    """Naming a setup is a different mistake from naming nothing at all."""
    unknown = new_id("component")
    with pytest.raises(CliFailure) as absent:
        command.passport_show({"id": unknown})
    assert absent.value.code == "AI_STP_NOT_FOUND"

    with pytest.raises(CliFailure) as unvalidatable:
        component_passports.validate_for_publication(registry, unknown)
    assert unvalidatable.value.code == "AI_STP_NOT_FOUND"

    setup = revisions.commit(
        registry,
        {
            "schema_version": 1,
            "kind": "setup",
            "stable_id": new_id("setup"),
            "owner_id": new_id("account"),
            "created_at": CREATED,
            "visibility": "private",
            "parent_revision_ids": [],
            "facts": {"name": _fact("a setup")},
        },
        device_id="device_test",
    )
    with pytest.raises(CliFailure) as wrong_kind:
        command.passport_show({"id": setup.stable_id})
    assert wrong_kind.value.code == "AI_STP_VALIDATION_ERROR"

    with pytest.raises(CliFailure) as validated:
        component_passports.validate_for_publication(registry, setup.stable_id)
    assert validated.value.code == "AI_STP_VALIDATION_ERROR"


def test_publication_validation_refuses_a_source_outside_the_declared_forge(
    registry: sqlite3.Connection,
) -> None:
    """A passport with every field present is still unpublishable off GitHub."""
    payload = b"# component\n"
    facts: dict[str, JsonValue] = {
        "name": _fact("component"),
        "description": _fact("A deterministic component."),
        "tags": _fact(["quality"]),
        "harness_id": _fact("codex"),
        "component_type": _fact("skill"),
        "projection_kind": _fact("native_files"),
        "license": _fact({"spdx_id": "MIT", "redistribution_allowed": True}),
        "content_digest": _fact(digest_bytes("ai-stp:artifact:v1", payload)),
        "byte_length": _fact(len(payload)),
        "source_repository": _fact("https://example.com/component"),
        "source_revision": _fact(COMMIT),
        "source_subpath": _fact("skills/component"),
    }
    stored = revisions.commit(
        registry,
        {
            "schema_version": 1,
            "kind": "component",
            "stable_id": new_id("component"),
            "owner_id": new_id("account"),
            "created_at": CREATED,
            "visibility": "private",
            "parent_revision_ids": [],
            "facts": facts,
        },
        device_id="device_test",
    )

    readiness = component_passports.validate_for_publication(registry, stored.stable_id)
    assert not readiness.ready
    assert readiness.missing_fields == ()
    assert "source.repository" in readiness.invalid_fields


def test_update_creates_one_causal_revision_and_refuses_a_stale_patch(
    registry: sqlite3.Connection,
) -> None:
    original = _draft(registry)
    changed = component_passports.update(
        registry,
        original.stable_id,
        original.revision_id,
        _complete_patch(),
        device_id="device_test",
    )

    assert changed.revision_id != original.revision_id
    assert changed.parents == (original.revision_id,)
    assert revisions.head(registry, original.stable_id) == changed
    facts = changed.envelope.model_dump(mode="json")["facts"]
    assert facts["name"]["origin"] == "declared"
    assert facts["name"]["confirmation"] == "user_confirmed"

    replay = component_passports.update(
        registry,
        changed.stable_id,
        changed.revision_id,
        _complete_patch(),
        device_id="device_test",
    )
    assert replay.revision_id == changed.revision_id

    with pytest.raises(CliFailure) as raised:
        component_passports.update(
            registry,
            original.stable_id,
            original.revision_id,
            _complete_patch(),
            device_id="device_test",
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_publication_validation_reports_all_missing_fields_then_accepts_exact_source(
    registry: sqlite3.Connection,
) -> None:
    original = _draft(registry)
    incomplete = component_passports.validate_for_publication(registry, original.stable_id)
    assert not incomplete.ready
    assert set(incomplete.missing_fields) == {
        "description",
        "license",
        "name",
        "projection_kind",
        "source",
        "tags",
    }

    changed = component_passports.update(
        registry,
        original.stable_id,
        original.revision_id,
        _complete_patch(),
        device_id="device_test",
    )
    ready = component_passports.validate_for_publication(registry, original.stable_id)
    assert ready.ready
    assert ready.revision_id == changed.revision_id
    assert ready.missing_fields == ()
    assert ready.invalid_fields == ()


def test_a_released_revision_remains_exact_after_the_draft_advances(
    registry: sqlite3.Connection,
) -> None:
    original = _draft(registry)
    released_digest = digest_canonical(
        "ai-stp:passport:v1", cast(JsonValue, original.envelope.model_dump(mode="json"))
    )
    recorded = versions.record(
        registry,
        stable_id=original.stable_id,
        version="1.0",
        passport_digest=released_digest,
        revision_id=original.revision_id,
        at=CREATED,
    )
    component_passports.update(
        registry,
        original.stable_id,
        original.revision_id,
        _complete_patch(),
        device_id="device_test",
    )

    assert versions.held(registry, original.stable_id, "1.0") == recorded
    assert revisions.get(registry, original.revision_id) == original


def test_a_publication_refusal_names_the_fields_it_counted(
    registry: sqlite3.Connection,
) -> None:
    """Counting the blockers and hiding them costs the operator a round trip.

    The refusal reported `fields: "5"` and nothing else. Following its next
    action does answer — `validate --for-publication` names every missing
    field — but the field paths are already in hand at the point of refusal,
    inside the very `ValidationError` whose length was reported. Observed while
    driving the publication chain against the deployed catalogue.
    """
    original = _draft(registry)
    versions.record(
        registry,
        stable_id=original.stable_id,
        version="1.0",
        passport_digest=digest_canonical(
            "ai-stp:passport:v1",
            cast(dict[str, JsonValue], original.envelope.model_dump(mode="json")),
        ),
        revision_id=original.revision_id,
        at=CREATED,
    )

    with pytest.raises(CliFailure) as refused:
        component_passports.version_passport(registry, original.stable_id, "1.0")

    details = refused.value.details
    assert refused.value.message == "the released component is not ready for publication"
    named = str(details.get("fields", ""))
    assert named, details
    # Not a bare count: the paths themselves, so the next step is obvious.
    assert not named.isdigit(), f"the refusal still reports only a count: {named!r}"
    assert "name" in named, named
