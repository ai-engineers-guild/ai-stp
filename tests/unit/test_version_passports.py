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
    seal_envelope,
)

ARTIFACT = {"digest": digest_canonical("ai-stp:artifact:v1", {"bytes": 1}), "size_bytes": 128}
LICENSE = {"spdx_id": "MIT", "redistribution_allowed": True}
CREATED = "2026-08-05T10:00:00.000Z"


def _component(**overrides: JsonValue) -> dict[str, JsonValue]:
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
        "harness_id": "claude-code",
        "license": dict(LICENSE),
        "component_type": "skill",
        "projection_kind": "native_files",
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
    assert passport.projection_kind == "native_files"


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


def test_component_harness_ids_must_include_primary_and_may_name_os() -> None:
    with pytest.raises(ValidationError, match="harness_ids must include harness_id"):
        ComponentVersionPassport.model_validate(
            seal_envelope(_component(harness_ids=["codex"])).model_dump(mode="json")
        )
    accepted = ComponentVersionPassport.model_validate(
        seal_envelope(
            _component(harness_ids=["claude-code", "codex"], supported_os=["linux", "windows"])
        ).model_dump(mode="json")
    )
    assert list(accepted.harness_ids) == ["claude-code", "codex"]
    assert list(accepted.supported_os) == ["linux", "windows"]


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


def test_setup_requires_components_and_one_harness() -> None:
    with pytest.raises(ValidationError):
        SetupVersionPassport.model_validate(
            seal_envelope(_setup()).model_dump(mode="json") | {"components": []}
        )
    with pytest.raises(ValidationError):
        SetupVersionPassport.model_validate(
            seal_envelope(_setup()).model_dump(mode="json") | {"harness_id": "undefined"}
        )


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


def test_managed_paths_reject_traversal_and_absolute_paths() -> None:
    # A managed path names a file the provider will write inside the target.
    # `GitSource.path` is guarded and this list was not, so the guard was never
    # exercised on the field that decides where bytes actually land.
    for bad in ("../escape", "/etc/passwd", "a/../../b", ""):
        with pytest.raises(ValidationError):
            ComponentVersionPassport.model_validate(
                seal_envelope(_component()).model_dump(mode="json") | {"managed_paths": [bad]}
            )
    accepted = ComponentVersionPassport.model_validate(
        seal_envelope(_component()).model_dump(mode="json")
        | {"managed_paths": ["skills/example/SKILL.md"]}
    )
    assert accepted.managed_paths == ["skills/example/SKILL.md"]
