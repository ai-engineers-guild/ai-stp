"""GitHub language enrichment for explicitly linked corporate projects."""

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, get_settings, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.corporate import service
from ai_stp_api.slices.github_connector.router import get_client
from ai_stp_api.slices.github_connector.service import (
    _linked_subject,  # pyright: ignore[reportPrivateUsage]
    api_error,
)
from ai_stp_api.slices.technology import detection
from ai_stp_api.slices.technology.forge import language_handoff
from ai_stp_contracts.context import ProviderProjectId, RemoteProjectId
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.gitlab import GitLabEnrichRequest
from ai_stp_contracts.technology import (
    TechnologyScanHandoff,
    TechnologyScanRequest,
    TechnologyScanResult,
)
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.github_authority import load_connector, require_repository
from ai_stp_platform.github_client import GitHubClient, GitHubError, object_data
from ai_stp_platform.organization_models import Organization, ProjectIdentity, ProjectLink
from ai_stp_platform.technology_models import TechnologyScan

router = APIRouter(tags=["corporate"])


@router.post(
    "/corporate/organizations/{organization_id}/github/observations/"
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
    client: Annotated[GitHubClient, Depends(get_client)],
) -> TechnologyScanResult:
    await service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="technology.scan.publish",
        scope_kind="project",
        scope_id=project_id,
    )
    identity = await db.scalar(
        select(ProjectIdentity).where(
            ProjectIdentity.id == provider_project_id,
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.namespace == "provider",
            ProjectIdentity.provider_kind == "github",
            ProjectIdentity.state == "active",
        )
    )
    link = await db.scalar(
        select(ProjectLink).where(
            ProjectLink.organization_id == organization_id,
            ProjectLink.provider_project_id == provider_project_id,
            ProjectLink.remote_project_id == project_id,
            ProjectLink.state == "linked",
        )
    )
    if identity is None or link is None or identity.provider_installation_id is None:
        raise ApiError(ErrorCategory.PERMISSION, "linked GitHub project is unavailable")
    retained = await db.get(TechnologyScan, (organization_id, payload.scan_id))
    if retained is not None:
        handoff = TechnologyScanHandoff.model_validate(retained.handoff["handoff"])
        if (
            retained.project_id != project_id
            or handoff.scope != f"github/{provider_project_id}"
            or handoff.mapping_version != payload.mapping_version
        ):
            raise ApiError(ErrorCategory.CONFLICT, "scan ID was reused")
    else:
        if identity.immutable_repository_id is None:
            raise ApiError(ErrorCategory.CONFLICT, "GitHub repository identity is incomplete")
        try:
            repository_id = int(identity.immutable_repository_id.removeprefix("github:"))
            installation_id = int(identity.provider_installation_id)
        except ValueError:
            raise ApiError(
                ErrorCategory.CONFLICT, "GitHub repository identity is incomplete"
            ) from None
        try:
            connector, token = await load_connector(
                db,
                account_id=ctx.account_id,
                purpose="source",
                settings=settings.github_connector,
            )
            if connector.github_subject != await _linked_subject(db, ctx.account_id):
                raise GitHubError("github_identity_mismatch", status=403)
            repository = await require_repository(
                client,
                token=token,
                purpose="source",
                settings=settings.github_connector,
                installation_id=installation_id,
                repository_id=repository_id,
            )
            metadata = object_data(
                (await client.api("GET", f"/repositories/{repository_id}", token=token)).data
            )
            branch = metadata.get("default_branch")
            if not isinstance(branch, str) or not 1 <= len(branch) <= 128:
                raise GitHubError("invalid_upstream_response")
            commits_data = (
                await client.api(
                    "GET",
                    f"/repos/{repository.full_name}/commits",
                    token=token,
                    params={"sha": branch, "per_page": 1},
                )
            ).data
            if not isinstance(commits_data, list):
                raise GitHubError("invalid_upstream_response")
            commits = cast(list[object], commits_data)
            if len(commits) != 1:
                raise GitHubError("invalid_upstream_response")
            head = object_data(commits[0]).get("sha")
            if (
                not isinstance(head, str)
                or len(head) != 40
                or any(character not in "0123456789abcdef" for character in head)
            ):
                raise GitHubError("invalid_upstream_response")
            raw = object_data(
                (
                    await client.api("GET", f"/repos/{repository.full_name}/languages", token=token)
                ).data
            )
            if len(raw) > 100 or any(
                not 1 <= len(name) <= 80
                or type(value) is not int
                or not 0 <= value <= 1_000_000_000_000
                for name, value in raw.items()
            ):
                raise GitHubError("invalid_upstream_response")
            languages = {name: float(cast(int, value)) for name, value in raw.items()}
        except GitHubError as error:
            raise api_error(error) from None
        locked = await db.scalar(
            select(Organization).where(Organization.id == organization_id).with_for_update()
        )
        if locked is None:
            raise ApiError(ErrorCategory.PERMISSION, "organization access denied")
        await db.refresh(identity)
        await db.refresh(link)
        if (
            identity.provider_installation_id != str(installation_id)
            or (identity.immutable_repository_id or "").removeprefix("github:")
            != str(repository_id)
            or link.state != "linked"
        ):
            raise ApiError(ErrorCategory.PRECONDITION, "GitHub observation or project link changed")
        handoff = await language_handoff(
            db,
            organization_id=organization_id,
            project_id=project_id,
            scan_id=payload.scan_id,
            mapping_version=payload.mapping_version,
            provider="github",
            provider_project_id=provider_project_id,
            repository_id=repository_id,
            head=head,
            observed_at=format_timestamp(datetime.now(UTC)),
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
