"""Catalog API contract for official upstream snapshots (SPEC-056 REQ-5607)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.component_passports import adaptation_fields

from ai_stp_api.settings import Settings
from ai_stp_contracts.catalog import (
    ComponentDetail,
    ComponentListResponse,
    ComponentVersionResponse,
)
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_platform.models import Account, AccountAuthorVerification, CatalogMetadata
from ai_stp_platform.official_upstream import OFFICIAL_ACCOUNT_ID
from ai_stp_platform.official_upstream.attribution import OWNERSHIP_NOTICE, build_description
from ai_stp_platform.publication_logic import passport_digest

pytestmark = pytest.mark.platform

STABLE_ID = "component_01JZZK7B8N4M6P2R9T5V0X3Y7Z"
REPOSITORY = "https://github.com/acme/tool"
MAINTAINER = "Acme Maintainers"
COMMIT = "a" * 40


def _description() -> str:
    return build_description(
        project_name="Demo",
        maintainer=MAINTAINER,
        repository=REPOSITORY,
        license_spdx="MIT",
        reviewed_body="Reviewed component body.",
    )


def _passport() -> dict[str, object]:
    description = _description()
    passport: dict[str, object] = {
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
            "commit": COMMIT,
            "path": "skills/demo",
        },
        "artifact": {"digest": "sha256:" + "b" * 64, "size_bytes": 12},
        **adaptation_fields(digest="sha256:" + "b" * 64, size=12),
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "compatibility_evidence_refs": [],
        "component_type": "skill",
        "provides_capabilities": [],
        "requires_components": [],
        "requires_capabilities": [],
        "conflicts": {
            "paths": [],
            "commands": [],
            "hooks": [],
            "mcp": [],
            "agents": [],
            "plugins": [],
        },
    }
    passport["revision_id"] = derive_revision_id(passport)  # type: ignore[arg-type]
    return passport


async def _seed_official_snapshot(sessionmaker: async_sessionmaker[AsyncSession]) -> str:
    passport = _passport()
    published_at = datetime(2026, 8, 31, tzinfo=UTC)
    async with sessionmaker() as session:
        if await session.get(Account, OFFICIAL_ACCOUNT_ID) is None:
            session.add(Account(id=OFFICIAL_ACCOUNT_ID, allow_publisher_listing=True))
            await session.flush()
        if await session.get(AccountAuthorVerification, OFFICIAL_ACCOUNT_ID) is None:
            session.add(AccountAuthorVerification(account_id=OFFICIAL_ACCOUNT_ID, verified=True))
        session.add(
            CatalogMetadata(
                owner_account_id=OFFICIAL_ACCOUNT_ID,
                object_kind="component",
                stable_id=STABLE_ID,
                version="1.0",
                current_revision_id=str(passport["revision_id"]),
                visibility="public",
                lifecycle_state="active",
                name="Demo Skill",
                published_at=published_at,
                trust_lane="experimental",
                author_verified=True,
                component_verified=False,
                passport_digest=passport_digest(ComponentVersionPassport.model_validate(passport)),
                passport_document=passport,
                likes_count=0,
                updated_at=published_at,
            )
        )
        await session.commit()
    return str(passport["description"])


def _assert_separate_publisher_and_upstream(description: str, publisher_id: str) -> None:
    assert publisher_id == OFFICIAL_ACCOUNT_ID
    assert publisher_id not in description
    assert description.startswith(f"Demo is maintained by {MAINTAINER}")
    assert MAINTAINER in description
    assert REPOSITORY in description
    assert "AI STP authored" not in description
    assert "does not claim upstream authorship" in description
    assert OWNERSHIP_NOTICE in description or "does not claim upstream authorship" in description


@pytest.mark.asyncio
async def test_catalog_api_presents_official_publisher_apart_from_upstream(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    description = await _seed_official_snapshot(sessionmaker)

    listing = await client.get(
        "/v1/catalog/components",
        params={"page_size": "20", "include_experimental": "true"},
    )
    assert listing.status_code == 200
    listed = ComponentListResponse.model_validate(listing.json())
    card = next(item for item in listed.experimental if item.stable_id == STABLE_ID)
    assert card.publisher_id == OFFICIAL_ACCOUNT_ID
    assert card.publisher_id != card.latest_description
    assert card.latest_description.startswith(f"Demo is maintained by {MAINTAINER}")
    assert "AI STP authored" not in card.latest_description
    assert card.latest_trust.author_verified is True
    assert card.latest_trust.component_verified is False

    detail = await client.get(f"/v1/catalog/components/{STABLE_ID}")
    assert detail.status_code == 200
    body = ComponentDetail.model_validate(detail.json())
    assert body.summary.publisher_id == OFFICIAL_ACCOUNT_ID
    assert body.summary.latest_trust.author_verified is True
    assert body.summary.latest_trust.component_verified is False
    assert body.versions[0].trust.author_verified is True
    assert body.versions[0].trust.component_verified is False

    version = await client.get(f"/v1/catalog/components/{STABLE_ID}/versions/1.0")
    assert version.status_code == 200
    exact = ComponentVersionResponse.model_validate(version.json())
    assert exact.passport.owner_id == OFFICIAL_ACCOUNT_ID
    assert exact.passport.source is not None
    assert exact.passport.source.repository == REPOSITORY
    _assert_separate_publisher_and_upstream(exact.passport.description, exact.passport.owner_id)
    assert exact.passport.description == description
    assert exact.trust.author_verified is True
    assert exact.trust.component_verified is False
