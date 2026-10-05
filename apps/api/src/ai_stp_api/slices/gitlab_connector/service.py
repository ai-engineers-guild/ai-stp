"""Account-bound GitLab grant lifecycle and canonical source preparation."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
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
from ai_stp_contracts.gitlab_connector import (
    GitLabConnectionStatus,
    GitLabConnectorRepository,
    GitLabConnectorStatus,
    GitLabConnectResponse,
    GitLabPlatformObject,
    GitLabSourcePrepared,
    GitLabSourcePrepareRequest,
)
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.gitlab_authority import (
    gitlab_host,
    grant_fields,
    load_connector,
    member_projects,
    qualified_subject,
    require_project,
    store_grant,
    utc,
)
from ai_stp_platform.gitlab_client import GitLabClient, GitLabError, GitLabRepository
from ai_stp_platform.gitlab_models import (
    GitLabAuthorizationFlow,
    GitLabConnector,
    GitLabSourceBinding,
)
from ai_stp_platform.gitlab_settings import GitLabConnection
from ai_stp_platform.gitlab_sources import request_digest
from ai_stp_platform.models import Account, OAuthIdentity, PublicationPlan
from ai_stp_platform.storage.object_store import ImmutableObjectStore
from ai_stp_sources.archive import MAX_GIT_ARCHIVE_BYTES, extract_component_files
from ai_stp_sources.coordinates import canonical_subpath
from ai_stp_sources.definition import pack_component_tree
from ai_stp_sources.errors import SourceError

PURPOSE = "source"


def api_error(error: GitLabError) -> ApiError:
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
        "GitLab connector operation could not complete",
        details={"reason": error.reason},
    )


def connector_client(connection: GitLabConnection) -> GitLabClient:
    """The request-scoped client always carries user-grant Bearer credentials."""
    return GitLabClient(
        connection.base_url,
        allowed_hosts=connection.allowed_hosts,
        auth="bearer",
    )


async def _linked_subjects(db: AsyncSession, account_id: str) -> list[str]:
    return list(
        await db.scalars(
            select(OAuthIdentity.provider_subject).where(
                OAuthIdentity.account_id == account_id,
                OAuthIdentity.provider == "gitlab",
                OAuthIdentity.state == "linked",
            )
        )
    )


def _authorization_url(*, base_url: str, client_id: str, callback: str, state: str) -> str:
    return f"{base_url}/oauth/authorize?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": callback,
            "state": state,
            "scope": "read_api",
        }
    )


async def start_connect(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    body_locale: str,
    settings: Settings,
    client: GitLabClient,
) -> GitLabConnectResponse:
    credentials = settings.gitlab.connector_credentials(organization_id)
    if credentials is None or not settings.gitlab.connector_enabled(organization_id):
        raise GitLabError("connector_not_configured")
    host = gitlab_host(client.base_url)
    if not any(
        subject.rpartition(":")[0] == host for subject in await _linked_subjects(db, ctx.account_id)
    ):
        raise GitLabError("link_gitlab_identity_required", status=403)
    expiry = datetime.now(UTC) + timedelta(minutes=10)
    state = secrets.token_urlsafe(32)
    callback = f"{settings.auth.oauth_callback_base()}/v1/connectors/gitlab/callback"
    db.add(
        GitLabAuthorizationFlow(
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            account_id=ctx.account_id,
            session_id=ctx.session_id,
            connection_organization_id=organization_id,
            purpose=PURPOSE,
            locale=body_locale,
            callback_uri=callback,
            expires_at=expiry,
        )
    )
    url = _authorization_url(
        base_url=client.base_url, client_id=credentials[0], callback=callback, state=state
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="gitlab.connector_started",
        target_table="gitlab_connector",
        target_id=PURPOSE,
    )
    return GitLabConnectResponse(authorization_url=url, expires_at=format_timestamp(expiry))


def _project_scope(repositories: list[GitLabRepository]) -> list[dict[str, object]]:
    return [
        {
            "project_id": repository.repository_id,
            "namespace_id": repository.namespace_id,
            "path_with_namespace": repository.path_with_namespace,
        }
        for repository in repositories
    ]


async def finish_connect(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    state: str,
    code: str | None,
    settings: Settings,
    client_for: Callable[[GitLabConnection], GitLabClient],
) -> tuple[str, str]:
    """Finish the grant; ``client_for`` builds the instance client per flow."""
    flow = await db.scalar(
        select(GitLabAuthorizationFlow)
        .where(GitLabAuthorizationFlow.state_hash == hashlib.sha256(state.encode()).hexdigest())
        .with_for_update()
    )
    if (
        flow is None
        or flow.account_id != ctx.account_id
        or flow.session_id != ctx.session_id
        or flow.consumed_at is not None
        or utc(flow.expires_at) <= datetime.now(UTC)
    ):
        raise GitLabError("invalid_connection_state", status=403)
    organization_id = flow.connection_organization_id
    connection = settings.gitlab.connections.get(organization_id)
    locale, callback_uri = flow.locale, flow.callback_uri
    flow.consumed_at = datetime.now(UTC)
    # A code exchange must never run twice after a lost callback response.
    await db.commit()
    await db.scalar(select(Account).where(Account.id == ctx.account_id).with_for_update())
    if connection is None:
        raise GitLabError("connector_not_configured")
    client = client_for(connection)
    row = await db.scalar(
        select(GitLabConnector)
        .where(
            GitLabConnector.account_id == ctx.account_id,
            GitLabConnector.gitlab_base_url == client.base_url,
            GitLabConnector.purpose == PURPOSE,
        )
        .with_for_update()
    )
    if row is None:
        row = GitLabConnector(
            id=str(uuid4()),
            account_id=ctx.account_id,
            gitlab_base_url=client.base_url,
            connection_organization_id=organization_id,
            purpose=PURPOSE,
            gitlab_subject="",
            authorization_revision=str(uuid4()),
            state="disconnected",
            projects=[],
        )
        db.add(row)
    row.connection_organization_id = organization_id
    reason: str | None = None
    try:
        credentials = settings.gitlab.connector_credentials(organization_id)
        if credentials is None or not settings.gitlab.connector_enabled(organization_id):
            raise GitLabError("connector_not_configured")
        if not code:
            raise GitLabError("reauthorization_required", status=401)
        exchanged = await client.oauth_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback_uri,
                "client_id": credentials[0],
                "client_secret": credentials[1],
            }
        )
        token, _refresh, _expires = grant_fields(exchanged)
        identity = await client.user(token=token)
        subject = qualified_subject(client.base_url, identity.user_id)
        if subject not in await _linked_subjects(db, ctx.account_id):
            raise GitLabError("gitlab_identity_mismatch", status=403)
        projects = await member_projects(client, token=token)
        row.gitlab_subject = subject
        await store_grant(row, exchanged, settings=settings.gitlab)
        row.projects = _project_scope(projects)
        row.state = "connected"
    except GitLabError as error:
        reason = error.reason
        row.state = "reauthorization_required"
    if row.state != "connected":
        row.token_ciphertext = None
        row.refresh_token_ciphertext = None
        row.expires_at = None
        row.projects = []
    row.authorization_revision = str(uuid4())
    row.updated_at = datetime.now(UTC)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="gitlab.connector_completed",
        target_table="gitlab_connector",
        target_id=row.id,
        reason=reason,
        payload={"outcome": row.state},
    )
    return locale, row.state


def _repository_view(repository: GitLabRepository) -> GitLabConnectorRepository:
    return GitLabConnectorRepository(
        project_id=repository.repository_id,
        namespace_id=repository.namespace_id,
        path_with_namespace=repository.path_with_namespace,
        repository_url=repository.repository_url,
        visibility=cast(Literal["private", "internal", "public"] | None, repository.visibility),
        default_branch=repository.default_branch,
    )


async def _attach_platform_objects(
    db: AsyncSession, *, account_id: str, repositories: list[GitLabConnectorRepository]
) -> list[GitLabConnectorRepository]:
    project_ids = {repository.project_id for repository in repositories}
    if not project_ids:
        return repositories
    rows = (
        await db.execute(
            select(GitLabSourceBinding, PublicationPlan)
            .join(
                PublicationPlan,
                PublicationPlan.gitlab_source_binding_id == GitLabSourceBinding.id,
            )
            .where(
                GitLabSourceBinding.account_id == account_id,
                GitLabSourceBinding.project_id.in_(project_ids),
                PublicationPlan.state == "published",
            )
        )
    ).all()
    by_project: dict[int, list[GitLabPlatformObject]] = {}
    for binding, plan in rows:
        name = plan.passport.get("name")
        by_project.setdefault(binding.project_id, []).append(
            GitLabPlatformObject(
                object_kind=plan.object_kind,  # type: ignore[arg-type]
                stable_id=plan.stable_id,
                version=plan.version,
                name=name if isinstance(name, str) and name else plan.stable_id,
                visibility=plan.visibility,  # type: ignore[arg-type]
            )
        )
    return [
        repository.model_copy(
            update={"platform_objects": by_project.get(repository.project_id, [])}
        )
        for repository in repositories
    ]


async def read_status(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    settings: Settings,
    client: GitLabClient,
) -> GitLabConnectorStatus:
    configured = settings.gitlab.connector_enabled(organization_id)
    row = await db.scalar(
        select(GitLabConnector).where(
            GitLabConnector.account_id == ctx.account_id,
            GitLabConnector.gitlab_base_url == client.base_url,
            GitLabConnector.purpose == PURPOSE,
        )
    )
    status = GitLabConnectionStatus(
        purpose="source",
        configured=configured,
        gitlab_base_url=client.base_url,
        state="disconnected"
        if row is None
        else cast(Literal["disconnected", "connected", "reauthorization_required"], row.state),
        expires_at=None
        if row is None or row.expires_at is None
        else format_timestamp(utc(row.expires_at)),
    )
    if configured and row is not None and row.state == "connected":
        try:
            connector, token = await load_connector(
                db,
                account_id=ctx.account_id,
                gitlab_base_url=client.base_url,
                client=client,
                settings=settings.gitlab,
                lock=True,
            )
            if connector.gitlab_subject not in await _linked_subjects(db, ctx.account_id):
                raise GitLabError("gitlab_identity_mismatch", status=403)
            repositories = await member_projects(client, token=token)
            row.projects = _project_scope(repositories)
            status = status.model_copy(
                update={
                    "repositories": await _attach_platform_objects(
                        db,
                        account_id=ctx.account_id,
                        repositories=[_repository_view(item) for item in repositories],
                    )
                }
            )
        except GitLabError as error:
            if error.status in {401, 403}:
                row.state = "reauthorization_required"
                row.token_ciphertext = None
                row.refresh_token_ciphertext = None
                row.projects = []
                await emit_audit(
                    db,
                    actor_account_id=ctx.account_id,
                    organization_id=organization_id,
                    action="gitlab.connector_unavailable",
                    target_table="gitlab_connector",
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
    return GitLabConnectorStatus(connections=[status])


async def disconnect(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, gitlab_base_url: str
) -> None:
    row = await db.scalar(
        select(GitLabConnector)
        .where(
            GitLabConnector.account_id == ctx.account_id,
            GitLabConnector.gitlab_base_url == gitlab_base_url,
            GitLabConnector.purpose == PURPOSE,
        )
        .with_for_update()
    )
    if row is not None and row.state != "disconnected":
        row.token_ciphertext = None
        row.refresh_token_ciphertext = None
        row.expires_at = None
        row.state = "disconnected"
        row.projects = []
        row.authorization_revision = str(uuid4())
        row.updated_at = datetime.now(UTC)
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            organization_id=organization_id,
            action="gitlab.connector_disconnected",
            target_table="gitlab_connector",
            target_id=row.id,
        )


def source_response(binding: GitLabSourceBinding) -> GitLabSourcePrepared:
    return GitLabSourcePrepared(
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
    organization_id: str,
    body: GitLabSourcePrepareRequest,
    settings: Settings,
    client: GitLabClient,
    store: ImmutableObjectStore,
) -> GitLabSourcePrepared:
    try:
        subpath = canonical_subpath(body.subpath)
    except SourceError:
        raise GitLabError("invalid_component_subpath", status=400) from None
    connector, token = await load_connector(
        db,
        account_id=ctx.account_id,
        gitlab_base_url=client.base_url,
        client=client,
        settings=settings.gitlab,
        lock=True,
    )
    if connector.gitlab_subject not in await _linked_subjects(db, ctx.account_id):
        raise GitLabError("gitlab_identity_mismatch", status=403)
    repository = await require_project(client, token=token, project_id=body.project_id)
    request_hash = request_digest(body.model_dump(mode="json", exclude={"idempotency_key"}))
    existing = await db.scalar(
        select(GitLabSourceBinding).where(
            GitLabSourceBinding.account_id == ctx.account_id,
            GitLabSourceBinding.idempotency_key == body.idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise GitLabError("idempotency_conflict", status=409)
        payload = await store.read_by_digest(
            existing.content_digest,
            expected_size=existing.size_bytes,
            owner_account_id=ctx.account_id,
        )
        if payload is None:
            raise GitLabError("source_artifact_unavailable")
        return source_response(existing)
    if await client.head_revision(repository.repository_id, body.commit, token=token) != (
        body.commit
    ):
        raise GitLabError("source_snapshot_refused", status=400)
    try:
        archive = await client.archive(repository.repository_id, sha=body.commit, token=token)
        files = extract_component_files(
            archive, subpath=subpath, max_archive_bytes=MAX_GIT_ARCHIVE_BYTES
        )
    except (GitLabError, SourceError):
        raise GitLabError("source_snapshot_refused", status=400) from None
    if len(files) > 1000:
        raise GitLabError("source_inventory_too_large", status=400)
    payload = pack_component_tree(files)
    content_digest = digest_bytes("ai-stp:artifact:v1", payload)
    await store.put_immutable(
        payload,
        expected_digest=content_digest,
        expected_size=len(payload),
        owner_account_id=ctx.account_id,
    )
    binding = GitLabSourceBinding(
        id=str(uuid4()),
        account_id=ctx.account_id,
        connector_id=connector.id,
        gitlab_base_url=client.base_url,
        project_id=repository.repository_id,
        namespace_id=repository.namespace_id,
        path_with_namespace=repository.path_with_namespace,
        commit=body.commit,
        subpath=subpath,
        source_visibility="public" if repository.visibility == "public" else "private",
        content_digest=content_digest,
        size_bytes=len(payload),
        inventory=sorted(files),
        request_hash=request_hash,
        idempotency_key=body.idempotency_key,
    )
    db.add(binding)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="gitlab.source_prepared",
        target_table="gitlab_source_binding",
        target_id=binding.id,
        payload={"content_digest": content_digest, "source_visibility": binding.source_visibility},
    )
    return source_response(binding)
