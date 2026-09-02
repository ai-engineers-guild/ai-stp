"""Catalog machine contract for official upstream snapshots (SPEC-056 REQ-5607)."""

from __future__ import annotations

from ai_stp_contracts.catalog import (
    CatalogSupport,
    CatalogTrust,
    ComponentSummary,
    ComponentVersionResponse,
)
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_platform.official_upstream import OFFICIAL_ACCOUNT_ID
from ai_stp_platform.official_upstream.attribution import OWNERSHIP_NOTICE, build_description

SUPPORT_MISSING = CatalogSupport(
    schema_version=1,
    tier="primary",
    state="missing",
    evidence=[],
)

STABLE_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"
REPOSITORY = "https://github.com/acme/tool"
MAINTAINER = "Acme Maintainers"


def _description() -> str:
    return build_description(
        project_name="Demo",
        maintainer=MAINTAINER,
        repository=REPOSITORY,
        license_spdx="MIT",
        reviewed_body="Reviewed component body.",
    )


def test_catalog_trust_axes_are_independent() -> None:
    author_only = CatalogTrust(
        trust_lane="experimental", author_verified=True, component_verified=False
    )
    bytes_only = CatalogTrust(
        trust_lane="experimental", author_verified=False, component_verified=True
    )
    assert author_only.author_verified is True
    assert author_only.component_verified is False
    assert bytes_only.author_verified is False
    assert bytes_only.component_verified is True


def test_component_summary_separates_publisher_from_upstream_attribution() -> None:
    description = _description()
    summary = ComponentSummary.model_validate(
        {
            "stable_id": STABLE_ID,
            "publisher_id": OFFICIAL_ACCOUNT_ID,
            "likes_count": 0,
            "updated_at": "2026-08-31T00:00:00.000Z",
            "latest_version": "1.0",
            "latest_name": "Demo Skill",
            "latest_description": description[:240],
            "latest_harness_id": "claude-code",
            "latest_component_type": "skill",
            "latest_projection_kind": "native_files",
            "latest_tags": ["code-review"],
            "latest_lifecycle": "active",
            "latest_trust": {
                "trust_lane": "experimental",
                "author_verified": True,
                "component_verified": False,
            },
            "latest_published_at": "2026-08-31T00:00:00.000Z",
            "latest_support": SUPPORT_MISSING.model_dump(mode="json"),
        }
    )
    payload = summary.model_dump(mode="json")
    assert payload["publisher_id"] == OFFICIAL_ACCOUNT_ID
    assert payload["publisher_id"] != payload["latest_description"]
    assert payload["latest_description"].startswith(f"Demo is maintained by {MAINTAINER}")
    assert MAINTAINER in payload["latest_description"]
    assert REPOSITORY in payload["latest_description"]
    assert "AI STP authored" not in payload["latest_description"]
    assert payload["latest_trust"]["author_verified"] is True
    assert payload["latest_trust"]["component_verified"] is False


def test_version_response_keeps_official_publisher_and_upstream_notice() -> None:
    description = _description()
    passport = ComponentVersionPassport.model_validate(
        {
            "schema_version": 1,
            "kind": "component",
            "stable_id": STABLE_ID,
            "revision_id": "revision_" + "0" * 64,
            "parent_revision_ids": [],
            "owner_id": OFFICIAL_ACCOUNT_ID,
            "created_at": "2026-08-31T00:00:00.000Z",
            "visibility": "public",
            "facts": {},
            "name": "Demo Skill",
            "description": description,
            "version": "1.0",
            "license": {"spdx_id": "MIT", "redistribution_allowed": True},
            "tags": ["code-review"],
            "source": {
                "repository": REPOSITORY,
                "commit": "a" * 40,
                "path": "skills/demo",
            },
            "artifact": {"digest": "sha256:" + "b" * 64, "size_bytes": 12},
            "harness_id": "claude-code",
            "required_env": [],
            "requires_credentials": False,
            "requires_authorization": "none",
            "permissions": {"filesystem": [], "network": [], "process": []},
            "external_endpoints": [],
            "component_type": "skill",
            "projection_kind": "native_files",
        }
    )
    response = ComponentVersionResponse.model_validate(
        {
            "passport": passport.model_dump(mode="json"),
            "passport_digest": "sha256:" + "0" * 64,
            "lifecycle": "active",
            "trust": {
                "trust_lane": "experimental",
                "author_verified": True,
                "component_verified": False,
            },
            "support": SUPPORT_MISSING.model_dump(mode="json"),
            "published_at": "2026-08-31T00:00:00.000Z",
        }
    )
    payload = response.model_dump(mode="json")
    assert payload["passport"]["owner_id"] == OFFICIAL_ACCOUNT_ID
    assert payload["passport"]["source"]["repository"] == REPOSITORY
    assert payload["passport"]["description"].startswith(f"Demo is maintained by {MAINTAINER}")
    assert payload["passport"]["description"].rstrip().endswith(OWNERSHIP_NOTICE)
    assert "AI STP authored" not in payload["passport"]["description"]
    assert payload["trust"]["author_verified"] is True
    assert payload["trust"]["component_verified"] is False
