"""GitHub language observations publish only through an explicit project link."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.api_settings import make_settings

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.slices.corporate import github_languages
from ai_stp_contracts.context import context_authorization_revision
from ai_stp_contracts.github_connector import GitHubRepository
from ai_stp_foundation.ids import new_id
from ai_stp_platform.github_client import GitHubClient, GitHubReply
from ai_stp_platform.models import Account, Device
from ai_stp_platform.organization_models import (
    CorporateProject,
    Organization,
    OrganizationMembership,
    ProjectIdentity,
    ProjectLink,
)
from ai_stp_platform.technology_models import (
    Technology,
    TechnologyCoordinateMapping,
    TechnologyUsageFact,
)

pytestmark = pytest.mark.platform


@pytest_asyncio.fixture
async def client_db(
    tmp_path: Path, migrated_database_url: str
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    app = create_app(make_settings(tmp_path, database_url=migrated_database_url))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client, app.state.sessionmaker


async def test_github_languages_require_link_and_publish_proposed(
    client_db: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sessionmaker = client_db
    account_id = new_id("account")
    device_id = new_id("device")
    async with sessionmaker() as db:
        db.add_all(
            [
                Account(id=account_id, status="active"),
                Device(
                    id=device_id,
                    account_id=account_id,
                    public_key="gh-language-" + uuid.uuid4().hex[:24],
                    state="active",
                ),
            ]
        )
        await db.flush()
        token = (
            await issue_session(db, account_id=account_id, device_id=device_id, ttl_seconds=3600)
        ).raw_token
        await db.commit()
    boot = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "organization_name": "github-languages-" + uuid.uuid4().hex[:20],
            "superadmin_account_id": account_id,
            "idempotency_key": "boot-" + uuid.uuid4().hex,
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert boot.status_code == 200, boot.text
    organization_id = boot.json()["organization_id"]
    provider_id = new_id("provider_project")
    project_id = new_id("remote_project")
    technology_id = new_id("technology")
    async with sessionmaker() as db:
        db.add_all(
            [
                ProjectIdentity(
                    id=provider_id,
                    organization_id=organization_id,
                    namespace="provider",
                    external_key="github:42",
                    display_name="team/repo",
                    provider_kind="github",
                    provider_installation_id="7",
                    immutable_repository_id="github:42",
                    current_url="https://github.com/team/repo",
                    state="active",
                ),
                ProjectIdentity(
                    id=project_id,
                    organization_id=organization_id,
                    namespace="remote",
                    external_key=f"manual:{project_id}",
                    display_name="repo",
                    state="active",
                ),
                Technology(
                    id=technology_id,
                    organization_id=organization_id,
                    name="Python",
                    lifecycle="active",
                    provenance="manual",
                ),
            ]
        )
        await db.flush()
        db.add_all(
            [
                CorporateProject(
                    id=project_id,
                    organization_id=organization_id,
                    name="repo",
                    lifecycle="active",
                    state="active",
                    revision=1,
                ),
                TechnologyCoordinateMapping(
                    organization_id=organization_id,
                    version="mapping1",
                    kind="alias",
                    coordinate="Python",
                    technology_id=technology_id,
                    provenance="manual",
                ),
            ]
        )
        await db.commit()
    async with sessionmaker() as db:
        organization = await db.get(Organization, organization_id)
        membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id
            )
        )
        assert organization is not None and membership is not None
        revision = context_authorization_revision(
            "corporate", organization_id, organization.policy_revision, membership.revision
        )

    calls: list[str] = []

    async def fake_load(*_args: object, **_kwargs: object) -> tuple[object, str]:
        return SimpleNamespace(github_subject="123"), "test-token"

    async def fake_subject(*_args: object) -> str:
        return "123"

    async def fake_repository(*_args: object, **_kwargs: object) -> GitHubRepository:
        calls.append("selected")
        return GitHubRepository(
            installation_id=7,
            repository_id=42,
            owner_id=5,
            full_name="team/repo",
            html_url="https://github.com/team/repo",
            owner_type="Organization",
            private=True,
            can_administer=False,
            permission="read",
        )

    async def fake_api(
        _self: GitHubClient, _method: str, path: str, **_kwargs: object
    ) -> GitHubReply:
        calls.append(path)
        data: object = {
            "/repositories/42": {"default_branch": "main"},
            "/repos/team/repo/commits": [{"sha": "a" * 40}],
            "/repos/team/repo/languages": {"Python": 100, "Other": 20},
        }[path]
        return GitHubReply(200, data)

    monkeypatch.setattr(github_languages, "load_connector", fake_load)
    monkeypatch.setattr(github_languages, "_linked_subject", fake_subject)
    monkeypatch.setattr(github_languages, "require_repository", fake_repository)
    monkeypatch.setattr(GitHubClient, "api", fake_api)
    path = (
        f"/v1/corporate/organizations/{organization_id}/github/observations/"
        f"{provider_id}/projects/{project_id}/enrich"
    )
    payload = {
        "authorization_revision": revision,
        "expected_revision": 1,
        "idempotency_key": "enrich-" + uuid.uuid4().hex,
        "scan_id": new_id("scan"),
        "mapping_version": "mapping1",
    }
    auth = {"Authorization": f"Bearer {token}"}
    denied = await client.post(path, json=payload, headers=auth)
    assert denied.status_code == 403 and calls == []
    async with sessionmaker() as db:
        db.add(
            ProjectLink(
                id=new_id("project_link"),
                plan_id=new_id("link_plan"),
                plan_digest="sha256:" + "a" * 64,
                organization_id=organization_id,
                actor_account_id=account_id,
                device_id=device_id,
                local_project_id=new_id("project"),
                remote_project_id=project_id,
                provider_project_id=provider_id,
                state="linked",
                local_revision="local1",
                remote_revision="remote1",
                provider_revision="provider1",
                create_idempotency_key="link-" + uuid.uuid4().hex,
            )
        )
        await db.commit()
    published = await client.post(path, json=payload, headers=auth)
    assert published.status_code == 200, published.text
    assert len(published.json()["usages"]) == 1
    before = list(calls)
    replay = await client.post(path, json=payload, headers=auth)
    assert replay.status_code == 200 and replay.json() == published.json()
    assert calls == before
    async with sessionmaker() as db:
        fact = await db.scalar(
            select(TechnologyUsageFact).where(
                TechnologyUsageFact.organization_id == organization_id
            )
        )
        assert fact is not None and fact.review == "proposed"
        assert fact.evidence[0]["source_revision"] == "a" * 40
