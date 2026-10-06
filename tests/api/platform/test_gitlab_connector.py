"""Real HTTP/database GitLab connector lifecycle; the instance alone is synthetic."""

from __future__ import annotations

import base64
import io
import json
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
from ai_stp_foundation.ids import new_id
from ai_stp_platform.gitlab_client import GitLabClient
from ai_stp_platform.gitlab_models import GitLabConnector, GitLabSourceBinding
from ai_stp_platform.gitlab_settings import GitLabConnection, GitLabSettings
from ai_stp_platform.models import Account, AuditEvent, Device, OAuthIdentity
from ai_stp_platform.organization_models import (
    CorporatePermissionGrant,
    Organization,
    OrganizationMembership,
)
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
    visibility: str = "private"
    members: dict[int, int] = field(default_factory=dict[int, int])
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
        assert request.headers["Authorization"] == f"Bearer {self.token}"
        if request.method != "GET":
            return self._mutate(request)
        if path == "/api/v4/user":
            return httpx.Response(200, json={"id": 7, "username": "synthetic"})
        if path == "/api/v4/users":
            return httpx.Response(200, json=[{"id": 9, "username": "colleague"}])
        if path == "/api/v4/projects":
            assert request.url.params["membership"] == "true"
            return httpx.Response(200, json=[PROJECT] if self.member else [])
        if path == "/api/v4/projects/42":
            body = {**PROJECT, "visibility": self.visibility}
            return httpx.Response(200, json=body) if self.member else httpx.Response(404)
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

    def _mutate(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "PUT" and path == "/api/v4/projects/42":
            body = json.loads(request.content)
            assert set(body) == {"visibility"}
            self.visibility = cast(str, body["visibility"])
            return httpx.Response(200, json={**PROJECT, "visibility": self.visibility})
        if request.method == "POST" and path == "/api/v4/projects/42/members":
            body = json.loads(request.content)
            user_id = int(cast(int, body["user_id"]))
            self.members[user_id] = int(cast(int, body["access_level"]))
            return httpx.Response(201, json={"id": user_id})
        if request.method == "DELETE" and path.startswith("/api/v4/projects/42/members/"):
            self.members.pop(int(path.rpartition("/")[2]), None)
            return httpx.Response(204)
        if request.method == "POST" and path == "/api/v4/projects":
            body = json.loads(request.content)
            created = {
                "id": 43,
                "namespace": {"id": 7},
                "path_with_namespace": f"group/{body['path']}",
                "web_url": f"{BASE_URL}/group/{body['path']}",
                "default_branch": "main",
                "visibility": body["visibility"],
            }
            return httpx.Response(201, json=created)
        raise AssertionError(f"unexpected synthetic mutation: {request.method} {path}")


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

    async def connect(self, purpose: str = "source") -> httpx.Response:
        response = await self.client.post(
            self.root + "/connect",
            headers=self.headers,
            json={"purpose": purpose, "locale": "en", "confirmed": True},
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
            await db.flush()
            # The connector gates every route on scoped permissions; grant the
            # harness owner the whole connector set directly (ADR-0220).
            db.add_all(
                CorporatePermissionGrant(
                    id=new_id("operation"),
                    organization_id=organization.id,
                    principal_type="user",
                    account_id=account.id,
                    permission=permission,
                    scope_kind="organization",
                    scope_id=organization.id,
                    issuer_account_id=account.id,
                )
                for permission in (
                    "connector.gitlab.use",
                    "connector.gitlab.read",
                    "connector.gitlab.access",
                    "connector.gitlab.visibility",
                    "connector.gitlab.create",
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
        f"/v1/corporate/organizations/{new_id('organization')}/gitlab/connect",
        headers=h.headers,
        json={"purpose": "source", "locale": "en", "confirmed": True},
    )
    assert response.status_code == 403
    assert h.gitlab.exchanges == 0


async def test_administration_grant_drives_visibility_access_and_creation(
    harness: Harness,
) -> None:
    h = harness
    assert (await h.connect("administration")).status_code == 303

    async def plan(body: dict[str, object]) -> dict[str, Any]:
        response = await h.client.post(
            h.root + "/actions",
            headers=h.headers,
            json={
                "device_id": h.device,
                "idempotency_key": uuid4().hex,
                **body,
            },
        )
        assert response.status_code == 200, response.text
        return cast(dict[str, Any], response.json())

    async def confirm(plan_id: str, plan_hash: str, typed: str | None = None) -> dict[str, Any]:
        response = await h.client.post(
            f"{h.root}/actions/{plan_id}/confirm",
            headers=h.headers,
            json={
                "plan_hash": plan_hash,
                "confirmed": True,
                "typed_project_path": typed,
                "idempotency_key": uuid4().hex,
            },
        )
        assert response.status_code == 200, response.text
        return cast(dict[str, Any], response.json())

    # Visibility: exact path must be retyped before the plan applies.
    planned = await plan({"action": "make_public", "project_id": 42})
    assert planned["state"] == "planned" and planned["warning"] == "repository_and_history_public"
    applied = await confirm(planned["plan_id"], planned["plan_hash"], "group/subgroup/service")
    assert applied["state"] == "applied" and applied["result"] == "public"
    assert h.gitlab.visibility == "public"
    # A second confirmation of the applied plan replays, it does not re-mutate.
    replay = await confirm(planned["plan_id"], planned["plan_hash"], "group/subgroup/service")
    assert replay["state"] == "applied"

    # Access: the exact collaborator is resolved to a numeric id at plan time.
    granted = await plan(
        {
            "action": "grant_access",
            "project_id": 42,
            "recipient": "colleague",
            "access_level": "developer",
        }
    )
    done = await confirm(granted["plan_id"], granted["plan_hash"])
    assert done["state"] == "applied" and h.gitlab.members == {9: 30}
    revoked = await plan({"action": "revoke_access", "project_id": 42, "recipient": "colleague"})
    done = await confirm(revoked["plan_id"], revoked["plan_hash"])
    assert done["state"] == "applied" and h.gitlab.members == {}

    # Creation needs no existing project, only a fresh name/path/visibility.
    created = await plan(
        {
            "action": "create_repository",
            "name": "Service B",
            "path": "service-b",
            "target_visibility": "internal",
        }
    )
    done = await confirm(created["plan_id"], created["plan_hash"])
    assert done["state"] == "applied" and done["result"] == "created"
    assert done["path_with_namespace"] == "group/service-b"

    # Source grants never see administration endpoints as connected.
    status = await h.client.get(h.root + "/connection", headers=h.headers)
    states = {item["purpose"]: item["state"] for item in status.json()["connections"]}
    assert states == {"source": "disconnected", "administration": "connected"}
