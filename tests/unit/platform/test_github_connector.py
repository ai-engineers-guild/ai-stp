"""Synthetic GitHub transport and authority checks; no live credentials or repositories."""

import base64
import io
import json
import os
import tarfile
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.github_connector import actions, service
from ai_stp_contracts.github_connector import GitHubActionConfirmRequest, GitHubConnectRequest
from ai_stp_platform.github_authority import decrypt_token, encrypt_token, require_repository
from ai_stp_platform.github_client import GitHubClient, GitHubError
from ai_stp_platform.github_models import GitHubActionPlan, GitHubAuthorizationFlow, GitHubConnector
from ai_stp_platform.github_settings import GitHubConnectorSettings
from ai_stp_sources.definition import pack_component_tree
from ai_stp_sources.errors import SourceError
from ai_stp_sources.git import resolve_git
from ai_stp_sources.models import GitIntent

pytestmark = pytest.mark.platform
ACCOUNT = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"
DEVICE = "device_01ARZ3NDEKTSV4RRFFQ69G5FAV"
COMMIT = "a" * 40


def config() -> GitHubConnectorSettings:
    return GitHubConnectorSettings(
        client_id="synthetic-github",
        client_secret=SecretStr(uuid4().hex),
        app_slug="synthetic-github",
        encryption_key=SecretStr(base64.urlsafe_b64encode(os.urandom(32)).decode()),
    )


def context() -> AuthContext:
    return AuthContext(ACCOUNT, "synthetic-session", DEVICE, "active", False, True)


def repository() -> dict[str, Any]:
    return {
        "id": 42,
        "full_name": "example/synthetic",
        "private": True,
        "owner": {"id": 7, "type": "User"},
        "permissions": {"pull": True, "admin": True},
    }


def transport(
    *, selected: bool = True, admin: bool = False, changed_id: bool = False
) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/installations":
            permissions = {"metadata": "read", "contents": "read"}
            if admin:
                permissions["administration"] = "write"
            return httpx.Response(
                200,
                json={
                    "installations": [
                        {
                            "id": 3,
                            "app_slug": "synthetic-github",
                            "suspended_at": None,
                            "repository_selection": "selected",
                            "permissions": permissions,
                        }
                    ]
                },
            )
        if request.url.path == "/user/installations/3/repositories":
            return httpx.Response(200, json={"repositories": [repository()] if selected else []})
        if request.url.path == "/repositories/42":
            value = repository()
            if changed_id:
                value["id"] = 43
            return httpx.Response(200, json=value)
        raise AssertionError(f"unexpected synthetic route: {request.url.path}")

    return httpx.MockTransport(handle)


def test_encrypted_tokens_bind_account_purpose_and_expiry() -> None:
    settings, token = config(), uuid4().hex
    row = GitHubConnector(
        account_id=ACCOUNT,
        purpose="source",
        state="connected",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    row.token_ciphertext = encrypt_token(
        token, account_id=ACCOUNT, purpose="source", settings=settings
    )
    ciphertext = row.token_ciphertext
    assert ciphertext is not None and token not in ciphertext
    assert decrypt_token(row, settings) == token
    for field, value in (
        ("purpose", "administration"),
        ("account_id", "another"),
        ("state", "disconnected"),
    ):
        previous = getattr(row, field)
        setattr(row, field, value)
        with pytest.raises(GitHubError, match="reauthorization_required"):
            decrypt_token(row, settings)
        setattr(row, field, previous)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(GitHubError, match="reauthorization_required"):
        decrypt_token(row, settings)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selected,changed_id,expected",
    [
        (True, False, None),
        (False, False, "selected_repository_required"),
        (True, True, "repository_identity_changed"),
    ],
)
async def test_live_selected_repository_scope(
    selected: bool, changed_id: bool, expected: str | None
) -> None:
    client = GitHubClient(transport(selected=selected, changed_id=changed_id))

    async def read():
        return await require_repository(
            client,
            token=uuid4().hex,
            purpose="source",
            settings=config(),
            installation_id=3,
            repository_id=42,
        )

    if expected:
        with pytest.raises(GitHubError, match=expected):
            await read()
    else:
        assert (await read()).repository_id == 42


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,reason",
    [
        (401, "reauthorization_required"),
        (403, "repository_access_denied"),
        (404, "repository_access_denied"),
        (422, "github_action_refused"),
        (429, "github_rate_limited"),
    ],
)
async def test_safe_upstream_error_matrix(status: int, reason: str) -> None:
    token = uuid4().hex
    client = GitHubClient(
        httpx.MockTransport(lambda _req: httpx.Response(status, json={"message": token}))
    )
    with pytest.raises(GitHubError) as error:
        await client.api("GET", "/repositories/42", token=token)
    assert str(error.value) == reason
    assert token not in repr(error.value)


@pytest.mark.asyncio
async def test_mutation_token_is_scoped_by_immutable_id() -> None:
    token, scoped, settings = uuid4().hex, uuid4().hex, config()

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/applications/synthetic-github/token/scoped"
        assert request.headers["authorization"].startswith("Basic ")
        body = json.loads(request.content)
        assert body["repository_ids"] == [42] and body["target_id"] == 7
        assert body["permissions"] == {"metadata": "read", "administration": "write"}
        return httpx.Response(200, json={"token": scoped})

    client = GitHubClient(httpx.MockTransport(handle))
    assert (
        await client.scoped_token(
            token=token,
            client_id=settings.client_id,
            client_secret=settings.client_secret.get_secret_value(),
            owner_id=7,
            repository_id=42,
        )
        == scoped
    )


def archive() -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        data = b"# Synthetic skill\n"
        member = tarfile.TarInfo("snapshot/skill/SKILL.md")
        member.size = len(data)
        tar.addfile(member, io.BytesIO(data))
    return output.getvalue()


@pytest.mark.asyncio
async def test_private_snapshot_exact_commit_and_cross_host_token_stripping() -> None:
    token, packed = uuid4().hex, archive()

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "codeload.github.com":
            assert "authorization" not in request.headers
            return httpx.Response(200, content=packed)
        assert request.headers.get("authorization") == f"Bearer {token}"
        if request.url.path.endswith("/commits/" + COMMIT):
            return httpx.Response(200, json={"sha": COMMIT})
        if "/tarball/" in request.url.path:
            return httpx.Response(
                302,
                headers={
                    "location": "https://codeload.github.com/example/synthetic/tar.gz/" + COMMIT
                },
            )
        return httpx.Response(200, json=repository())

    client = GitHubClient(httpx.MockTransport(handle))
    intent = GitIntent(
        repository_url="https://github.com/example/synthetic", tracked_ref=COMMIT, subpath="skill"
    )
    snapshot = await resolve_git(
        intent, fetch=client.fetch, token=token, authorized_repository_id=42
    )
    assert pack_component_tree(snapshot.files) == pack_component_tree(
        {"SKILL.md": b"# Synthetic skill\n"}
    )
    with pytest.raises(SourceError):
        await resolve_git(intent, fetch=client.fetch, token=token)


@pytest.mark.asyncio
async def test_callback_replay_or_other_session_never_exchanges_code() -> None:
    flow = GitHubAuthorizationFlow(
        account_id=ACCOUNT,
        session_id="different-session",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        consumed_at=None,
    )
    db, client = AsyncMock(), AsyncMock(spec=GitHubClient)
    db.scalar.return_value = flow
    with pytest.raises(GitHubError, match="invalid_connection_state"):
        await service.finish_connect(
            db,
            ctx=context(),
            state=uuid4().hex,
            code=uuid4().hex,
            setup_action=None,
            settings=cast(Any, None),
            client=client,
        )
    client.exchange_code.assert_not_called()
    db.commit.assert_not_called()


def test_external_effects_require_affirmative_confirmation() -> None:
    with pytest.raises(ValidationError):
        GitHubConnectRequest.model_validate({})
    with pytest.raises(ValidationError):
        GitHubActionConfirmRequest.model_validate(
            {"plan_hash": "sha256:" + "a" * 64, "idempotency_key": "synthetic-request"}
        )


@pytest.mark.asyncio
async def test_repository_typed_name_is_enforced_before_any_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = GitHubActionPlan(
        id=str(uuid4()),
        account_id=ACCOUNT,
        device_id=DEVICE,
        action="make_public",
        plan_hash="sha256:" + "a" * 64,
        repository_full_name="example/synthetic",
    )
    db, client = AsyncMock(), AsyncMock(spec=GitHubClient)
    db.scalar.return_value = plan
    monkeypatch.setattr(actions, "load_connector", AsyncMock(return_value=(object(), uuid4().hex)))
    monkeypatch.setattr(actions, "_require_active_device", AsyncMock())
    with pytest.raises(GitHubError, match="exact_repository_name_required"):
        await actions.confirm(
            db,
            ctx=context(),
            plan_id=plan.id,
            settings=cast(Any, type("Settings", (), {"github_connector": config()})()),
            client=client,
            body=GitHubActionConfirmRequest(
                plan_hash=plan.plan_hash,
                confirmed=True,
                typed_repository_name="different",
                idempotency_key="synthetic-request",
            ),
        )
    client.api.assert_not_called()
