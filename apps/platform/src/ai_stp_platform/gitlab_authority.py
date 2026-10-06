"""Live project authority, account-bound token encryption and refresh rotation."""

from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.gitlab_client import GitLabClient, GitLabError, GitLabRepository
from ai_stp_platform.gitlab_models import GitLabConnector
from ai_stp_platform.gitlab_settings import GitLabSettings

MAX_SCOPE_PROJECTS = 500
_REFRESH_SKEW = timedelta(seconds=30)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def gitlab_host(base_url: str) -> str:
    host = urlsplit(base_url).hostname or ""
    return host.lower()


def qualified_subject(base_url: str, user_id: int) -> str:
    """GitLab user ids are only unique inside one instance; the qualified
    subject must match the OIDC identity's ``{host}:{sub}`` binding."""
    return f"{gitlab_host(base_url)}:{user_id}"


def _cipher(settings: GitLabSettings) -> AESGCM:
    key = settings.connector_encryption_key.get_secret_value()
    if not key:
        raise GitLabError("connector_not_configured")
    return AESGCM(base64.b64decode(key, altchars=b"-_", validate=True))


def _aad(connector_fields: str, purpose: str) -> bytes:
    return f"ai-stp:gitlab-token:v1:{connector_fields}:{purpose}".encode()


def encrypt_token(
    token: str,
    *,
    account_id: str,
    gitlab_base_url: str,
    purpose: str,
    settings: GitLabSettings,
    kind: str = "access",
) -> str:
    nonce = os.urandom(12)
    bound = _aad(f"{account_id}:{gitlab_base_url}:{kind}", purpose)
    encrypted = _cipher(settings).encrypt(nonce, token.encode(), bound)
    return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def _decrypt(
    ciphertext: str, *, connector: GitLabConnector, settings: GitLabSettings, kind: str
) -> str:
    try:
        payload = base64.b64decode(ciphertext, altchars=b"-_", validate=True)
        bound = _aad(
            f"{connector.account_id}:{connector.gitlab_base_url}:{kind}", connector.purpose
        )
        return _cipher(settings).decrypt(payload[:12], payload[12:], bound).decode()
    except (InvalidTag, ValueError, UnicodeDecodeError):
        raise GitLabError("reauthorization_required", status=401) from None


def decrypt_token(connector: GitLabConnector, settings: GitLabSettings) -> str:
    if (
        connector.state != "connected"
        or not connector.token_ciphertext
        or connector.expires_at is None
    ):
        raise GitLabError("reauthorization_required", status=401)
    return _decrypt(
        connector.token_ciphertext, connector=connector, settings=settings, kind="access"
    )


def _decrypt_refresh(connector: GitLabConnector, settings: GitLabSettings) -> str:
    if not connector.refresh_token_ciphertext:
        raise GitLabError("reauthorization_required", status=401)
    return _decrypt(
        connector.refresh_token_ciphertext,
        connector=connector,
        settings=settings,
        kind="refresh",
    )


def grant_fields(payload: Mapping[str, object]) -> tuple[str, str, int]:
    """Validate one OAuth token response; GitLab rotates both tokens on
    refresh, so refresh and exchange share the same surface."""
    token = payload.get("access_token")
    refresh = payload.get("refresh_token")
    expires = payload.get("expires_in")
    if (
        not isinstance(token, str)
        or not 1 <= len(token) <= 4096
        or any(char.isspace() for char in token)
        or not isinstance(refresh, str)
        or not 1 <= len(refresh) <= 4096
        or any(char.isspace() for char in refresh)
        or type(expires) is not int
        or not 0 < expires <= 86_400
        or str(payload.get("token_type", "")).lower() != "bearer"
    ):
        raise GitLabError("expiring_user_authorization_required", status=403)
    return token, refresh, expires


async def store_grant(
    connector: GitLabConnector,
    payload: Mapping[str, object],
    *,
    settings: GitLabSettings,
) -> None:
    token, refresh, expires = grant_fields(payload)
    connector.token_ciphertext = encrypt_token(
        token,
        account_id=connector.account_id,
        gitlab_base_url=connector.gitlab_base_url,
        purpose=connector.purpose,
        settings=settings,
    )
    connector.refresh_token_ciphertext = encrypt_token(
        refresh,
        account_id=connector.account_id,
        gitlab_base_url=connector.gitlab_base_url,
        purpose=connector.purpose,
        settings=settings,
        kind="refresh",
    )
    connector.expires_at = datetime.now(UTC) + timedelta(seconds=expires)


async def load_connector(
    db: AsyncSession,
    *,
    account_id: str,
    gitlab_base_url: str,
    client: GitLabClient,
    settings: GitLabSettings,
    purpose: str = "source",
    lock: bool = False,
) -> tuple[GitLabConnector, str]:
    """Load the live grant and rotate it transparently when it expired.

    GitLab access tokens live about two hours; refresh rotates both tokens, so
    the row is held FOR UPDATE while the grant is exchanged.
    """
    query = select(GitLabConnector).where(
        GitLabConnector.account_id == account_id,
        GitLabConnector.gitlab_base_url == gitlab_base_url,
        GitLabConnector.purpose == purpose,
    )
    connector = await db.scalar(query.with_for_update() if lock else query)
    if connector is None or connector.state != "connected":
        raise GitLabError("connect_gitlab_required", status=401)
    if (
        connector.expires_at is None
        or utc(connector.expires_at) <= datetime.now(UTC) + _REFRESH_SKEW
    ):
        credentials = settings.connector_credentials(connector.connection_organization_id)
        if credentials is None:
            raise GitLabError("connector_not_configured")
        client_id, client_secret = credentials
        try:
            payload = await client.oauth_token(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": _decrypt_refresh(connector, settings),
                    "client_id": client_id,
                    "client_secret": client_secret,
                }
            )
            await store_grant(connector, payload, settings=settings)
        except GitLabError as error:
            if error.reason in {"gitlab_grant_revoked", "reauthorization_required"}:
                connector.state = "reauthorization_required"
                connector.token_ciphertext = None
                connector.refresh_token_ciphertext = None
            raise GitLabError("reauthorization_required", status=401) from error
    return connector, decrypt_token(connector, settings)


async def member_projects(
    client: GitLabClient, *, token: str, limit: int = MAX_SCOPE_PROJECTS
) -> list[GitLabRepository]:
    return await client.list_repositories(token=token, limit=limit)


async def require_project(
    client: GitLabClient,
    *,
    token: str,
    project_id: int,
) -> GitLabRepository:
    """Re-check membership immediately before use, not from a saved list."""
    members = await member_projects(client, token=token)
    if not any(repository.repository_id == project_id for repository in members):
        raise GitLabError("selected_project_required", status=403)
    return await client.repository(project_id, token=token)
