"""Explicit web repository bindings; public GitHub needs no account credential."""

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, get_settings, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.corporate import gitlab, service
from ai_stp_contracts.corporate import (
    CorporateProjectView,
    CorporateRepositoryBindRequest,
    CorporateRepositoryPlan,
    CorporateRepositoryPlanRequest,
    OrganizationId,
)
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp
from ai_stp_platform.github_client import GitHubClient, GitHubError, object_data
from ai_stp_platform.gitlab_client import GitLabError
from ai_stp_platform.organization_models import (
    CorporateMutationReceipt,
    CorporateProject,
    CorporateRepositoryBinding,
    ProjectIdentity,
)
from ai_stp_platform.repository_bindings import repository_links

router = APIRouter(tags=["corporate"])


def repository_coordinates(value: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ApiError(ErrorCategory.VALIDATION, "Repository URL is invalid") from None
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or port not in (None, 443)
    ):
        raise ApiError(
            ErrorCategory.VALIDATION,
            "Use an HTTPS repository URL without credentials, query or fragment",
        )
    path = parsed.path.strip("/").removesuffix(".git")
    if (
        not parsed.hostname
        or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", path)
        or any(part in (".", "..") for part in path.split("/"))
    ):
        raise ApiError(
            ErrorCategory.VALIDATION,
            "Use a repository URL, for example https://github.com/owner/repository",
        )
    if parsed.hostname == "github.com" and path.count("/") != 1:
        raise ApiError(
            ErrorCategory.VALIDATION, "Use the GitHub repository URL without a branch or file path"
        )
    return f"https://{parsed.hostname}", path


async def resolve_repository(url: str, settings: Settings, organization_id: str) -> dict[str, str]:
    base, path = repository_coordinates(url)
    try:
        if base == "https://github.com":
            client = GitHubClient()
            data = object_data((await client.api("GET", f"/repos/{path}", token=None)).data)
            if data.get("private") is not False or data.get("visibility", "public") != "public":
                raise ApiError(
                    ErrorCategory.PERMISSION, "Only public GitHub repositories can be linked here"
                )
            repository_id, owner = data.get("id"), object_data(data.get("owner"))
            name, branch = data.get("full_name"), data.get("default_branch")
            namespace_id = owner.get("id")
            if (
                type(repository_id) is not int
                or type(namespace_id) is not int
                or not isinstance(name, str)
                or not isinstance(branch, str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name)
            ):
                raise ApiError(
                    ErrorCategory.DEPENDENCY, "GitHub returned invalid repository metadata"
                )
            commits = (
                await client.api(
                    "GET",
                    f"/repos/{name}/commits",
                    token=None,
                    params={"sha": branch, "per_page": 1},
                )
            ).data
            if not isinstance(commits, list) or len(cast(list[object], commits)) != 1:
                raise ApiError(ErrorCategory.VALIDATION, "Repository must contain a commit")
            head = object_data(cast(list[object], commits)[0]).get("sha")
            if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head):
                raise ApiError(ErrorCategory.DEPENDENCY, "GitHub returned invalid commit metadata")
            return {
                "provider": "github",
                "repository_url": f"https://github.com/{name}",
                "repository_id": str(repository_id),
                "namespace_id": str(namespace_id),
                "name": name,
                "default_branch": branch,
                "observed_revision": head,
            }
        client, token = gitlab._connection(settings, organization_id)  # pyright: ignore[reportPrivateUsage]
        if base != client.base_url.rstrip("/"):
            raise ApiError(
                ErrorCategory.VALIDATION,
                "Use GitHub or the GitLab host configured for this organization",
            )
        repositories = await client.list_repositories(token=token, limit=500)
        repository = next((item for item in repositories if item.path_with_namespace == path), None)
        if repository is None or not repository.default_branch:
            raise ApiError(
                ErrorCategory.NOT_FOUND,
                "Repository is unavailable on the configured GitLab connection",
            )
        head = await client.head_revision(
            repository.repository_id, repository.default_branch, token=token
        )
        return {
            "provider": "gitlab",
            "repository_url": repository.repository_url,
            "repository_id": str(repository.repository_id),
            "namespace_id": str(repository.namespace_id),
            "name": repository.path_with_namespace,
            "default_branch": repository.default_branch,
            "observed_revision": head,
        }
    except (GitHubError, GitLabError):
        raise ApiError(
            ErrorCategory.DEPENDENCY,
            "Repository could not be read. Check its URL, public access and provider availability",
        ) from None
    except ValueError:
        raise ApiError(ErrorCategory.VALIDATION, "Repository URL is invalid") from None


async def require_unbound(db: AsyncSession, organization_id: str, project_id: str) -> None:
    sources = repository_links().c
    if (
        await db.scalar(
            select(sources.provider_project_id).where(
                sources.organization_id == organization_id,
                sources.remote_project_id == project_id,
                sources.state == "linked",
                sources.provider_project_id.is_not(None),
            )
        )
        is not None
    ):
        raise ApiError(ErrorCategory.CONFLICT, "Project already has a linked repository")


@router.post(
    "/corporate/organizations/{organization_id}/projects/{project_id}/repository-plan",
    response_model=CorporateRepositoryPlan,
)
async def plan_repository(
    organization_id: OrganizationId,
    project_id: str,
    payload: CorporateRepositoryPlanRequest,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CorporateRepositoryPlan:
    fingerprint = service.mutation_fingerprint(
        {"project_id": project_id, **payload.model_dump(exclude={"idempotency_key"})}
    )
    _, receipt = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.update",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="project.repository.plan",
        fingerprint=fingerprint,
        scope_kind="project",
        scope_id=project_id,
    )
    if receipt is not None:
        return CorporateRepositoryPlan.model_validate(receipt.response_body)
    project = await db.get(CorporateProject, project_id)
    if project is None or project.organization_id != organization_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "Project not found")
    if project.revision != payload.expected_revision or project.lifecycle != "active":
        raise ApiError(ErrorCategory.PRECONDITION, "Project changed; refresh before linking")
    await require_unbound(db, organization_id, project_id)
    values = dict(
        project_id=project_id,
        **await resolve_repository(payload.repository_url, settings, organization_id),
        expected_revision=payload.expected_revision,
        authorization_revision=payload.authorization_revision,
        plan_key=payload.idempotency_key,
        expires_at=format_timestamp(datetime.now(UTC) + timedelta(minutes=15)),
    )
    digest = service.mutation_fingerprint(
        {"organization_id": organization_id, "actor_account_id": ctx.account_id, **values}
    )
    result = CorporateRepositoryPlan(
        project_id=project_id,
        repository_url=str(values["repository_url"]),
        provider=cast(Literal["github", "gitlab"], values["provider"]),
        repository_id=str(values["repository_id"]),
        namespace_id=str(values["namespace_id"]),
        name=str(values["name"]),
        default_branch=str(values["default_branch"]),
        observed_revision=str(values["observed_revision"]),
        expected_revision=payload.expected_revision,
        authorization_revision=payload.authorization_revision,
        plan_key=payload.idempotency_key,
        expires_at=str(values["expires_at"]),
        plan_digest=digest,
    )
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="project.repository.plan",
        fingerprint=fingerprint,
        response=result,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.repository.plan",
        target_table="corporate_project",
        target_id=project_id,
        payload={"plan_digest": result.plan_digest},
    )
    await db.commit()
    return result


@router.post(
    "/corporate/organizations/{organization_id}/projects/{project_id}/repository",
    response_model=CorporateProjectView,
)
async def bind_repository(
    organization_id: OrganizationId,
    project_id: str,
    payload: CorporateRepositoryBindRequest,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CorporateProjectView:
    fingerprint = service.mutation_fingerprint(
        {"project_id": project_id, **payload.model_dump(exclude={"idempotency_key"})}
    )
    organization, replay = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.update",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="project.repository.bind",
        fingerprint=fingerprint,
        scope_kind="project",
        scope_id=project_id,
    )
    if replay is not None:
        return CorporateProjectView.model_validate(replay.response_body)
    receipt = await db.get(CorporateMutationReceipt, (organization_id, payload.plan_key))
    if receipt is None or receipt.operation != "project.repository.plan":
        raise ApiError(ErrorCategory.NOT_FOUND, "Repository plan not found")
    plan = CorporateRepositoryPlan.model_validate(receipt.response_body)
    values = plan.model_dump(exclude={"plan_digest"})
    expected = service.mutation_fingerprint(
        {"organization_id": organization_id, "actor_account_id": ctx.account_id, **values}
    )
    if (
        plan.project_id != project_id
        or plan.plan_digest != payload.plan_digest
        or expected != payload.plan_digest
        or plan.authorization_revision != payload.authorization_revision
        or parse_timestamp(plan.expires_at) <= datetime.now(UTC)
    ):
        raise ApiError(
            ErrorCategory.PRECONDITION,
            "Repository plan changed or expired; check the repository again",
        )
    project = await db.get(CorporateProject, project_id)
    if (
        project is None
        or project.organization_id != organization_id
        or project.revision != plan.expected_revision
        or project.lifecycle != "active"
    ):
        raise ApiError(ErrorCategory.PRECONDITION, "Project changed; refresh before linking")
    await require_unbound(db, organization_id, project_id)
    metadata = await resolve_repository(plan.repository_url, settings, organization_id)
    if any(metadata[key] != values[key] for key in metadata):
        raise ApiError(
            ErrorCategory.PRECONDITION, "Repository changed; check it again before linking"
        )
    external_key = f"{urlsplit(plan.repository_url).netloc}:{plan.repository_id}"
    identity = await db.scalar(
        select(ProjectIdentity).where(
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.namespace == "provider",
            ProjectIdentity.external_key == external_key,
        )
    )
    if identity is None:
        identity = ProjectIdentity(
            id=new_id("provider_project"),
            organization_id=organization_id,
            namespace="provider",
            external_key=external_key,
            display_name=plan.name,
            provider_kind=plan.provider,
            provider_installation_id="public"
            if plan.provider == "github"
            else repository_coordinates(plan.repository_url)[0],
            provider_namespace_id=plan.namespace_id,
            immutable_repository_id=plan.repository_id,
            current_url=plan.repository_url,
            observed_name=plan.name,
            observed_at=datetime.now(UTC),
            provider_default_branch=plan.default_branch,
            provider_observed_revision=plan.observed_revision,
            revision=1,
            state="active",
        )
        db.add(identity)
        await db.flush()
    elif (
        identity.state != "active"
        or identity.provider_installation_id
        != (
            "public"
            if plan.provider == "github"
            else repository_coordinates(plan.repository_url)[0]
        )
        or identity.current_url != plan.repository_url
    ):
        raise ApiError(ErrorCategory.CONFLICT, "Repository observation changed")
    identity.provider_default_branch = plan.default_branch
    identity.provider_observed_revision = plan.observed_revision
    identity.observed_at = datetime.now(UTC)
    db.add(
        CorporateRepositoryBinding(
            organization_id=organization_id,
            remote_project_id=project_id,
            provider_project_id=identity.id,
            actor_account_id=ctx.account_id,
            plan_digest=plan.plan_digest,
            state="linked",
        )
    )
    project.revision += 1
    organization.policy_revision += 1
    await db.flush()
    result = await service.read_project(
        db, ctx=ctx, organization_id=organization_id, project_id=project_id, request_id=None
    )
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="project.repository.bind",
        fingerprint=fingerprint,
        response=result,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.repository.bind",
        target_table="corporate_project",
        target_id=project_id,
        payload={"provider_project_id": identity.id, "plan_digest": plan.plan_digest},
    )
    await db.commit()
    return result
