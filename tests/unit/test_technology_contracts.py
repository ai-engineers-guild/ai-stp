"""Small runnable checks for technology trust-boundary contracts."""

from urllib.parse import urlunsplit

import pytest
from pydantic import ValidationError

from ai_stp_contracts.context import CapabilityScopeQuery
from ai_stp_contracts.technology import (
    INITIAL_CATEGORY_NAMES,
    RESERVED_CATEGORY_NAMES,
    TechnologyCategoryMetadata,
    TechnologyEvidence,
    TechnologyLandscapeQuery,
    TechnologyMappingEntry,
    TechnologyMetadata,
    TechnologyScanHandoff,
    TechnologyUsageFact,
    normalize_technology_name,
)
from ai_stp_contracts.technology_seed import SEED_CATEGORIES, SEED_TECHNOLOGIES
from ai_stp_foundation.ids import is_valid_id, new_id


def test_mapping_coordinates_preserve_scoped_packages_but_reject_uri_credentials() -> None:
    base = {"technology_id": new_id("technology"), "kind": "package", "provenance": "catalog-v1"}
    assert (
        TechnologyMappingEntry.model_validate({**base, "coordinate": "@scope/package"}).coordinate
        == "@scope/package"
    )
    credential_uri = urlunsplit(("https", "owner:password@example.invalid", "/artifact", "", ""))
    with pytest.raises(ValidationError, match="credentials"):
        TechnologyMappingEntry.model_validate({**base, "coordinate": credential_uri})


def test_seed_manifest_identity_and_classification() -> None:
    assert len(SEED_CATEGORIES) == 23
    assert len({identifier for identifier, _ in SEED_CATEGORIES}) == 23
    assert all(is_valid_id(identifier, "category") for identifier, _ in SEED_CATEGORIES)
    assert all(is_valid_id(identifier, "technology") for identifier, _ in SEED_TECHNOLOGIES)
    by_name = {metadata.name: (identifier, metadata) for identifier, metadata in SEED_TECHNOLOGIES}
    assert by_name["React"][1].aliases == ["React.js"]
    assert by_name["PostgreSQL"][1].aliases == ["Postgres"]
    assert by_name["npm CLI"][0] != by_name["npm registry"][0]
    assert by_name["GitLab CI/CD"][0] != by_name["GitLab Runner"][0]
    categories = dict(SEED_CATEGORIES)
    assert {categories[key] for key in by_name["Bun"][1].category_ids} == {
        "Runtime",
        "Build and bundling tool",
        "Package manager",
        "Test runner and browser automation",
    }


def test_scoped_projection_rejects_untyped_or_missing_resource_identity() -> None:
    assert CapabilityScopeQuery().scope_kind == "organization"
    assert CapabilityScopeQuery(scope_kind="technology", scope_id=new_id("technology"))
    for fields in (
        {"scope_kind": "project"},
        {"scope_kind": "project", "scope_id": new_id("technology")},
        {"scope_kind": "setup", "scope_id": new_id("operation")},
    ):
        with pytest.raises(ValidationError):
            CapabilityScopeQuery.model_validate(fields)


def test_landscape_filters_are_typed_and_independently_bounded() -> None:
    query = TechnologyLandscapeQuery(limit=1, project_limit=256, project_offset=900)
    assert query.review is None
    assert not query.include_history
    assert not query.include_inactive
    for fields in (
        {"limit": 257},
        {"project_limit": 0},
        {"project_offset": -1},
        {"context": "setup"},
        {"project_id": new_id("technology")},
        {"query": "   "},
        {"query": "x" * 201},
    ):
        with pytest.raises(ValidationError):
            TechnologyLandscapeQuery.model_validate(fields)


def test_category_vocabulary_and_exact_normalization() -> None:
    assert len(INITIAL_CATEGORY_NAMES) == 23
    for name in INITIAL_CATEGORY_NAMES:
        assert TechnologyCategoryMetadata(name=name).name == name
    for name in RESERVED_CATEGORY_NAMES:
        with pytest.raises(ValidationError):
            TechnologyCategoryMetadata(name=f" {name.upper()} ")
    assert (
        normalize_technology_name("  \uff32\uff45\uff41\uff43\uff54.\uff4a\uff53  ") == "react.js"
    )
    assert normalize_technology_name("React.js") != normalize_technology_name("React")


def test_multiple_categories_and_safe_metadata() -> None:
    categories = [new_id("category"), new_id("category")]
    assert TechnologyMetadata(name="Bun", category_ids=categories).category_ids == categories
    for fields in (
        {"aliases": ["Postgres", " POSTGRES "]},
        {"category_ids": [categories[0], categories[0]]},
        {"official_urls": [urlunsplit(("https", "user:password@example.test", "/", "", ""))]},
        {"official_urls": ["https://example.test/?token=value"]},
    ):
        with pytest.raises(ValidationError):
            TechnologyMetadata.model_validate({"name": "Bun", "category_ids": categories, **fields})


def test_evidence_paths_and_unknown_versions() -> None:
    evidence = {"source": "declared", "observed_at": "2026-09-12T00:00:00.000Z"}
    assert TechnologyEvidence.model_validate(
        {**evidence, "path": "packages/api/pyproject.toml"}
    ).path
    for path in ("/etc/passwd", "../secret", "C:/private", "a\\file", ".env", "keys/id_rsa"):
        with pytest.raises(ValidationError):
            TechnologyEvidence.model_validate({**evidence, "path": path})
    assert TechnologyUsageFact(context="production").version is None
    assert (
        TechnologyUsageFact(
            context="development", version="^22", version_kind="declared_range"
        ).version_kind
        == "declared_range"
    )
    for fields in ({"version": "22"}, {"version_kind": "observed_version"}):
        with pytest.raises(ValidationError):
            TechnologyUsageFact.model_validate({"context": "testing", **fields})


def test_scan_handoff_keeps_offline_and_publication_identities_explicit() -> None:
    fields: dict[str, object] = {
        "local_project_id": new_id("project"),
        "scan_id": new_id("scan"),
        "scope": "repository",
        "complete": True,
        "detector_version": "offline-1",
        "mapping_version": "registry-1",
        "observations": [],
    }
    assert TechnologyScanHandoff.model_validate(fields).project_id is None
    for identity in (
        {"local_project_id": None},
        {"organization_id": new_id("organization")},
        {"project_id": new_id("remote_project")},
    ):
        with pytest.raises(ValidationError):
            TechnologyScanHandoff.model_validate({**fields, **identity})
    published = TechnologyScanHandoff.model_validate(
        {
            **fields,
            "organization_id": new_id("organization"),
            "project_id": new_id("remote_project"),
        }
    )
    assert published.project_id != published.local_project_id
