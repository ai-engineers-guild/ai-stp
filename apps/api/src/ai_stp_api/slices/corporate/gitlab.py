"""GitLab discovery over retained provider identities; project links stay explicit."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, get_settings, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.corporate import service
from ai_stp_api.slices.technology import detection
from ai_stp_api.slices.technology.forge import language_handoff
from ai_stp_contracts.context import ProviderProjectId, RemoteProjectId
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.gitlab import (
    GitLabEnrichRequest,
    GitLabMutationRequest,
    GitLabRepositoryList,
    GitLabRepositoryView,
)
from ai_stp_contracts.technology import (
    TechnologyScanHandoff,
    TechnologyScanRequest,
    TechnologyScanResult,
)
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp
from ai_stp_platform.gitlab_client import GitLabClient, GitLabError, GitLabRepository
from ai_stp_platform.organization_models import (
    CorporateProject,
    Organization,
    ProjectIdentity,
    ProjectLink,
)
from ai_stp_platform.technology_models import TechnologyScan

router = APIRouter(tags=["corporate"])


def _connection(settings: Settings, organization_id: str) -> tuple[GitLabClient, str]:
    config = settings.gitlab.connections.get(organization_id)
    if config is None:
        raise ApiError(ErrorCategory.DEPENDENCY, "GitLab discovery is unavailable")
    try:
        client = GitLabClient(config.base_url, allowed_hosts=config.allowed_hosts)
    except GitLabError:
        raise ApiError(ErrorCategory.DEPENDENCY, "GitLab discovery is unavailable") from None
    return client, config.token.get_secret_value()


def _upstream(error: GitLabError) -> ApiError:
    if error.reason == "gitlab_repository_inaccessible":
        return ApiError(ErrorCategory.PERMISSION, "GitLab repository is unavailable")
    if error.reason in {"invalid_gitlab_response", "gitlab_response_too_large"}:
        return ApiError(ErrorCategory.DEPENDENCY, "GitLab returned invalid metadata")
    return ApiError(ErrorCategory.DEPENDENCY, "GitLab discovery is unavailable")


def _view(
    organization_id: str, repository: GitLabRepository, identity: ProjectIdentity | None = None
) -> GitLabRepositoryView:
    return GitLabRepositoryView(
        organization_id=organization_id,
        repository_id=repository.repository_id,
        namespace_id=repository.namespace_id,
        path_with_namespace=repository.path_with_namespace,
        repository_url=repository.repository_url,
        default_branch=repository.default_branch,
        last_activity_at=repository.last_activity_at,
        observed_revision=identity.provider_observed_revision if identity else None,
        observed_at=format_timestamp(identity.observed_at)
        if identity and identity.observed_at
        else None,
        provider_project_id=identity.id if identity else None,
        connected=bool(identity and identity.provider_installation_id),
        identity_revision=identity.revision if identity else None,
    )


def _retained_view(organization_id: str, identity: ProjectIdentity) -> GitLabRepositoryView:
    if (
        identity.current_url is None
        or identity.observed_name is None
        or identity.provider_namespace_id is None
        or identity.immutable_repository_id is None
    ):
        raise ApiError(ErrorCategory.CONFLICT, "GitLab observation is incomplete")
    return GitLabRepositoryView(
        organization_id=organization_id,
        repository_id=int(identity.immutable_repository_id),
        namespace_id=int(identity.provider_namespace_id),
        path_with_namespace=identity.observed_name,
        repository_url=identity.current_url,
        default_branch=identity.provider_default_branch,
        observed_revision=identity.provider_observed_revision,
        observed_at=format_timestamp(identity.observed_at) if identity.observed_at else None,
        provider_project_id=identity.id,
        connected=identity.provider_installation_id is not None,
        identity_revision=identity.revision,
    )


async def _finish(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: GitLabMutationRequest,
    operation: str,
    fingerprint: str,
    response: GitLabRepositoryView,
) -> None:
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action=operation,
        target_table="project_identity",
        target_id=response.provider_project_id or organization_id,
        payload={"repository_id": response.repository_id, "revision": response.identity_revision},
    )


def _fingerprint(operation: str, target: str, payload: GitLabMutationRequest) -> str:
    return service.mutation_fingerprint(
        {"operation": operation, "target": target, "expected_revision": payload.expected_revision}
    )


@router.get(
    "/corporate/organizations/{organization_id}/gitlab/repositories",
    response_model=GitLabRepositoryList,
)
async def list_repositories(
    organization_id: OrganizationId,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> GitLabRepositoryList:
    await service.authorize(db, ctx=ctx, organization_id=organization_id, permission="project.list")
    client, token = _connection(settings, organization_id)
    try:
        repositories = await client.list_repositories(token=token, limit=limit)
    except GitLabError as error:
        raise _upstream(error) from None
    keys = {f"{client.base_url}:{repository.repository_id}" for repository in repositories}
    identities = await db.scalars(
        select(ProjectIdentity).where(
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.namespace == "provider",
            ProjectIdentity.provider_kind == "gitlab",
            ProjectIdentity.external_key.in_(keys),
        )
    )
    by_key = {identity.external_key: identity for identity in identities}
    items = [
        _view(
            organization_id,
            repository,
            by_key.get(f"{client.base_url}:{repository.repository_id}"),
        )
        for repository in repositories
    ]
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="gitlab.repository.list",
        target_table="project_identity",
        target_id=organization_id,
        payload={"count": len(items)},
    )
    await db.commit()
    return GitLabRepositoryList(organization_id=organization_id, total=len(items), items=items)


@router.post(
    "/corporate/organizations/{organization_id}/gitlab/repositories/{repository_id}",
    response_model=GitLabRepositoryView,
)
async def register_repository(
    organization_id: OrganizationId,
    repository_id: int,
    payload: GitLabMutationRequest,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GitLabRepositoryView:
    await service.authorize(
        db, ctx=ctx, organization_id=organization_id, permission="project.create"
    )
    client, token = _connection(settings, organization_id)
    operation = "gitlab.repository.register"
    target = f"{client.base_url}:{repository_id}"
    fingerprint = _fingerprint(operation, target, payload)
    organization, receipt = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.create",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
    )
    if receipt is not None:
        await db.commit()
        return GitLabRepositoryView.model_validate(receipt.response_body)
    existing = await db.scalar(
        select(ProjectIdentity).where(
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.namespace == "provider",
            ProjectIdentity.external_key == target,
        )
    )
    if existing is None and payload.expected_revision != 0:
        raise ApiError(ErrorCategory.PRECONDITION, "repository observation changed")
    if existing is not None and (
        existing.provider_kind != "gitlab"
        or existing.state != "active"
        or existing.provider_installation_id is not None
        or existing.revision != payload.expected_revision
    ):
        raise ApiError(ErrorCategory.CONFLICT, "repository observation already exists or changed")
    try:
        repository = await client.repository(repository_id, token=token)
        revision = (
            await client.head_revision(repository_id, repository.default_branch, token=token)
            if repository.default_branch
            else None
        )
    except GitLabError as error:
        raise _upstream(error) from None
    identity = existing
    if identity is None:
        identity = ProjectIdentity(
            id=new_id("provider_project"),
            organization_id=organization_id,
            namespace="provider",
            external_key=target,
            provider_kind="gitlab",
            immutable_repository_id=str(repository.repository_id),
            revision=1,
            state="active",
        )
        db.add(identity)
    else:
        identity.revision += 1
    identity.display_name = repository.path_with_namespace
    identity.provider_installation_id = client.base_url
    identity.provider_namespace_id = str(repository.namespace_id)
    identity.current_url = repository.repository_url
    identity.observed_name = repository.path_with_namespace
    identity.observed_at = datetime.now(UTC)
    identity.provider_default_branch = repository.default_branch
    identity.provider_observed_revision = revision
    await _sync_linked_activity(
        db,
        organization_id=organization_id,
        provider_project_id=identity.id,
        repository=repository,
    )
    organization.policy_revision += 1
    await db.flush()
    response = _view(organization_id, repository, identity)
    await _finish(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        fingerprint=fingerprint,
        response=response,
    )
    await db.commit()
    return response


async def _identity(
    db: AsyncSession, organization_id: str, provider_project_id: str, base_url: str
) -> ProjectIdentity:
    row = await db.get(ProjectIdentity, provider_project_id)
    if (
        row is None
        or row.organization_id != organization_id
        or row.namespace != "provider"
        or row.provider_kind != "gitlab"
        or row.state != "active"
        or not row.external_key.startswith(f"{base_url}:")
    ):
        raise ApiError(ErrorCategory.PERMISSION, "GitLab repository is unavailable")
    return row


async def _sync_linked_activity(
    db: AsyncSession,
    *,
    organization_id: str,
    provider_project_id: str,
    repository: GitLabRepository,
) -> None:
    """Refresh canonical landscape activity only for explicit project links."""
    projects = await db.scalars(
        select(CorporateProject)
        .join(
            ProjectLink,
            (ProjectLink.organization_id == CorporateProject.organization_id)
            & (ProjectLink.remote_project_id == CorporateProject.id),
        )
        .where(
            CorporateProject.organization_id == organization_id,
            ProjectLink.provider_project_id == provider_project_id,
            ProjectLink.state == "linked",
        )
    )
    for project in projects:
        activity_at = (
            parse_timestamp(repository.last_activity_at) if repository.last_activity_at else None
        )
        if (
            project.repository_activity_at != activity_at
            or project.source_availability != "available"
        ):
            project.repository_activity_at = activity_at
            project.source_availability = "available"
            project.revision += 1


@router.post(
    "/corporate/organizations/{organization_id}/gitlab/observations/{provider_project_id}/refresh",
    response_model=GitLabRepositoryView,
)
async def refresh_repository(
    organization_id: OrganizationId,
    provider_project_id: ProviderProjectId,
    payload: GitLabMutationRequest,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GitLabRepositoryView:
    await service.authorize(
        db, ctx=ctx, organization_id=organization_id, permission="project.update"
    )
    client, token = _connection(settings, organization_id)
    operation = "gitlab.repository.refresh"
    fingerprint = _fingerprint(operation, provider_project_id, payload)
    organization, receipt = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.update",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
    )
    if receipt is not None:
        await db.commit()
        return GitLabRepositoryView.model_validate(receipt.response_body)
    row = await _identity(db, organization_id, provider_project_id, client.base_url)
    if row.revision != payload.expected_revision or row.provider_installation_id is None:
        raise ApiError(ErrorCategory.PRECONDITION, "GitLab observation changed or disconnected")
    if row.immutable_repository_id is None:
        raise ApiError(ErrorCategory.CONFLICT, "GitLab repository identity is incomplete")
    try:
        repository_id = int(row.immutable_repository_id)
    except ValueError:
        raise ApiError(ErrorCategory.CONFLICT, "GitLab repository identity is incomplete") from None
    try:
        repository = await client.repository(repository_id, token=token)
        revision = (
            await client.head_revision(repository_id, repository.default_branch, token=token)
            if repository.default_branch
            else None
        )
    except GitLabError as error:
        raise _upstream(error) from None
    row.display_name = repository.path_with_namespace
    row.provider_namespace_id = str(repository.namespace_id)
    row.current_url = repository.repository_url
    row.observed_name = repository.path_with_namespace
    row.observed_at = datetime.now(UTC)
    row.provider_default_branch = repository.default_branch
    row.provider_observed_revision = revision
    row.revision += 1
    await _sync_linked_activity(
        db,
        organization_id=organization_id,
        provider_project_id=provider_project_id,
        repository=repository,
    )
    organization.policy_revision += 1
    await db.flush()
    response = _view(organization_id, repository, row)
    await _finish(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        fingerprint=fingerprint,
        response=response,
    )
    await db.commit()
    return response


@router.post(
    "/corporate/organizations/{organization_id}/gitlab/observations/{provider_project_id}/disconnect",
    response_model=GitLabRepositoryView,
)
async def disconnect_repository(
    organization_id: OrganizationId,
    provider_project_id: ProviderProjectId,
    payload: GitLabMutationRequest,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GitLabRepositoryView:
    await service.authorize(
        db, ctx=ctx, organization_id=organization_id, permission="project.update"
    )
    client, _ = _connection(settings, organization_id)
    operation = "gitlab.repository.disconnect"
    fingerprint = _fingerprint(operation, provider_project_id, payload)
    organization, receipt = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.update",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
    )
    if receipt is not None:
        await db.commit()
        return GitLabRepositoryView.model_validate(receipt.response_body)
    row = await _identity(db, organization_id, provider_project_id, client.base_url)
    if row.revision != payload.expected_revision or row.provider_installation_id is None:
        raise ApiError(ErrorCategory.PRECONDITION, "GitLab observation changed or disconnected")
    row.provider_installation_id = None
    row.revision += 1
    organization.policy_revision += 1
    await db.flush()
    response = _retained_view(organization_id, row)
    await _finish(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        fingerprint=fingerprint,
        response=response,
    )
    await db.commit()
    return response


@router.post(
    "/corporate/organizations/{organization_id}/gitlab/observations/"
    "{provider_project_id}/projects/{project_id}/enrich",
    response_model=TechnologyScanResult,
)
async def enrich_languages(
    organization_id: OrganizationId,
    provider_project_id: ProviderProjectId,
    project_id: RemoteProjectId,
    payload: GitLabEnrichRequest,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TechnologyScanResult:
    await service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="technology.scan.publish",
        scope_kind="project",
        scope_id=project_id,
    )
    client, token = _connection(settings, organization_id)
    identity = await _identity(db, organization_id, provider_project_id, client.base_url)
    link = await db.scalar(
        select(ProjectLink).where(
            ProjectLink.organization_id == organization_id,
            ProjectLink.provider_project_id == provider_project_id,
            ProjectLink.remote_project_id == project_id,
            ProjectLink.state == "linked",
        )
    )
    if link is None or identity.provider_installation_id != client.base_url:
        raise ApiError(ErrorCategory.PERMISSION, "linked GitLab project is unavailable")
    retained_scan = await db.get(TechnologyScan, (organization_id, payload.scan_id))
    if retained_scan is not None:
        retained_handoff = TechnologyScanHandoff.model_validate(retained_scan.handoff["handoff"])
        if (
            retained_scan.project_id != project_id
            or retained_handoff.scope != f"gitlab/{provider_project_id}"
            or retained_handoff.mapping_version != payload.mapping_version
        ):
            raise ApiError(ErrorCategory.CONFLICT, "scan ID was reused")
        result = await detection.publish_scan(
            db,
            ctx=ctx,
            organization_id=organization_id,
            project_id=project_id,
            payload=TechnologyScanRequest(
                authorization_revision=payload.authorization_revision,
                expected_revision=payload.expected_revision,
                idempotency_key=payload.idempotency_key,
                handoff=retained_handoff,
            ),
            request_id=None,
        )
        await db.commit()
        return result
    if identity.provider_default_branch is None or identity.provider_observed_revision is None:
        raise ApiError(ErrorCategory.PRECONDITION, "GitLab default branch has no observed revision")
    if identity.immutable_repository_id is None or identity.observed_at is None:
        raise ApiError(ErrorCategory.CONFLICT, "GitLab observation is incomplete")
    try:
        repository_id = int(identity.immutable_repository_id)
    except ValueError:
        raise ApiError(ErrorCategory.CONFLICT, "GitLab repository identity is incomplete") from None
    expected_identity_revision = identity.revision
    try:
        head = await client.head_revision(
            repository_id, identity.provider_default_branch, token=token
        )
        languages = await client.languages(repository_id, token=token)
    except GitLabError as error:
        raise _upstream(error) from None
    if head != identity.provider_observed_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "GitLab observation requires refresh")
    locked = await db.scalar(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )
    if locked is None:
        raise ApiError(ErrorCategory.PERMISSION, "organization access denied")
    await db.refresh(identity)
    await db.refresh(link)
    if (
        identity.revision != expected_identity_revision
        or identity.provider_installation_id != client.base_url
        or identity.provider_observed_revision != head
        or link.state != "linked"
    ):
        raise ApiError(ErrorCategory.PRECONDITION, "GitLab observation or project link changed")
    handoff = await language_handoff(
        db,
        organization_id=organization_id,
        project_id=project_id,
        scan_id=payload.scan_id,
        mapping_version=payload.mapping_version,
        provider="gitlab",
        provider_project_id=provider_project_id,
        repository_id=repository_id,
        head=head,
        observed_at=format_timestamp(identity.observed_at),
        languages=languages,
    )
    result = await detection.publish_scan(
        db,
        ctx=ctx,
        organization_id=organization_id,
        project_id=project_id,
        payload=TechnologyScanRequest(
            authorization_revision=payload.authorization_revision,
            expected_revision=payload.expected_revision,
            idempotency_key=payload.idempotency_key,
            handoff=handoff,
        ),
        request_id=None,
    )
    await db.commit()
    return result
