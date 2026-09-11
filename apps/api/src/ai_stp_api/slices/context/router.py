"""Product context, organization, capability and project-link routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, optional_auth, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.local_session import require as require_local_session
from ai_stp_api.local_session import start as start_local_session
from ai_stp_api.local_session import stop as stop_local_session
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.context import service
from ai_stp_contracts.context import (
    ActiveContext,
    OrganizationListResponse,
    OrganizationSummary,
    ProductMode,
    ProjectConflictResolutionRequest,
    ProjectLinkPlanRequest,
    ProjectLinkProposalRequest,
    ProjectLinkRequest,
    ProjectRevisionPushRequest,
    ProjectSyncApplyRequest,
    ProjectSyncPlanRequest,
    ProjectUnlinkPlanRequest,
    ProjectUnlinkRequest,
    ProviderProjectObservationRequest,
)
from ai_stp_foundation.timestamps import format_timestamp

router = APIRouter(tags=["context"])
_NO_STORE = {"Cache-Control": "private, no-store"}


@router.post("/local/session", response_model=None)
async def create_local_session(request: Request) -> JSONResponse:
    session = await start_local_session(request)
    return JSONResponse(
        content={
            "session": session.token,
            "csrf": session.csrf_token,
            "expires_at": format_timestamp(session.expires_at),
            "api_base_url": session.api_base_url,
        },
        headers=_NO_STORE,
    )


@router.delete("/local/session", response_model=None)
async def delete_local_session(request: Request) -> JSONResponse:
    await stop_local_session(request)
    return JSONResponse(content={"ok": True}, headers=_NO_STORE)


def _organization_body(organization: object) -> dict[str, object]:
    # The ORM type is kept out of the contract package. This function is the
    # only wire projection for organization rows.
    item = organization
    return {
        "schema_version": 1,
        "organization_id": item.id,  # type: ignore[attr-defined]
        "kind": item.kind,  # type: ignore[attr-defined]
        "display_name": item.display_name,  # type: ignore[attr-defined]
        "membership_revision": item.revision,  # type: ignore[attr-defined]
    }


@router.get("/context", response_model=None)
async def read_context(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext | None, Depends(optional_auth)],
    organization_id: Annotated[str | None, Header(alias="X-AI-STP-Organization-Id")] = None,
    product_mode: Annotated[str | None, Header(alias="X-AI-STP-Product-Mode")] = None,
) -> JSONResponse:
    """Resolve a loopback context or the backend-owned remote context."""
    if product_mode == "local":
        require_local_session(request)
        if organization_id is not None:
            raise ApiError(ErrorCategory.VALIDATION, "local context cannot name an organization")
        projection = service.projection_for(mode="local", organization_id=None)
        return JSONResponse(
            content=ActiveContext(
                mode="local", organization_id=None, capabilities=projection
            ).model_dump(mode="json"),
            headers=_NO_STORE,
        )
    if product_mode is not None:
        raise ApiError(ErrorCategory.VALIDATION, "product mode is not selectable by name")
    if ctx is None:
        if organization_id is not None:
            raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication required")
        projection = service.projection_for(mode="local", organization_id=None)
        return JSONResponse(
            content=ActiveContext(
                mode="local", organization_id=None, capabilities=projection
            ).model_dump(mode="json"),
            headers=_NO_STORE,
        )
    organization = (
        await service.require_membership(db, ctx=ctx, organization_id=organization_id)
        if organization_id is not None
        else await service.personal_organization(db, account_id=ctx.account_id, create=True)
    )
    if organization is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "personal organization not found")
    projection = await service.remote_projection(db, ctx=ctx, organization_id=organization.id)
    return JSONResponse(
        content=ActiveContext(
            mode=cast(ProductMode, organization.kind),
            organization_id=organization.id,
            capabilities=projection,
        ).model_dump(mode="json"),
        headers=_NO_STORE,
    )


@router.get("/organizations", response_model=None)
async def list_organizations(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    items = await service.organizations_for_account(db, account_id=ctx.account_id)
    body = OrganizationListResponse(
        items=[OrganizationSummary.model_validate(_organization_body(item)) for item in items]
    )
    return JSONResponse(content=body.model_dump(mode="json"), headers=_NO_STORE)


@router.get("/organizations/{organization_id}/capabilities", response_model=None)
async def read_organization_capabilities(
    organization_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    body = await service.remote_projection(db, ctx=ctx, organization_id=organization_id)
    return JSONResponse(content=body.model_dump(mode="json"), headers=_NO_STORE)


@router.post("/organizations/{organization_id}/provider-project-observations", response_model=None)
async def observe_provider_project(
    organization_id: str,
    payload: ProviderProjectObservationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    identity = await service.observe_provider_project(
        db, ctx=ctx, organization_id=organization_id, payload=payload
    )
    return JSONResponse(
        content={
            "schema_version": 1,
            "provider_project_id": identity.id,
            "organization_id": identity.organization_id,
            "provider_kind": identity.provider_kind,
            "installation_id": identity.provider_installation_id,
            "namespace_id": identity.provider_namespace_id,
            "immutable_repository_id": identity.immutable_repository_id,
            "current_url": identity.current_url,
            "observed_name": identity.observed_name,
            "revision": identity.revision,
            "observed_at": format_timestamp(
                (identity.observed_at or datetime.now(UTC)).astimezone(UTC)
            ),
        },
        status_code=201,
    )


@router.post("/organizations/{organization_id}/project-link-proposals", response_model=None)
async def create_project_link_proposal(
    organization_id: str,
    payload: ProjectLinkProposalRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    proposal = await service.create_project_link_proposal(
        db, ctx=ctx, organization_id=organization_id, payload=payload
    )
    return JSONResponse(
        content={
            "schema_version": 1,
            "proposal_id": proposal.id,
            "organization_id": proposal.organization_id,
            "local_project_id": proposal.local_project_id,
            "remote_project_id": proposal.remote_project_id,
            "provider_project_id": proposal.provider_project_id,
            "evidence": proposal.evidence,
            "state": proposal.state,
            "created_at": format_timestamp(
                (proposal.created_at or datetime.now(UTC)).astimezone(UTC)
            ),
        },
        status_code=201,
    )


@router.post("/projects/links", response_model=None)
async def create_project_link(
    payload: ProjectLinkRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    organization_id: Annotated[str | None, Header(alias="X-AI-STP-Organization-Id")] = None,
) -> JSONResponse:
    if organization_id is None:
        raise ApiError(ErrorCategory.VALIDATION, "organization context required")
    body = await service.create_project_link(
        db, ctx=ctx, organization_id=organization_id, payload=payload
    )
    return JSONResponse(content=body.model_dump(mode="json"), status_code=201)


@router.post("/organizations/{organization_id}/project-link-plans", response_model=None)
async def create_project_link_plan(
    organization_id: str,
    payload: ProjectLinkPlanRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    body = await service.create_project_link_plan(
        db, ctx=ctx, organization_id=organization_id, payload=payload
    )
    return JSONResponse(content=body.model_dump(mode="json"), status_code=201)


@router.get("/organizations/{organization_id}/project-link-plans/{plan_id}", response_model=None)
async def read_project_link_plan(
    organization_id: str,
    plan_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    body = await service.read_project_link_plan(
        db, ctx=ctx, organization_id=organization_id, plan_id=plan_id
    )
    return JSONResponse(content=body.model_dump(mode="json"))


@router.get("/projects/links/{link_id}", response_model=None)
async def read_project_link(
    link_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    organization_id: Annotated[str, Header(alias="X-AI-STP-Organization-Id")],
) -> JSONResponse:
    body = await service.read_project_link(
        db, ctx=ctx, organization_id=organization_id, link_id=link_id
    )
    return JSONResponse(content=body.model_dump(mode="json"))


@router.post("/organizations/{organization_id}/project-unlink-plans", response_model=None)
async def create_project_unlink_plan(
    organization_id: str,
    payload: ProjectUnlinkPlanRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    body = await service.create_project_unlink_plan(
        db, ctx=ctx, organization_id=organization_id, payload=payload
    )
    return JSONResponse(content=body.model_dump(mode="json"), status_code=201)


@router.get("/organizations/{organization_id}/project-unlink-plans/{plan_id}", response_model=None)
async def read_project_unlink_plan(
    organization_id: str,
    plan_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    body = await service.read_project_unlink_plan(
        db, ctx=ctx, organization_id=organization_id, plan_id=plan_id
    )
    return JSONResponse(content=body.model_dump(mode="json"))


@router.post("/projects/links/{link_id}/sync-plans", response_model=None)
async def create_project_sync_plan(
    link_id: str,
    payload: ProjectSyncPlanRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    organization_id: Annotated[str, Header(alias="X-AI-STP-Organization-Id")],
) -> JSONResponse:
    if payload.link_id != link_id:
        raise ApiError(ErrorCategory.VALIDATION, "link id does not match request path")
    body = await service.create_sync_plan(
        db, ctx=ctx, organization_id=organization_id, payload=payload
    )
    return JSONResponse(content=body.model_dump(mode="json"), status_code=201)


@router.delete("/projects/links/{link_id}", response_model=None)
async def unlink_project(
    link_id: str,
    payload: ProjectUnlinkRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    organization_id: Annotated[str, Header(alias="X-AI-STP-Organization-Id")],
) -> JSONResponse:
    body = await service.unlink_project_link(
        db,
        ctx=ctx,
        organization_id=organization_id,
        link_id=link_id,
        payload=payload,
    )
    return JSONResponse(content=body.model_dump(mode="json"))


@router.post("/projects/links/{link_id}/sync-plans/{plan_id}/apply", response_model=None)
async def apply_project_sync_plan(
    link_id: str,
    plan_id: str,
    payload: ProjectSyncApplyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    organization_id: Annotated[str, Header(alias="X-AI-STP-Organization-Id")],
) -> JSONResponse:
    plan = await service.apply_sync_plan(
        db,
        ctx=ctx,
        organization_id=organization_id,
        plan_id=plan_id,
        link_id=link_id,
        payload=payload,
    )
    return JSONResponse(content=plan.model_dump(mode="json"))


@router.post("/projects/links/{link_id}/revisions", response_model=None)
async def push_project_revision(
    link_id: str,
    payload: ProjectRevisionPushRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    organization_id: Annotated[str, Header(alias="X-AI-STP-Organization-Id")],
) -> JSONResponse:
    body = await service.push_project_revision(
        db,
        ctx=ctx,
        organization_id=organization_id,
        link_id=link_id,
        payload=payload,
    )
    return JSONResponse(content=body.model_dump(mode="json"))


@router.post("/projects/links/{link_id}/conflict-resolutions", response_model=None)
async def resolve_project_conflict(
    link_id: str,
    payload: ProjectConflictResolutionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    organization_id: Annotated[str, Header(alias="X-AI-STP-Organization-Id")],
) -> JSONResponse:
    body = await service.resolve_project_conflict(
        db,
        ctx=ctx,
        organization_id=organization_id,
        link_id=link_id,
        payload=payload,
    )
    return JSONResponse(content=body.model_dump(mode="json"))


@router.get("/projects/links/{link_id}/revisions", response_model=None)
async def pull_project_revisions(
    link_id: str,
    authorization_revision: Annotated[str, Header(alias="X-AI-STP-Authorization-Revision")],
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    organization_id: Annotated[str, Header(alias="X-AI-STP-Organization-Id")],
) -> JSONResponse:
    body = await service.pull_project_revisions(
        db,
        ctx=ctx,
        organization_id=organization_id,
        link_id=link_id,
        authorization_revision=authorization_revision,
    )
    return JSONResponse(content=body.model_dump(mode="json"))
