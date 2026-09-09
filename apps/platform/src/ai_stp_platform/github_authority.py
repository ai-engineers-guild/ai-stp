"""Live selected-repository authority and account-bound token encryption."""

from __future__ import annotations

import base64
import os
import re
from datetime import UTC, datetime
from typing import cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.github_connector import GitHubRepository
from ai_stp_platform.github_client import GitHubClient, GitHubError, object_data, positive_id
from ai_stp_platform.github_models import GitHubConnector
from ai_stp_platform.github_settings import ConnectorPurpose, GitHubConnectorSettings

MAX_SCOPE_PAGES = 10
PAGE_SIZE = 100
_FULL_NAME = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _cipher(settings: GitHubConnectorSettings) -> AESGCM:
    key = settings.encryption_key.get_secret_value()
    if not key:
        raise GitHubError("connector_not_configured")
    return AESGCM(base64.b64decode(key, altchars=b"-_", validate=True))


def encrypt_token(
    token: str, *, account_id: str, purpose: str, settings: GitHubConnectorSettings
) -> str:
    nonce = os.urandom(12)
    bound = f"ai-stp:github-token:v1:{account_id}:{purpose}".encode()
    encrypted = _cipher(settings).encrypt(nonce, token.encode(), bound)
    return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_token(connector: GitHubConnector, settings: GitHubConnectorSettings) -> str:
    if (
        connector.state != "connected"
        or not connector.token_ciphertext
        or connector.expires_at is None
    ):
        raise GitHubError("reauthorization_required", status=401)
    if utc(connector.expires_at) <= datetime.now(UTC):
        raise GitHubError("reauthorization_required", status=401)
    try:
        payload = base64.b64decode(connector.token_ciphertext, altchars=b"-_", validate=True)
        bound = f"ai-stp:github-token:v1:{connector.account_id}:{connector.purpose}".encode()
        return _cipher(settings).decrypt(payload[:12], payload[12:], bound).decode()
    except (InvalidTag, ValueError, UnicodeDecodeError):
        raise GitHubError("reauthorization_required", status=401) from None


async def load_connector(
    db: AsyncSession,
    *,
    account_id: str,
    purpose: ConnectorPurpose,
    settings: GitHubConnectorSettings,
    lock: bool = False,
) -> tuple[GitHubConnector, str]:
    if not settings.enabled(purpose):
        raise GitHubError("connector_not_configured")
    query = select(GitHubConnector).where(
        GitHubConnector.account_id == account_id, GitHubConnector.purpose == purpose
    )
    connector = await db.scalar(query.with_for_update() if lock else query)
    if connector is None:
        raise GitHubError("connect_github_required", status=401)
    return connector, decrypt_token(connector, settings)


async def _pages(
    client: GitHubClient, path: str, *, token: str, field: str
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for page in range(1, MAX_SCOPE_PAGES + 1):
        reply = await client.api(
            "GET",
            path,
            token=token,
            params={"per_page": PAGE_SIZE, "page": page},
        )
        data = object_data(reply.data)
        raw = data.get(field)
        if not isinstance(raw, list) or len(cast(list[object], raw)) > PAGE_SIZE:
            raise GitHubError("invalid_upstream_response")
        items.extend(object_data(item) for item in cast(list[object], raw))
        if len(cast(list[object], raw)) < PAGE_SIZE:
            return items
    raise GitHubError("repository_scope_too_large", status=400)


async def selected_installations(
    client: GitHubClient,
    *,
    token: str,
    purpose: ConnectorPurpose,
    settings: GitHubConnectorSettings,
) -> list[dict[str, object]]:
    installations = await _pages(client, "/user/installations", token=token, field="installations")
    expected_slug = settings.credentials(purpose)[2]
    allowed: list[dict[str, object]] = []
    for item in installations:
        if item.get("app_slug") != expected_slug or item.get("suspended_at") is not None:
            continue
        if item.get("repository_selection") != "selected":
            continue
        permissions = object_data(item.get("permissions"))
        if permissions.get("metadata") != "read" or permissions.get("contents") != "read":
            continue
        administration = permissions.get("administration")
        if purpose == "administration" and administration != "write":
            continue
        positive_id(item.get("id"))
        allowed.append(item)
    return allowed


def repository_view(
    raw: dict[str, object], *, installation_id: int, purpose: ConnectorPurpose
) -> GitHubRepository:
    owner = object_data(raw.get("owner"))
    permissions = object_data(raw.get("permissions"))
    name = raw.get("full_name")
    private = raw.get("private")
    owner_type = owner.get("type")
    if (
        not isinstance(name, str)
        or len(name) > 256
        or _FULL_NAME.fullmatch(name) is None
        or type(private) is not bool
        or owner_type not in {"User", "Organization"}
        or permissions.get("pull") is not True
    ):
        raise GitHubError("repository_access_denied", status=403)
    return GitHubRepository(
        installation_id=installation_id,
        repository_id=positive_id(raw.get("id")),
        owner_id=positive_id(owner.get("id")),
        full_name=name,
        owner_type=owner_type,  # type: ignore[arg-type]
        private=private,
        can_administer=purpose == "administration" and permissions.get("admin") is True,
        permission="administration" if purpose == "administration" else "read",
    )


async def selected_repositories(
    client: GitHubClient,
    *,
    token: str,
    purpose: ConnectorPurpose,
    settings: GitHubConnectorSettings,
) -> tuple[list[GitHubRepository], list[dict[str, object]]]:
    installations = await selected_installations(
        client, token=token, purpose=purpose, settings=settings
    )
    repositories: list[GitHubRepository] = []
    for installation in installations:
        installation_id = positive_id(installation["id"])
        raw = await _pages(
            client,
            f"/user/installations/{installation_id}/repositories",
            token=token,
            field="repositories",
        )
        repositories.extend(
            repository_view(item, installation_id=installation_id, purpose=purpose) for item in raw
        )
        if len(repositories) > MAX_SCOPE_PAGES * PAGE_SIZE:
            raise GitHubError("repository_scope_too_large", status=400)
    return repositories, installations


async def require_repository(
    client: GitHubClient,
    *,
    token: str,
    purpose: ConnectorPurpose,
    settings: GitHubConnectorSettings,
    installation_id: int,
    repository_id: int,
) -> GitHubRepository:
    installations = await selected_installations(
        client, token=token, purpose=purpose, settings=settings
    )
    if not any(item["id"] == installation_id for item in installations):
        raise GitHubError("selected_installation_required", status=403)
    raw = await _pages(
        client,
        f"/user/installations/{installation_id}/repositories",
        token=token,
        field="repositories",
    )
    if not any(item.get("id") == repository_id for item in raw):
        raise GitHubError("selected_repository_required", status=403)
    # Refresh permissions and identity immediately before use, not from a saved list.
    reply = await client.api("GET", f"/repositories/{repository_id}", token=token)
    repository = repository_view(
        object_data(reply.data), installation_id=installation_id, purpose=purpose
    )
    if repository.repository_id != repository_id:
        raise GitHubError("repository_identity_changed", status=412)
    if purpose == "administration" and not repository.can_administer:
        raise GitHubError("repository_admin_required", status=403)
    return repository
