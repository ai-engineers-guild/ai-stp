"""GitLab observations retain provider identity without making project links."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import ClassVar

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.api_settings import make_settings

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import GitLabConnection, Settings
from ai_stp_api.slices.corporate import gitlab as gitlab_route
from ai_stp_contracts.context import context_authorization_revision
from ai_stp_foundation.ids import new_id
from ai_stp_platform.gitlab_client import GitLabError, GitLabRepository
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


class FakeGitLabClient:
    calls: ClassVar[list[tuple[str, int]]] = []
    path = "team/service"
    unavailable = False

    def __init__(self, base_url: str, *, allowed_hosts: list[str]) -> None:
        assert base_url == "https://gitlab.com"
        assert allowed_hosts == []
        self.base_url = base_url

    async def list_repositories(self, *, token: str, limit: int) -> list[GitLabRepository]:
        assert token == "x"
        self.calls.append(("list", limit))
        return [self._repository()]

    async def repository(self, repository_id: int, *, token: str) -> GitLabRepository:
        assert token == "x"
        self.calls.append(("repository", repository_id))
        if self.unavailable:
            raise GitLabError("gitlab_repository_inaccessible")
        return self._repository()

    async def head_revision(self, repository_id: int, branch: str, *, token: str) -> str:
        assert token == "x" and branch == "main"
        self.calls.append(("revision", repository_id))
        return "a" * 40

    async def languages(self, repository_id: int, *, token: str) -> dict[str, float]:
        assert token == "x"
        self.calls.append(("languages", repository_id))
        return {"Python": 80.0, "Unmapped": 20.0}

    @classmethod
    def _repository(cls) -> GitLabRepository:
        return GitLabRepository(
            repository_id=42,
            namespace_id=7,
            path_with_namespace=cls.path,
            repository_url=f"https://gitlab.com/{cls.path}",
            default_branch="main",
            last_activity_at="2026-09-01T00:00:00.000Z",
        )


@pytest_asyncio.fixture
async def discovery_client(
    tmp_path: Path, migrated_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings]]:
    FakeGitLabClient.calls = []
    FakeGitLabClient.path = "team/service"
    FakeGitLabClient.unavailable = False
    settings = make_settings(tmp_path, database_url=migrated_database_url)
    settings.gitlab.connections.clear()
    app = create_app(settings)
    monkeypatch.setattr(gitlab_route, "GitLabClient", FakeGitLabClient)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client, app.state.sessionmaker, settings


async def _account(sessionmaker: async_sessionmaker[AsyncSession]) -> tuple[str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"), status="active")
        device = Device(
            id=new_id("device"),
            account_id=account.id,
            public_key="gl-pk-" + uuid.uuid4().hex[:24],
            state="active",
        )
        db.add_all([account, device])
        await db.flush()
        issued = await issue_session(
            db, account_id=account.id, device_id=device.id, ttl_seconds=3600
        )
        await db.commit()
        return account.id, issued.raw_token


async def _bootstrap(client: AsyncClient, account_id: str) -> str:
    key = "gitlab-discovery-" + uuid.uuid4().hex[:20]
    response = await client.post(
        "/v1/corporate/bootstrap",
        json={
            "schema_version": 1,
            "organization_name": key,
            "superadmin_account_id": account_id,
            "idempotency_key": key,
        },
        headers={"X-AI-STP-Bootstrap-Secret": "corporate-bootstrap-test-secret"},
    )
    assert response.status_code == 200, response.text
    return response.json()["organization_id"]


async def _revision(sessionmaker: async_sessionmaker[AsyncSession], organization_id: str) -> str:
    async with sessionmaker() as db:
        organization = await db.get(Organization, organization_id)
        membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id
            )
        )
        assert organization is not None and membership is not None
        return context_authorization_revision(
            "corporate", organization_id, organization.policy_revision, membership.revision
        )


async def test_gitlab_register_refresh_disconnect_and_replay_preserve_links(
    discovery_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, settings = discovery_client
    account_id, token = await _account(sessionmaker)
    organization_id = await _bootstrap(client, account_id)
    settings.gitlab.connections[organization_id] = GitLabConnection(
        base_url="https://gitlab.com", token=SecretStr("x")
    )
    auth = {"Authorization": f"Bearer {token}"}
    base = f"/v1/corporate/organizations/{organization_id}/gitlab"

    listed = await client.get(f"{base}/repositories", headers=auth)
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["provider_project_id"] is None

    payload = {
        "schema_version": 1,
        "authorization_revision": await _revision(sessionmaker, organization_id),
        "expected_revision": 0,
        "idempotency_key": "register-" + uuid.uuid4().hex,
    }
    registered = await client.post(f"{base}/repositories/42", json=payload, headers=auth)
    assert registered.status_code == 200, registered.text
    identity_id = registered.json()["provider_project_id"]
    assert registered.json()["observed_revision"] == "a" * 40
    assert registered.json()["connected"] is True
    replay = await client.post(f"{base}/repositories/42", json=payload, headers=auth)
    assert replay.status_code == 200 and replay.json() == registered.json()

    FakeGitLabClient.path = "renamed/service"
    refreshed = await client.post(
        f"{base}/observations/{identity_id}/refresh",
        json={
            **payload,
            "authorization_revision": await _revision(sessionmaker, organization_id),
            "expected_revision": 1,
            "idempotency_key": "refresh-" + uuid.uuid4().hex,
        },
        headers=auth,
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["repository_url"] == "https://gitlab.com/renamed/service"
    assert refreshed.json()["provider_project_id"] == identity_id

    FakeGitLabClient.unavailable = True
    denied = await client.post(
        f"{base}/observations/{identity_id}/refresh",
        json={
            **payload,
            "authorization_revision": await _revision(sessionmaker, organization_id),
            "expected_revision": 2,
            "idempotency_key": "inaccessible-" + uuid.uuid4().hex,
        },
        headers=auth,
    )
    assert denied.status_code == 403

    disconnected = await client.post(
        f"{base}/observations/{identity_id}/disconnect",
        json={
            **payload,
            "authorization_revision": await _revision(sessionmaker, organization_id),
            "expected_revision": 2,
            "idempotency_key": "disconnect-" + uuid.uuid4().hex,
        },
        headers=auth,
    )
    assert disconnected.status_code == 200, disconnected.text
    assert disconnected.json()["connected"] is False
    FakeGitLabClient.unavailable = False
    reconnected = await client.post(
        f"{base}/repositories/42",
        json={
            **payload,
            "authorization_revision": await _revision(sessionmaker, organization_id),
            "expected_revision": 3,
            "idempotency_key": "reconnect-" + uuid.uuid4().hex,
        },
        headers=auth,
    )
    assert reconnected.status_code == 200, reconnected.text
    assert reconnected.json()["provider_project_id"] == identity_id
    assert reconnected.json()["connected"] is True
    async with sessionmaker() as db:
        identity = await db.get(ProjectIdentity, identity_id)
        assert identity is not None
        assert identity.current_url == "https://gitlab.com/renamed/service"
        assert identity.provider_installation_id == "https://gitlab.com"
        assert list((await db.scalars(select(ProjectLink))).all()) == []


async def test_gitlab_list_requires_membership_before_accessing_connection(
    discovery_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, settings = discovery_client
    owner_id, _ = await _account(sessionmaker)
    organization_id = await _bootstrap(client, owner_id)
    settings.gitlab.connections[organization_id] = GitLabConnection(
        base_url="https://gitlab.com", token=SecretStr("x")
    )
    _, outsider_token = await _account(sessionmaker)
    denied = await client.get(
        f"/v1/corporate/organizations/{organization_id}/gitlab/repositories",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert denied.status_code == 403
    assert FakeGitLabClient.calls == []


async def test_linked_gitlab_languages_publish_only_proposed_canonical_facts(
    discovery_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, settings = discovery_client
    account_id, token = await _account(sessionmaker)
    organization_id = await _bootstrap(client, account_id)
    settings.gitlab.connections[organization_id] = GitLabConnection(
        base_url="https://gitlab.com", token=SecretStr("x")
    )
    auth = {"Authorization": f"Bearer {token}"}
    base = f"/v1/corporate/organizations/{organization_id}/gitlab"
    registered = await client.post(
        f"{base}/repositories/42",
        json={
            "authorization_revision": await _revision(sessionmaker, organization_id),
            "expected_revision": 0,
            "idempotency_key": "register-" + uuid.uuid4().hex,
        },
        headers=auth,
    )
    assert registered.status_code == 200, registered.text
    provider_id = registered.json()["provider_project_id"]
    remote_id = new_id("remote_project")
    technology_id = new_id("technology")
    async with sessionmaker() as db:
        device = await db.scalar(select(Device).where(Device.account_id == account_id))
        assert device is not None
        db.add_all(
            [
                ProjectIdentity(
                    id=remote_id,
                    organization_id=organization_id,
                    namespace="remote",
                    external_key=f"manual:{remote_id}",
                    display_name="service",
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
                    id=remote_id,
                    organization_id=organization_id,
                    name="service",
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

    scan_id = new_id("scan")
    scan_payload = {
        "authorization_revision": await _revision(sessionmaker, organization_id),
        "expected_revision": 1,
        "idempotency_key": "enrich-" + uuid.uuid4().hex,
        "scan_id": scan_id,
        "mapping_version": "mapping1",
    }
    scan_path = f"{base}/observations/{provider_id}/projects/{remote_id}/enrich"
    unlinked = await client.post(scan_path, json=scan_payload, headers=auth)
    assert unlinked.status_code == 403
    assert ("languages", 42) not in FakeGitLabClient.calls
    async with sessionmaker() as db:
        db.add(
            ProjectLink(
                id=new_id("project_link"),
                plan_id=new_id("link_plan"),
                plan_digest="sha256:" + "a" * 64,
                organization_id=organization_id,
                actor_account_id=account_id,
                device_id=device.id,
                local_project_id=new_id("project"),
                remote_project_id=remote_id,
                provider_project_id=provider_id,
                state="linked",
                local_revision="local1",
                remote_revision="remote1",
                provider_revision="provider1",
                create_idempotency_key="link-" + uuid.uuid4().hex,
            )
        )
        await db.commit()
    scan = await client.post(
        scan_path,
        json=scan_payload,
        headers=auth,
    )
    assert scan.status_code == 200, scan.text
    assert scan.json()["scan_id"] == scan_id
    assert len(scan.json()["usages"]) == 1
    FakeGitLabClient.unavailable = True
    prior_calls = list(FakeGitLabClient.calls)
    replay = await client.post(scan_path, json=scan_payload, headers=auth)
    assert replay.status_code == 200 and replay.json() == scan.json()
    assert FakeGitLabClient.calls == prior_calls
    async with sessionmaker() as db:
        fact = await db.scalar(
            select(TechnologyUsageFact).where(
                TechnologyUsageFact.organization_id == organization_id
            )
        )
        assert fact is not None
        assert fact.review == "proposed"
        assert fact.evidence[0]["source"] == "forge_language"
        assert fact.evidence[0]["source_revision"] == "a" * 40
    FakeGitLabClient.unavailable = False
    refreshed = await client.post(
        f"{base}/observations/{provider_id}/refresh",
        json={
            "authorization_revision": await _revision(sessionmaker, organization_id),
            "expected_revision": 1,
            "idempotency_key": "activity-" + uuid.uuid4().hex,
        },
        headers=auth,
    )
    assert refreshed.status_code == 200, refreshed.text
    async with sessionmaker() as db:
        project = await db.get(CorporateProject, remote_id)
        assert project is not None
        assert project.source_availability == "available"
        assert project.repository_activity_at is not None
        assert project.repository_activity_at.year == 2026
        assert project.revision == 3
