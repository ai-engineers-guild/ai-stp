"""Real HTTP/database GitLab connector lifecycle; the instance alone is synthetic."""

from __future__ import annotations

import base64
import io
import os
import tarfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_platform.gitlab_client import GitLabClient
from ai_stp_platform.gitlab_models import GitLabConnector, GitLabSourceBinding
from ai_stp_platform.gitlab_settings import GitLabConnection, GitLabSettings
from ai_stp_platform.models import Account, AuditEvent, Device, OAuthIdentity
from ai_stp_platform.organization_models import Organization, OrganizationMembership
from ai_stp_platform.storage.memory import MemoryObjectClient

pytestmark = pytest.mark.platform
COMMIT = "a" * 40
BASE_URL = "https://gitlab.example.com"
PROJECT = {
    "id": 42,
    "namespace": {"id": 7},
    "path_with_namespace": "group/subgroup/service",
    "web_url": f"{BASE_URL}/group/subgroup/service",
    "default_branch": "main",
    "last_activity_at": "2026-09-01T00:00:00Z",
    "visibility": "private",
}


@dataclass
class GitLab:
    """Stateful upstream fixture; every /api/v4 request must be a GET."""

    token: str = field(default_factory=lambda: uuid4().hex)
    refresh: str = field(default_factory=lambda: uuid4().hex)
    member: bool = True
    exchanges: int = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/oauth/token":
            assert request.method == "POST"
            self.exchanges += 1
            return httpx.Response(
                200,
                json={
                    "access_token": self.token,
                    "refresh_token": self.refresh,
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        assert request.method == "GET", f"GitLab connector wrote: {request.method} {path}"
        assert request.headers["Authorization"] == f"Bearer {self.token}"
        if path == "/api/v4/user":
            return httpx.Response(200, json={"id": 7, "username": "synthetic"})
        if path == "/api/v4/projects":
            assert request.url.params["membership"] == "true"
            return httpx.Response(200, json=[PROJECT] if self.member else [])
        if path == "/api/v4/projects/42":
            return httpx.Response(200, json=PROJECT) if self.member else httpx.Response(404)
        if path == f"/api/v4/projects/42/repository/commits/{COMMIT}":
            return httpx.Response(200, json={"id": COMMIT})
        if path == "/api/v4/projects/42/repository/archive.tar.gz":
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w:gz") as archive:
                payload = b"# Synthetic skill\n"
                member = tarfile.TarInfo("snapshot/skill/SKILL.md")
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
            return httpx.Response(200, content=output.getvalue())
        raise AssertionError(f"unexpected synthetic route: {request.method} {path}")


@dataclass
class Harness:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    settings: Settings
    gitlab: GitLab
    account: str
    device: str
    token: str
    organization_id: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @property
    def root(self) -> str:
        return f"/v1/corporate/organizations/{self.organization_id}/gitlab"

    async def connect(self) -> httpx.Response:
        response = await self.client.post(
            self.root + "/connect",
            headers=self.headers,
            json={"purpose": "source", "locale": "en", "confirmed": True},
        )
        assert response.status_code == 200, response.text
        authorization_url = cast(str, response.json()["authorization_url"])
        query: dict[str, list[str]] = parse_qs(str(urlsplit(authorization_url).query))
        return await self.client.get(
            "/v1/connectors/gitlab/callback",
            headers=self.headers,
            params={"state": query["state"][0], "code": uuid4().hex},
        )


@pytest_asyncio.fixture
async def harness(migrated_database_url: str, settings_factory: Any) -> AsyncIterator[Harness]:
    config = GitLabSettings(
        connector_encryption_key=SecretStr(base64.urlsafe_b64encode(os.urandom(32)).decode()),
    )
    settings = replace(settings_factory(database_url=migrated_database_url), gitlab=config)
    app = create_app(settings)
    upstream = GitLab()
    async with app.router.lifespan_context(app):
        app.state.gitlab_client = GitLabClient(
            BASE_URL,
            allowed_hosts=["gitlab.example.com"],
            auth="bearer",
            transport=httpx.MockTransport(upstream.handle),
        )
        app.state.object_client = MemoryObjectClient()
        sessions = app.state.sessionmaker
        async with sessions() as db:
            from ai_stp_foundation.ids import new_id

            account = Account(id=new_id("account"))
            device = Device(
                id=new_id("device"), account_id=account.id, public_key="synthetic", state="active"
            )
            organization = Organization(
                id=new_id("organization"), kind="corporate", display_name="On-prem"
            )
            db.add_all(
                [
                    account,
                    device,
                    organization,
                    OAuthIdentity(
                        account_id=account.id,
                        provider="gitlab",
                        provider_subject="gitlab.example.com:7",
                        state="linked",
                        email="synthetic@example.invalid",
                        email_verified=False,
                    ),
                ]
            )
            await db.flush()
            db.add(
                OrganizationMembership(
                    organization_id=organization.id, account_id=account.id, role="owner"
                )
            )
            session = await issue_session(
                db, account_id=account.id, device_id=device.id, ttl_seconds=3600
            )
            await db.commit()
            # The OAuth application lives on this organization's connection.
            config.connections[organization.id] = GitLabConnection(
                base_url=BASE_URL,
                token=SecretStr("operator-pat"),
                allowed_hosts=["gitlab.example.com"],
                oauth_client_id="synthetic-app",
                oauth_client_secret=SecretStr(uuid4().hex),
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield Harness(
                client,
                sessions,
                settings,
                upstream,
                account.id,
                device.id,
                session.raw_token,
                organization.id,
            )


async def test_connect_status_sources_disconnect_and_callback_replay(harness: Harness) -> None:
    h = harness
    status = await h.client.get(h.root + "/connection", headers=h.headers)
    assert status.status_code == 200 and status.json()["connections"][0]["state"] == "disconnected"
    assert status.json()["connections"][0]["configured"] is True

    callback = await h.connect()
    assert callback.status_code == 303, callback.text
    replay = await h.client.get(callback.request.url, headers=h.headers)
    assert replay.status_code == 403 and h.gitlab.exchanges == 1

    status = await h.client.get(h.root + "/connection", headers=h.headers)
    connection = status.json()["connections"][0]
    assert connection["state"] == "connected"
    assert connection["repositories"][0]["project_id"] == 42
    assert connection["repositories"][0]["path_with_namespace"] == "group/subgroup/service"
    assert h.token not in status.text and h.gitlab.token not in status.text

    body = {
        "project_id": 42,
        "commit": COMMIT,
        "subpath": "skill",
        "idempotency_key": uuid4().hex,
    }
    prepared = await h.client.post(h.root + "/sources", headers=h.headers, json=body)
    assert prepared.status_code == 200, prepared.text
    assert "group/subgroup/service" not in prepared.text and h.gitlab.token not in prepared.text
    retry = await h.client.post(h.root + "/sources", headers=h.headers, json=body)
    assert retry.json() == prepared.json()
    conflict = await h.client.post(
        h.root + "/sources", headers=h.headers, json={**body, "subpath": "."}
    )
    assert conflict.status_code == 409

    async with h.sessions() as db:
        connector = await db.scalar(select(GitLabConnector))
        assert connector is not None and connector.token_ciphertext != h.gitlab.token
        binding = await db.scalar(select(GitLabSourceBinding))
        assert binding is not None and binding.commit == COMMIT
        events = list((await db.scalars(select(AuditEvent))).all())
        assert h.gitlab.token not in repr([e.payload for e in events])

    disconnected = await h.client.post(
        h.root + "/connection/disconnect",
        headers=h.headers,
        json={"purpose": "source", "confirmed": True},
    )
    assert disconnected.json()["connections"][0]["state"] == "disconnected"
    denied = await h.client.post(h.root + "/sources", headers=h.headers, json=body)
    assert denied.status_code == 401


async def test_unlinked_gitlab_identity_and_lost_membership_are_refused(harness: Harness) -> None:
    h = harness
    async with h.sessions() as db:
        identity = await db.scalar(select(OAuthIdentity).where(OAuthIdentity.provider == "gitlab"))
        assert identity is not None
        identity.state = "revoked"
        await db.commit()
    refused = await h.client.post(
        h.root + "/connect",
        headers=h.headers,
        json={"purpose": "source", "locale": "en", "confirmed": True},
    )
    assert refused.status_code == 403

    async with h.sessions() as db:
        identity = await db.scalar(select(OAuthIdentity).where(OAuthIdentity.provider == "gitlab"))
        assert identity is not None
        identity.state = "linked"
        await db.commit()
    assert (await h.connect()).status_code == 303
    h.gitlab.member = False
    status = await h.client.get(h.root + "/connection", headers=h.headers)
    assert status.json()["connections"][0]["state"] == "reauthorization_required"
    assert status.json()["connections"][0]["repositories"] == []


async def test_foreign_organization_membership_is_denied(harness: Harness) -> None:
    h = harness
    response = await h.client.post(
        "/v1/corporate/organizations/organization_missing/gitlab/connect",
        headers=h.headers,
        json={"purpose": "source", "locale": "en", "confirmed": True},
    )
    assert response.status_code == 403
    assert h.gitlab.exchanges == 0
