"""Account-bound connector installation, status and canonical source preparation."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from urllib.parse import urlencode
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_contracts.github_connector import (
    GitHubConnectionStatus,
    GitHubConnectorStatus,
    GitHubConnectRequest,
    GitHubConnectResponse,
    GitHubRepository,
    GitHubSourcePrepared,
    GitHubSourcePrepareRequest,
)
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.github_authority import (
    decrypt_token,
    encrypt_token,
    load_connector,
    require_repository,
    selected_repositories,
    utc,
)
from ai_stp_platform.github_client import GitHubClient, GitHubError, object_data, positive_id
from ai_stp_platform.github_models import (
    GitHubAuthorizationFlow,
    GitHubConnector,
    GitHubSourceBinding,
)
from ai_stp_platform.github_settings import ConnectorPurpose
from ai_stp_platform.github_sources import request_digest
from ai_stp_platform.models import Account, OAuthIdentity
from ai_stp_platform.storage.object_store import ImmutableObjectStore
from ai_stp_sources.coordinates import canonical_subpath
from ai_stp_sources.definition import pack_component_tree
from ai_stp_sources.errors import SourceError
from ai_stp_sources.git import resolve_git
from ai_stp_sources.models import GitIntent


def api_error(error: GitHubError) -> ApiError:
    categories = {
        400: ErrorCategory.VALIDATION,
        401: ErrorCategory.AUTH_REQUIRED,
        403: ErrorCategory.PERMISSION,
        404: ErrorCategory.NOT_FOUND,
        409: ErrorCategory.CONFLICT,
        412: ErrorCategory.PRECONDITION,
        422: ErrorCategory.VALIDATION,
        429: ErrorCategory.RATE_LIMITED,
    }
    return ApiError(
        categories.get(error.status, ErrorCategory.DEPENDENCY),
        "GitHub connector operation could not complete",
        details={"reason": error.reason},
    )


async def _linked_subject(db: AsyncSession, account_id: str) -> str:
    subject = await db.scalar(
        select(OAuthIdentity.provider_subject).where(
            OAuthIdentity.account_id == account_id,
            OAuthIdentity.provider == "github",
            OAuthIdentity.state == "linked",
        )
    )
    if subject is None:
        raise GitHubError("link_github_identity_required", status=403)
    return subject


async def start_connect(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: GitHubConnectRequest,
    settings: Settings,
) -> GitHubConnectResponse:
    config = settings.github_connector
    if not config.enabled(body.purpose):
        raise GitHubError("connector_not_configured")
    await _linked_subject(db, ctx.account_id)
    state = secrets.token_urlsafe(32)
    expiry = datetime.now(UTC) + timedelta(minutes=10)
    callback = f"{settings.auth.oauth_callback_base()}/v1/connectors/github/callback"
    db.add(
        GitHubAuthorizationFlow(
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            account_id=ctx.account_id,
            session_id=ctx.session_id,
            purpose=body.purpose,
            locale=body.locale,
            callback_uri=callback,
            expires_at=expiry,
        )
    )
    client_id, _secret, slug = config.credentials(body.purpose)
    if body.mode == "install":
        url = f"https://github.com/apps/{slug}/installations/new?{urlencode({'state': state})}"
    else:
        url = "https://github.com/login/oauth/authorize?" + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": callback,
                "state": state,
            }
        )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="github.connector_started",
        target_table="github_connector",
        target_id=body.purpose,
    )
    return GitHubConnectResponse(authorization_url=url, expires_at=format_timestamp(expiry))


async def finish_connect(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    state: str,
    code: str | None,
    setup_action: str | None,
    settings: Settings,
    client: GitHubClient,
) -> tuple[str, str]:
    flow = await db.scalar(
        select(GitHubAuthorizationFlow)
        .where(GitHubAuthorizationFlow.state_hash == hashlib.sha256(state.encode()).hexdigest())
        .with_for_update()
    )
    if (
        flow is None
        or flow.account_id != ctx.account_id
        or flow.session_id != ctx.session_id
        or flow.consumed_at is not None
        or utc(flow.expires_at) <= datetime.now(UTC)
    ):
        raise GitHubError("invalid_connection_state", status=403)
    purpose = cast(ConnectorPurpose, flow.purpose)
    locale, callback_uri = flow.locale, flow.callback_uri
    flow.consumed_at = datetime.now(UTC)
    # A code exchange must never run twice after a lost callback response.
    await db.commit()
    await db.scalar(select(Account).where(Account.id == ctx.account_id).with_for_update())
    row = await db.scalar(
        select(GitHubConnector)
        .where(
            GitHubConnector.account_id == ctx.account_id,
            GitHubConnector.purpose == purpose,
        )
        .with_for_update()
    )
    if row is None:
        row = GitHubConnector(
            id=str(uuid4()),
            account_id=ctx.account_id,
            purpose=purpose,
            github_subject="",
            authorization_revision=str(uuid4()),
            state="disconnected",
            installations=[],
        )
        db.add(row)
    reason: str | None = None
    try:
        if not settings.github_connector.enabled(purpose):
            raise GitHubError("connector_not_configured")
        if setup_action == "request" and code is None:
            row.state = "pending_approval"
        else:
            if not code:
                raise GitHubError("reauthorization_required", status=401)
            client_id, secret, _slug = settings.github_connector.credentials(purpose)
            exchanged = await client.exchange_code(
                client_id=client_id, client_secret=secret, code=code, redirect_uri=callback_uri
            )
            token, expires = exchanged.get("access_token"), exchanged.get("expires_in")
            if (
                not isinstance(token, str)
                or not 1 <= len(token) <= 4096
                or any(char.isspace() for char in token)
                or type(expires) is not int
                or not 0 < expires <= 28_800
                or str(exchanged.get("token_type", "")).lower() != "bearer"
            ):
                raise GitHubError("expiring_user_authorization_required", status=403)
            user = object_data((await client.api("GET", "/user", token=token)).data)
            subject = str(positive_id(user.get("id")))
            if subject != await _linked_subject(db, ctx.account_id):
                raise GitHubError("github_identity_mismatch", status=403)
            repositories, installations = await selected_repositories(
                client, token=token, purpose=purpose, settings=settings.github_connector
            )
            if not installations:
                raise GitHubError("selected_installation_required", status=403)
            row.github_subject = subject
            row.expires_at = datetime.now(UTC) + timedelta(seconds=expires)
            row.token_ciphertext = encrypt_token(
                token,
                account_id=ctx.account_id,
                purpose=purpose,
                settings=settings.github_connector,
            )
            row.installations = _scope_record(repositories, installations)
            row.state = "connected"
    except GitHubError as error:
        reason = error.reason
        row.state = "reauthorization_required"
    if row.state != "connected":
        row.token_ciphertext = None
        row.expires_at = None
        row.installations = []
    row.authorization_revision = str(uuid4())
    row.updated_at = datetime.now(UTC)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="github.connector_completed",
        target_table="github_connector",
        target_id=row.id,
        reason=reason,
        payload={"outcome": row.state, "purpose": purpose},
    )
    return locale, row.state


def _scope_record(
    repositories: list[GitHubRepository], installations: list[dict[str, object]]
) -> list[dict[str, object]]:
    return [
        {
            "installation_id": item["id"],
            "permissions": item["permissions"],
            "repository_ids": [
                repo.repository_id for repo in repositories if repo.installation_id == item["id"]
            ],
        }
        for item in installations
    ]


async def read_status(
    db: AsyncSession, *, ctx: AuthContext, settings: Settings, client: GitHubClient
) -> GitHubConnectorStatus:
    statuses: list[GitHubConnectionStatus] = []
    for purpose in ("source", "administration"):
        configured = settings.github_connector.enabled(purpose)
        row = await db.scalar(
            select(GitHubConnector).where(
                GitHubConnector.account_id == ctx.account_id, GitHubConnector.purpose == purpose
            )
        )
        status = GitHubConnectionStatus(
            purpose=purpose,
            configured=configured,
            state="disconnected"
            if row is None
            else cast(
                Literal[
                    "disconnected", "pending_approval", "connected", "reauthorization_required"
                ],
                row.state,
            ),
            expires_at=None
            if row is None or row.expires_at is None
            else format_timestamp(utc(row.expires_at)),
        )
        if configured and row is not None and row.state == "connected":
            try:
                if row.github_subject != await _linked_subject(db, ctx.account_id):
                    raise GitHubError("github_identity_mismatch", status=403)
                token = decrypt_token(row, settings.github_connector)
                repositories, installations = await selected_repositories(
                    client, token=token, purpose=purpose, settings=settings.github_connector
                )
                if not installations:
                    raise GitHubError("selected_installation_required", status=403)
                row.installations = _scope_record(repositories, installations)
                status = status.model_copy(update={"repositories": repositories})
            except GitHubError as error:
                if error.status in {401, 403}:
                    row.state = "reauthorization_required"
                    row.token_ciphertext = None
                    row.installations = []
                    await emit_audit(
                        db,
                        actor_account_id=ctx.account_id,
                        action="github.connector_unavailable",
                        target_table="github_connector",
                        target_id=row.id,
                        reason=error.reason,
                    )
                status = status.model_copy(update={"state": row.state, "reason": error.reason})
        if not configured:
            status = status.model_copy(
                update={
                    "state": "disconnected",
                    "reason": "connector_not_configured",
                    "expires_at": None,
                }
            )
        statuses.append(status)
    return GitHubConnectorStatus(connections=statuses)


async def disconnect(db: AsyncSession, *, ctx: AuthContext, purpose: ConnectorPurpose) -> None:
    row = await db.scalar(
        select(GitHubConnector)
        .where(GitHubConnector.account_id == ctx.account_id, GitHubConnector.purpose == purpose)
        .with_for_update()
    )
    if row is not None and row.state != "disconnected":
        row.token_ciphertext = None
        row.expires_at = None
        row.state = "disconnected"
        row.installations = []
        row.authorization_revision = str(uuid4())
        row.updated_at = datetime.now(UTC)
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            action="github.connector_disconnected",
            target_table="github_connector",
            target_id=row.id,
        )


def source_response(binding: GitHubSourceBinding) -> GitHubSourcePrepared:
    return GitHubSourcePrepared(
        source_binding_id=binding.id,
        content_digest=binding.content_digest,
        size_bytes=binding.size_bytes,
        artifact_inventory=list(binding.inventory),
        source_visibility=cast(Literal["private", "public"], binding.source_visibility),
    )


async def prepare_source(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: GitHubSourcePrepareRequest,
    settings: Settings,
    client: GitHubClient,
    store: ImmutableObjectStore,
) -> GitHubSourcePrepared:
    try:
        subpath = canonical_subpath(body.subpath)
    except SourceError:
        raise GitHubError("invalid_component_subpath", status=400) from None
    connector, token = await load_connector(
        db,
        account_id=ctx.account_id,
        purpose="source",
        settings=settings.github_connector,
        lock=True,
    )
    if connector.github_subject != await _linked_subject(db, ctx.account_id):
        raise GitHubError("github_identity_mismatch", status=403)
    repository = await require_repository(
        client,
        token=token,
        purpose="source",
        settings=settings.github_connector,
        installation_id=body.installation_id,
        repository_id=body.repository_id,
    )
    request_hash = request_digest(body.model_dump(mode="json", exclude={"idempotency_key"}))
    existing = await db.scalar(
        select(GitHubSourceBinding).where(
            GitHubSourceBinding.account_id == ctx.account_id,
            GitHubSourceBinding.idempotency_key == body.idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise GitHubError("idempotency_conflict", status=409)
        payload = await store.read_by_digest(
            existing.content_digest,
            expected_size=existing.size_bytes,
            owner_account_id=ctx.account_id,
        )
        if payload is None:
            raise GitHubError("source_artifact_unavailable")
        return source_response(existing)
    try:
        snapshot = await resolve_git(
            GitIntent(
                repository_url=f"https://github.com/{repository.full_name}",
                tracked_ref=body.commit,
                subpath=subpath,
            ),
            fetch=client.fetch,
            token=token,
            authorized_repository_id=repository.repository_id,
        )
        payload = pack_component_tree(snapshot.files)
    except SourceError:
        raise GitHubError("source_snapshot_refused", status=400) from None
    if len(snapshot.files) > 1000:
        raise GitHubError("source_inventory_too_large", status=400)
    content_digest = digest_bytes("ai-stp:artifact:v1", payload)
    await store.put_immutable(
        payload,
        expected_digest=content_digest,
        expected_size=len(payload),
        owner_account_id=ctx.account_id,
    )
    binding = GitHubSourceBinding(
        id=str(uuid4()),
        account_id=ctx.account_id,
        connector_id=connector.id,
        installation_id=body.installation_id,
        repository_id=repository.repository_id,
        repository_owner_id=repository.owner_id,
        repository_full_name=repository.full_name,
        commit=body.commit,
        subpath=subpath,
        source_visibility="private" if repository.private else "public",
        content_digest=content_digest,
        size_bytes=len(payload),
        inventory=sorted(snapshot.files),
        request_hash=request_hash,
        idempotency_key=body.idempotency_key,
    )
    db.add(binding)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="github.source_prepared",
        target_table="github_source_binding",
        target_id=binding.id,
        payload={"content_digest": content_digest, "source_visibility": binding.source_visibility},
    )
    return source_response(binding)
