"""Real HTTP/database connector lifecycle and effects; GitHub alone is synthetic."""

from __future__ import annotations

import asyncio
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
from ai_stp_platform.github_client import GitHubClient
from ai_stp_platform.github_models import GitHubConnector, GitHubSourceBinding
from ai_stp_platform.github_settings import GitHubConnectorSettings
from ai_stp_platform.models import Account, AuditEvent, Device, OAuthIdentity
from ai_stp_platform.storage.memory import MemoryObjectClient

pytestmark = pytest.mark.platform
COMMIT = "a" * 40
ROOT = "/v1/connectors/github"


@dataclass
class GitHub:
    """Stateful upstream fixture to prove retries do not duplicate external writes."""

    token: str = field(default_factory=lambda: uuid4().hex)
    scoped: str = field(default_factory=lambda: uuid4().hex)
    private: bool = True
    selected: bool = True
    admin: bool = True
    suspended: bool = False
    owner_type: str = "User"
    full_name: str = "example/synthetic"
    refusal: int | None = None
    lose_response: bool = False
    invitation: bool = False
    writes: int = 0
    exchanges: int = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/login/oauth/access_token":
            self.exchanges += 1
            return httpx.Response(
                200, json={"access_token": self.token, "expires_in": 3600, "token_type": "bearer"}
            )
        if path == "/user":
            return httpx.Response(200, json={"id": 7})
        if path == "/user/installations":
            return httpx.Response(
                200,
                json={
                    "installations": [
                        {
                            "id": index,
                            "app_slug": slug,
                            "repository_selection": "selected",
                            "suspended_at": "2026-09-07T00:00:00Z" if self.suspended else None,
                            "permissions": {"metadata": "read", "contents": "read", **permissions},
                        }
                        for index, slug, permissions in (
                            (3, "synthetic-github", {"administration": "write"}),
                        )
                    ]
                },
            )
        repo = {
            "id": 42,
            "full_name": self.full_name,
            "private": self.private,
            "owner": {"id": 7, "type": self.owner_type},
            "permissions": {"pull": True, "admin": self.admin},
        }
        if path == "/user/installations/3/repositories":
            return httpx.Response(200, json={"repositories": [repo] if self.selected else []})
        if path == "/applications/synthetic-github/token/scoped":
            assert json.loads(request.content)["repository_ids"] == [42]
            return httpx.Response(200, json={"token": self.scoped})
        if path == "/repositories/42" or (
            path == "/repos/example/synthetic" and request.method == "GET"
        ):
            return httpx.Response(200, json=repo)
        if path.endswith("/commits/" + COMMIT):
            return httpx.Response(200, json={"sha": COMMIT})
        if path.endswith("/tarball/" + COMMIT):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w:gz") as archive:
                payload = b"# Synthetic skill\n"
                member = tarfile.TarInfo("snapshot/skill/SKILL.md")
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
            return httpx.Response(200, content=output.getvalue())
        if path.endswith("/collaborators/recipient") and request.method == "GET":
            return httpx.Response(404)
        if path.endswith("/invitations"):
            return httpx.Response(
                200, json=[{"invitee": {"login": "recipient"}}] if self.invitation else []
            )
        if request.method in {"PATCH", "PUT"}:
            assert request.headers["authorization"] == f"Bearer {self.scoped}"
            self.writes += 1
            if self.refusal:
                return httpx.Response(self.refusal, json={"message": self.token})
            if request.method == "PATCH":
                self.private = json.loads(request.content)["visibility"] == "private"
                repo["private"] = self.private
            else:
                self.invitation = True
            if self.lose_response:
                raise httpx.ReadTimeout("synthetic lost response", request=request)
            return httpx.Response(200 if request.method == "PATCH" else 201, json=repo)
        raise AssertionError(f"unexpected synthetic route: {request.method} {path}")


@dataclass
class Harness:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    settings: Settings
    github: GitHub
    account: str
    device: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def connect(self, purpose: str = "source", *, pending: bool = False) -> httpx.Response:
        response = await self.client.post(
            ROOT + "/connect",
            headers=self.headers,
            json={
                "purpose": purpose,
                "confirmed": True,
                "mode": "authorize",
            },
        )
        assert response.status_code == 200, response.text
        authorization_url = cast(str, response.json()["authorization_url"])
        query: dict[str, list[str]] = parse_qs(str(urlsplit(authorization_url).query))
        state = query["state"][0]
        return await self.client.get(
            ROOT + "/callback",
            headers=self.headers,
            params={
                "state": state,
                **({"setup_action": "request"} if pending else {"code": uuid4().hex}),
            },
        )

    async def plan(self, action: str = "make_public") -> dict[str, Any]:
        response = await self.client.post(
            ROOT + "/actions",
            headers=self.headers,
            json={
                "action": action,
                "installation_id": 3,
                "repository_id": 42,
                "device_id": self.device,
                "idempotency_key": uuid4().hex,
                **(
                    {"recipient": "recipient", "permission": "push"}
                    if action == "invite_collaborator"
                    else {}
                ),
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    async def confirm(self, plan: dict[str, Any], **overrides: object) -> httpx.Response:
        return await self.client.post(
            ROOT + f"/actions/{plan['plan_id']}/confirm",
            headers=self.headers,
            json={
                "plan_hash": plan["plan_hash"],
                "confirmed": True,
                "typed_repository_name": "example/synthetic",
                "idempotency_key": uuid4().hex,
                **overrides,
            },
        )


@pytest_asyncio.fixture
async def harness(migrated_database_url: str, settings_factory: Any) -> AsyncIterator[Harness]:
    config = GitHubConnectorSettings(
        client_id="synthetic-github",
        client_secret=SecretStr(uuid4().hex),
        app_slug="synthetic-github",
        encryption_key=SecretStr(base64.urlsafe_b64encode(os.urandom(32)).decode()),
    )
    settings = replace(
        settings_factory(database_url=migrated_database_url), github_connector=config
    )
    app, upstream = create_app(settings), GitHub()
    async with app.router.lifespan_context(app):
        app.state.github_client = GitHubClient(httpx.MockTransport(upstream.handle))
        app.state.object_client = MemoryObjectClient()
        sessions = app.state.sessionmaker
        async with sessions() as db:
            from ai_stp_foundation.ids import new_id

            account = Account(id=new_id("account"))
            device = Device(
                id=new_id("device"), account_id=account.id, public_key="synthetic", state="active"
            )
            db.add_all(
                [
                    account,
                    device,
                    OAuthIdentity(
                        account_id=account.id,
                        provider="github",
                        provider_subject="7",
                        state="linked",
                        email="synthetic@example.invalid",
                        email_verified=False,
                    ),
                ]
            )
            await db.flush()
            session = await issue_session(
                db, account_id=account.id, device_id=device.id, ttl_seconds=3600
            )
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield Harness(
                client, sessions, settings, upstream, account.id, device.id, session.raw_token
            )


async def test_connect_scope_snapshot_disconnect_and_callback_replay(harness: Harness) -> None:
    h = harness
    response = await h.client.get(ROOT, headers=h.headers)
    assert all(c["state"] == "disconnected" for c in response.json()["connections"])
    callback = await h.connect()
    assert callback.status_code == 303, callback.text
    replay = await h.client.get(callback.request.url, headers=h.headers)
    assert replay.status_code == 403 and h.github.exchanges == 1
    response = await h.client.get(ROOT, headers=h.headers)
    assert response.json()["connections"][0]["repositories"][0]["repository_id"] == 42
    body = {
        "installation_id": 3,
        "repository_id": 42,
        "commit": COMMIT,
        "subpath": "skill",
        "idempotency_key": uuid4().hex,
    }
    prepared = await h.client.post(ROOT + "/sources", headers=h.headers, json=body)
    assert prepared.status_code == 200, prepared.text
    assert "example/synthetic" not in prepared.text and h.github.token not in prepared.text
    retry = await h.client.post(ROOT + "/sources", headers=h.headers, json=body)
    assert retry.json() == prepared.json()
    conflict = await h.client.post(
        ROOT + "/sources", headers=h.headers, json={**body, "subpath": "."}
    )
    assert conflict.status_code == 409
    async with h.sessions() as db:
        connector = await db.scalar(select(GitHubConnector))
        assert connector is not None and connector.token_ciphertext != h.github.token
        binding = await db.scalar(select(GitHubSourceBinding))
        assert binding is not None and binding.commit == COMMIT
        events = list((await db.scalars(select(AuditEvent))).all())
        assert h.github.token not in repr([e.payload for e in events])
    disconnected = await h.client.post(
        ROOT + "/disconnect", headers=h.headers, json={"confirmed": True}
    )
    assert disconnected.json()["connections"][0]["state"] == "disconnected"
    denied = await h.client.post(ROOT + "/sources", headers=h.headers, json=body)
    assert denied.status_code == 401


async def test_install_callback_continues_to_user_authorization(harness: Harness) -> None:
    h = harness
    response = await h.client.post(
        ROOT + "/connect",
        headers=h.headers,
        json={"confirmed": True, "mode": "install"},
    )
    assert response.status_code == 200, response.text
    authorization_url = cast(str, response.json()["authorization_url"])
    state = parse_qs(str(urlsplit(authorization_url).query))["state"][0]

    installation = await h.client.get(
        ROOT + "/callback",
        headers=h.headers,
        params={"state": state, "setup_action": "install", "installation_id": 3},
    )
    assert installation.status_code == 303
    next_url = str(installation.headers["location"])
    next_query = parse_qs(str(urlsplit(next_url).query))
    assert urlsplit(next_url).path == "/login/oauth/authorize"
    assert next_query["state"] == [state]

    completed = await h.client.get(
        ROOT + "/callback",
        headers=h.headers,
        params={"state": state, "code": uuid4().hex},
    )
    assert completed.status_code == 303
    status = await h.client.get(ROOT, headers=h.headers)
    assert status.json()["connections"][0]["state"] == "connected"


@pytest.mark.parametrize("owner_type", ["User", "Organization"])
async def test_pending_approval_then_selected_installation(
    harness: Harness, owner_type: str
) -> None:
    h = harness
    h.github.owner_type = owner_type
    assert (await h.connect(pending=True)).status_code == 303
    status = await h.client.get(ROOT, headers=h.headers)
    assert status.json()["connections"][0]["state"] == "pending_approval"
    assert h.github.exchanges == 0
    assert (await h.connect()).status_code == 303
    h.github.suspended = True
    status = await h.client.get(ROOT, headers=h.headers)
    assert status.json()["connections"][0]["state"] == "reauthorization_required"
    assert status.json()["connections"][0]["repositories"] == []


@pytest.mark.parametrize("action", ["make_public", "make_private", "invite_collaborator"])
@pytest.mark.parametrize("lose_response", [False, True])
async def test_confirm_retry_and_concurrency_have_one_effect(
    harness: Harness, action: str, lose_response: bool
) -> None:
    h = harness
    assert (await h.connect("administration")).status_code == 303
    if action == "make_private":
        h.github.private = False
    plan = await h.plan(action)
    assert h.github.writes == 0
    h.github.lose_response = lose_response
    first = await h.confirm(plan)
    assert first.status_code == 200, first.text
    assert first.json()["state"] == ("unknown" if lose_response else "applied")
    replies = await asyncio.gather(h.confirm(plan), h.confirm(plan))
    assert all(r.status_code == 200 and r.json()["state"] == "applied" for r in replies)
    assert h.github.writes == 1


@pytest.mark.parametrize("change,status", [("admin", 403), ("selected", 403), ("full_name", 412)])
async def test_stale_or_revoked_repository_never_mutates(
    harness: Harness, change: str, status: int
) -> None:
    h = harness
    await h.connect("administration")
    plan = await h.plan()
    setattr(h.github, change, "example/renamed" if change == "full_name" else False)
    response = await h.confirm(plan)
    assert response.status_code == status, response.text
    assert h.github.writes == 0


async def test_confirmation_and_organization_refusal(harness: Harness) -> None:
    h = harness
    await h.connect("administration")
    plan = await h.plan()
    assert (await h.confirm(plan, confirmed=False)).status_code == 400
    assert (await h.confirm(plan, typed_repository_name="another/repository")).status_code == 400
    assert h.github.writes == 0
    h.github.refusal = 403
    denied = await h.confirm(plan)
    assert denied.json()["state"] == "failed" and h.github.private
    assert h.github.token not in denied.text
    assert (await h.confirm(plan)).status_code == 412
    assert h.github.writes == 1


async def test_cookie_csrf_and_foreign_session_cannot_confirm(harness: Harness) -> None:
    h = harness
    await h.connect("administration")
    plan = await h.plan()
    h.client.cookies.set(h.settings.auth.cookie_name, h.token)
    response = await h.client.post(ROOT + "/disconnect", json={"confirmed": True})
    assert response.status_code == 401
    response = await h.client.post(
        ROOT + f"/actions/{plan['plan_id']}/confirm",
        json={
            "confirmed": True,
            "plan_hash": plan["plan_hash"],
            "idempotency_key": uuid4().hex,
        },
    )
    assert response.status_code == 401 and h.github.writes == 0
