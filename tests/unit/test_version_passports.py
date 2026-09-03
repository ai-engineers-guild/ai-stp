"""Version passports: taxonomy, no setup variant axis, safe sources."""

from typing import cast

import pytest
from pydantic import ValidationError

from ai_stp_foundation import digest_canonical, new_id
from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports import (
    ArtifactRef,
    ComponentVersionPassport,
    GitSource,
    LicenseInfo,
    SetupVersionPassport,
    seal_adaptation,
    seal_envelope,
)

ARTIFACT = {"digest": digest_canonical("ai-stp:artifact:v1", {"bytes": 1}), "size_bytes": 128}
LICENSE = {"spdx_id": "MIT", "redistribution_allowed": True}
CREATED = "2026-08-05T10:00:00.000Z"


def _component(**overrides: JsonValue) -> dict[str, JsonValue]:
    adaptation = seal_adaptation(
        {
            "harness_id": "claude-code",
            "implementation_mode": "native",
            "source_artifact": None,
            "transform": None,
            "logical_component_type": "skill",
            "scope_adaptations": [
                {
                    "scope": "global",
                    "projection_format": "ai-stp-adaptation-projection/1",
                    "projection_artifact": dict(ARTIFACT),
                    "provider_component_kind": "skill",
                    "projection_kind": "native_files",
                    "required_surface": {
                        "profile_id": "claude/native-and-marketplace/1",
                        "profile_digest": ARTIFACT["digest"],
                        "bundle_format": "ai-stp-bundle/1",
                    },
                    "members": [
                        {
                            "path": "skills/pytest/SKILL.md",
                            "object_type": "file",
                            "mode": 420,
                            "content_artifact": dict(ARTIFACT),
                            "native_ids": ["pytest"],
                            "content_format": "commonmark_v1",
                            "ownership": "whole",
                            "write_semantics": "replace",
                            "withdrawal_semantics": "remove_path",
                        }
                    ],
                    "technical_support": "supported",
                }
            ],
        }
    )
    data: dict[str, JsonValue] = {
        "kind": "component",
        "stable_id": new_id("component"),
        "parent_revision_ids": [],
        "owner_id": new_id("account"),
        "created_at": CREATED,
        "name": "pytest-runner",
        "description": "Runs pytest and parses the report.",
        "version": "1.0",
        "tags": ["python", "tests"],
        "artifact": dict(ARTIFACT),
        "license": dict(LICENSE),
        "component_type": "skill",
        "origin_harness_id": "claude-code",
        "adaptations": [cast(JsonValue, adaptation.model_dump(mode="json"))],
    }
    data.update(overrides)
    return data


def _setup(**overrides: JsonValue) -> dict[str, JsonValue]:
    component_ref: dict[str, JsonValue] = {
        "stable_id": new_id("component"),
        "version": "1.0",
        "passport_digest": digest_canonical("ai-stp:passport:v1", {"c": 1}),
    }
    data: dict[str, JsonValue] = {
        "kind": "setup",
        "stable_id": new_id("setup"),
        "parent_revision_ids": [],
        "owner_id": new_id("account"),
        "created_at": CREATED,
        "name": "backend-setup",
        "description": "Backend role setup.",
        "version": "1.0",
        "tags": ["backend"],
        "artifact": dict(ARTIFACT),
        "harness_id": "codex",
        "license": dict(LICENSE),
        "purpose": "Backend development.",
        "target_role": "backend",
        "components": [component_ref],
    }
    data.update(overrides)
    return data


def test_component_passport_seals_with_taxonomy() -> None:
    sealed = seal_envelope(_component())
    passport = ComponentVersionPassport.model_validate(sealed.model_dump(mode="json"))
    assert passport.component_type == "skill"
    assert passport.adaptations[0].scope_adaptations[0].projection_kind == "native_files"


def test_immutable_version_passports_reject_draft_parents() -> None:
    parent = seal_envelope(_component()).revision_id
    with pytest.raises(ValidationError, match="immutable version snapshot"):
        ComponentVersionPassport.model_validate(
            seal_envelope(_component(parent_revision_ids=[parent])).model_dump(mode="json")
        )


def test_version_description_is_the_only_content_field_and_is_safe_markdown() -> None:
    accepted = ComponentVersionPassport.model_validate(
        seal_envelope(_component(description="**Runs** `pytest`.")).model_dump(mode="json")
    )
    assert accepted.description == "**Runs** `pytest`."
    assert "description_format" not in type(accepted).model_fields

    with pytest.raises(ValidationError, match="raw_html"):
        ComponentVersionPassport.model_validate(
            seal_envelope(_component(description="<script>x</script>")).model_dump(mode="json")
        )


def test_changing_only_the_description_changes_the_immutable_passport_digest() -> None:
    stable_id = new_id("component")
    owner_id = new_id("account")
    common: dict[str, JsonValue] = {"stable_id": stable_id, "owner_id": owner_id}
    first = seal_envelope(_component(**common, description="Initial description."))
    changed = seal_envelope(_component(**common, description="Revised description."))

    first_digest = digest_canonical("ai-stp:passport:v1", first.model_dump(mode="json"))
    changed_digest = digest_canonical("ai-stp:passport:v1", changed.model_dump(mode="json"))

    assert first_digest != changed_digest


def test_component_rejects_every_retired_flat_adaptation_field() -> None:
    for field, value in {
        "harness_id": "claude-code",
        "harness_ids": ["claude-code"],
        "managed_paths": ["skills/example"],
        "native_ids": ["example"],
        "projection_kind": "native_files",
        "supported_os": ["linux"],
        "variant_id": None,
    }.items():
        with pytest.raises(ValidationError, match="no flat adaptation fields"):
            ComponentVersionPassport.model_validate(
                seal_envelope(_component()).model_dump(mode="json") | {field: value}
            )


def test_marketplace_is_not_a_component_type() -> None:
    with pytest.raises(ValidationError):
        ComponentVersionPassport.model_validate(
            seal_envelope(_component()).model_dump(mode="json") | {"component_type": "marketplace"}
        )


def test_setup_rejects_variant_even_as_preserved_extra() -> None:
    data = _setup()
    sealed_data = seal_envelope(data).model_dump(mode="json")
    sealed_data["variant_id"] = new_id("variant")
    with pytest.raises(ValidationError):
        SetupVersionPassport.model_validate(sealed_data)


def test_a_setup_names_exactly_one_harness() -> None:
    with pytest.raises(ValidationError):
        SetupVersionPassport.model_validate(
            seal_envelope(_setup()).model_dump(mode="json") | {"harness_id": "undefined"}
        )


def test_a_setup_may_declare_no_components() -> None:
    """`ADR-0124`: an empty composition is a composition, not an absence.

    This assertion used to run the other way, bundled with the harness rule
    above and stated in no document. Installing such a setup leaves the target
    *managed* with declared-empty content, so a file appearing in it is drift —
    which is what separates it from removal, where nothing is watched at all.
    """
    empty = SetupVersionPassport.model_validate(
        seal_envelope(_setup()).model_dump(mode="json") | {"components": []}
    )
    assert empty.components == []


def test_tags_are_bounded_one_to_eight() -> None:
    with pytest.raises(ValidationError):
        ComponentVersionPassport.model_validate(
            seal_envelope(_component()).model_dump(mode="json") | {"tags": []}
        )
    with pytest.raises(ValidationError):
        ComponentVersionPassport.model_validate(
            seal_envelope(_component()).model_dump(mode="json")
            | {"tags": [f"tag-{index}" for index in range(9)]}
        )


def test_git_source_rejects_traversal_and_bad_commit() -> None:
    with pytest.raises(ValidationError):
        GitSource(repository="https://github.com/x/y", commit="a" * 40, path="../escape")
    with pytest.raises(ValidationError):
        GitSource(repository="https://github.com/x/y", commit="XYZ", path="components/x")
    source = GitSource(repository="https://github.com/x/y", commit="a" * 40, path="components/x")
    assert source.path == "components/x"


def test_artifact_and_license_are_strict() -> None:
    with pytest.raises(ValidationError):
        ArtifactRef(digest="sha256:short", size_bytes=1)
    with pytest.raises(ValidationError):
        ArtifactRef.model_validate(cast(dict[str, JsonValue], dict(ARTIFACT)) | {"extra": 1})
    assert LicenseInfo(spdx_id="AGPL-3.0-or-later", redistribution_allowed=True).spdx_id


def test_component_adaptations_must_preserve_type_and_not_repeat_harness() -> None:
    body = _component()
    adaptations = body["adaptations"]
    assert isinstance(adaptations, list)
    body["adaptations"] = [adaptations[0], adaptations[0]]
    with pytest.raises(ValidationError, match="must not repeat"):
        ComponentVersionPassport.model_validate(seal_envelope(body).model_dump(mode="json"))

    mismatched = _component(component_type="agent")
    with pytest.raises(ValidationError, match="preserve the logical component type"):
        ComponentVersionPassport.model_validate(seal_envelope(mismatched).model_dump(mode="json"))
