"""Organization-gated, CSRF-protected GitLab read-only connector endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, get_settings, require_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.corporate import service as corporate_service
from ai_stp_api.slices.gitlab_connector import service
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.gitlab_connector import (
    GitLabConnectorStatus,
    GitLabConnectRequest,
    GitLabConnectResponse,
    GitLabDisconnectRequest,
    GitLabSourcePrepared,
    GitLabSourcePrepareRequest,
)
from ai_stp_platform.gitlab_client import GitLabClient, GitLabError
from ai_stp_platform.gitlab_settings import GitLabConnection
from ai_stp_platform.storage.object_store import ImmutableObjectStore

router = APIRouter(tags=["gitlab-connector"])
Db = Annotated[AsyncSession, Depends(get_db)]
Auth = Annotated[AuthContext, Depends(require_auth)]
Config = Annotated[Settings, Depends(get_settings)]


def _connection(settings: Settings, organization_id: str) -> GitLabConnection:
    connection = settings.gitlab.connections.get(organization_id)
    if connection is None:
        raise GitLabError("connector_not_configured")
    return connection


def _client(request: Request, connection: GitLabConnection) -> GitLabClient:
    injected = getattr(request.app.state, "gitlab_client", None)
    candidate = GitLabClient(
        connection.base_url, allowed_hosts=connection.allowed_hosts, auth="bearer"
    )
    if injected is not None and injected.base_url == candidate.base_url:
        return injected
    return candidate


@router.post("/corporate/organizations/{organization_id}/gitlab/connect")
async def connect(
    organization_id: OrganizationId,
    body: GitLabConnectRequest,
    request: Request,
    db: Db,
    ctx: Auth,
    settings: Config,
) -> GitLabConnectResponse:
    await corporate_service.organization_and_membership(
        db, ctx=ctx, organization_id=organization_id
    )
    client = _client(request, _connection(settings, organization_id))
    return await service.start_connect(
        db,
        ctx=ctx,
        organization_id=organization_id,
        body_locale=body.locale,
        settings=settings,
        client=client,
    )


@router.get("/connectors/gitlab/callback", response_model=None)
async def callback(
    request: Request,
    db: Db,
    ctx: Auth,
    settings: Config,
    state: Annotated[str, Query(min_length=1, max_length=128)],
    code: Annotated[str | None, Query(max_length=1024)] = None,
) -> RedirectResponse:
    locale, _status = await service.finish_connect(
        db,
        ctx=ctx,
        state=state,
        code=code,
        settings=settings,
        client_for=lambda connection: _client(request, connection),
    )
    return RedirectResponse(
        f"{settings.auth.public_base_url.rstrip('/')}/{locale}/account",
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("/corporate/organizations/{organization_id}/gitlab/connection")
async def connection_status(
    organization_id: OrganizationId,
    request: Request,
    db: Db,
    ctx: Auth,
    settings: Config,
) -> GitLabConnectorStatus:
    await corporate_service.organization_and_membership(
        db, ctx=ctx, organization_id=organization_id
    )
    client = _client(request, _connection(settings, organization_id))
    return await service.read_status(
        db, ctx=ctx, organization_id=organization_id, settings=settings, client=client
    )


@router.post("/corporate/organizations/{organization_id}/gitlab/connection/disconnect")
async def disconnect(
    organization_id: OrganizationId,
    body: GitLabDisconnectRequest,
    request: Request,
    db: Db,
    ctx: Auth,
    settings: Config,
) -> GitLabConnectorStatus:
    await corporate_service.organization_and_membership(
        db, ctx=ctx, organization_id=organization_id
    )
    client = _client(request, _connection(settings, organization_id))
    await service.disconnect(
        db, ctx=ctx, organization_id=organization_id, gitlab_base_url=client.base_url
    )
    return await service.read_status(
        db, ctx=ctx, organization_id=organization_id, settings=settings, client=client
    )


@router.post("/corporate/organizations/{organization_id}/gitlab/sources")
async def prepare_source(
    organization_id: OrganizationId,
    body: GitLabSourcePrepareRequest,
    request: Request,
    db: Db,
    ctx: Auth,
    settings: Config,
) -> GitLabSourcePrepared:
    await corporate_service.organization_and_membership(
        db, ctx=ctx, organization_id=organization_id
    )
    client = _client(request, _connection(settings, organization_id))
    store = ImmutableObjectStore(settings=settings.storage, client=request.app.state.object_client)
    return await service.prepare_source(
        db,
        ctx=ctx,
        organization_id=organization_id,
        body=body,
        settings=settings,
        client=client,
        store=store,
    )
