"""GitLab grant encryption binds account, instance and purpose; reads stay live."""

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from ai_stp_platform.gitlab_authority import (
    decrypt_token,
    encrypt_token,
    grant_fields,
    qualified_subject,
    require_project,
    store_grant,
)
from ai_stp_platform.gitlab_client import GitLabClient, GitLabError
from ai_stp_platform.gitlab_models import GitLabConnector
from ai_stp_platform.gitlab_settings import GitLabSettings

ACCOUNT = "account_synthetic"
BASE_URL = "https://gitlab.example.com"


def config(**overrides: object) -> GitLabSettings:
    settings = GitLabSettings(
        connector_encryption_key=SecretStr(base64.urlsafe_b64encode(os.urandom(32)).decode())
    )
    for field, value in overrides.items():
        setattr(settings, field, value)
    return settings


def connector_row(**overrides: object) -> GitLabConnector:
    row = GitLabConnector(
        id=str(uuid4()),
        account_id=ACCOUNT,
        gitlab_base_url=BASE_URL,
        connection_organization_id="organization_test",
        purpose="source",
        gitlab_subject="gitlab.example.com:7",
        authorization_revision=str(uuid4()),
        state="connected",
        projects=[],
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    for field, value in overrides.items():
        setattr(row, field, value)
    return row


def test_encrypted_tokens_bind_account_instance_purpose_and_kind() -> None:
    settings, token = config(), uuid4().hex
    row = connector_row()
    row.token_ciphertext = encrypt_token(
        token,
        account_id=ACCOUNT,
        gitlab_base_url=BASE_URL,
        purpose="source",
        settings=settings,
    )
    ciphertext = row.token_ciphertext
    assert ciphertext is not None and token not in ciphertext
    assert decrypt_token(row, settings) == token
    for field, value in (
        ("purpose", "administration"),
        ("account_id", "account_other"),
        ("gitlab_base_url", "https://gitlab.other.example.com"),
        ("state", "disconnected"),
        ("expires_at", None),
    ):
        previous = getattr(row, field)
        setattr(row, field, value)
        with pytest.raises(GitLabError, match="reauthorization_required"):
            decrypt_token(row, settings)
        setattr(row, field, previous)
    # A refresh ciphertext under the same account never decrypts as access.
    row.refresh_token_ciphertext = encrypt_token(
        "refresh",
        account_id=ACCOUNT,
        gitlab_base_url=BASE_URL,
        purpose="source",
        settings=settings,
        kind="refresh",
    )
    access, refresh = row.token_ciphertext, row.refresh_token_ciphertext
    row.token_ciphertext = refresh
    with pytest.raises(GitLabError, match="reauthorization_required"):
        decrypt_token(row, settings)
    row.token_ciphertext = access


def test_missing_encryption_key_keeps_everything_closed() -> None:
    with pytest.raises(GitLabError, match="connector_not_configured"):
        encrypt_token(
            "x",
            account_id=ACCOUNT,
            gitlab_base_url=BASE_URL,
            purpose="source",
            settings=GitLabSettings(),
        )


@pytest.mark.asyncio
async def test_store_grant_validates_and_rotates_both_tokens() -> None:
    settings = config()
    row = connector_row()
    with pytest.raises(GitLabError, match="expiring_user_authorization_required"):
        await store_grant(row, {"access_token": "x"}, settings=settings)
    await store_grant(
        row,
        {
            "access_token": "access-" + uuid4().hex,
            "refresh_token": "refresh-" + uuid4().hex,
            "expires_in": 7200,
            "token_type": "Bearer",
        },
        settings=settings,
    )
    assert row.token_ciphertext is not None and row.refresh_token_ciphertext is not None
    assert row.expires_at is not None and row.expires_at > datetime.now(UTC)
    assert decrypt_token(row, settings).startswith("access-")


def test_qualified_subject_scopes_user_id_to_instance_host() -> None:
    assert qualified_subject("https://gitlab.example.com", 7) == "gitlab.example.com:7"
    assert qualified_subject("https://gitlab.com", 7) == "gitlab.com:7"


@pytest.mark.asyncio
async def test_require_project_demands_live_membership() -> None:
    project = {
        "id": 42,
        "namespace": {"id": 7},
        "path_with_namespace": "group/service",
        "web_url": f"{BASE_URL}/group/service",
        "default_branch": "main",
        "last_activity_at": None,
    }

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v4/projects":
            return httpx.Response(200, json=[project] if request.url.params["page"] == "1" else [])
        if request.url.path == "/api/v4/projects/42":
            return httpx.Response(200, json=project)
        raise AssertionError(request.url)

    member = GitLabClient(
        BASE_URL,
        allowed_hosts=["gitlab.example.com"],
        auth="bearer",
        transport=httpx.MockTransport(respond),
    )
    assert (await require_project(member, token="x", project_id=42)).repository_id == 42
    with pytest.raises(GitLabError, match="selected_project_required"):
        await require_project(member, token="x", project_id=43)


def test_grant_fields_rejects_non_expiring_or_typed_wrongly() -> None:
    good = {
        "access_token": "a",
        "refresh_token": "r",
        "expires_in": 7200,
        "token_type": "bearer",
    }
    assert grant_fields(good) == ("a", "r", 7200)
    for bad in (
        {**good, "refresh_token": None},
        {**good, "expires_in": 0},
        {**good, "expires_in": "7200"},
        {**good, "token_type": "mac"},
        {**good, "access_token": "with space"},
    ):
        with pytest.raises(GitLabError, match="expiring_user_authorization_required"):
            grant_fields(bad)
