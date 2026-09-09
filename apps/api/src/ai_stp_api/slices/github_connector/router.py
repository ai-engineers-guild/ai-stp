"""Authenticated, CSRF-protected GitHub source connection endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, get_settings, require_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.github_connector import actions, service
from ai_stp_contracts.github_connector import (
    GitHubActionConfirmRequest,
    GitHubActionPlanRequest,
    GitHubActionPlanResponse,
    GitHubConnectorStatus,
    GitHubConnectRequest,
    GitHubConnectResponse,
    GitHubDisconnectRequest,
    GitHubSourcePrepared,
    GitHubSourcePrepareRequest,
)
from ai_stp_platform.github_client import GitHubClient
from ai_stp_platform.storage.object_store import ImmutableObjectStore

router = APIRouter(prefix="/connectors/github", tags=["github-connector"])
Db = Annotated[AsyncSession, Depends(get_db)]
Auth = Annotated[AuthContext, Depends(require_auth)]
Config = Annotated[Settings, Depends(get_settings)]


def get_client(request: Request) -> GitHubClient:
    return getattr(request.app.state, "github_client", None) or GitHubClient()


Client = Annotated[GitHubClient, Depends(get_client)]


@router.post("/connect")
async def connect(
    body: GitHubConnectRequest, db: Db, ctx: Auth, settings: Config
) -> GitHubConnectResponse:
    return await service.start_connect(db, ctx=ctx, body=body, settings=settings)


@router.get("/callback", response_model=None)
async def callback(
    db: Db,
    ctx: Auth,
    settings: Config,
    client: Client,
    state: Annotated[str, Query(min_length=1, max_length=128)],
    code: Annotated[str | None, Query(max_length=1024)] = None,
    setup_action: Annotated[str | None, Query(max_length=32)] = None,
) -> RedirectResponse:
    locale, _status, authorization_url = await service.finish_connect(
        db,
        ctx=ctx,
        state=state,
        code=code,
        setup_action=setup_action,
        settings=settings,
        client=client,
    )
    if authorization_url is not None:
        return RedirectResponse(
            authorization_url,
            status_code=303,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )
    return RedirectResponse(
        f"{settings.auth.public_base_url.rstrip('/')}/{locale}/account/github",
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("")
async def status(db: Db, ctx: Auth, settings: Config, client: Client) -> GitHubConnectorStatus:
    return await service.read_status(db, ctx=ctx, settings=settings, client=client)


@router.post("/disconnect")
async def disconnect(
    body: GitHubDisconnectRequest, db: Db, ctx: Auth, settings: Config, client: Client
) -> GitHubConnectorStatus:
    await service.disconnect(db, ctx=ctx, purpose=body.purpose)
    return await service.read_status(db, ctx=ctx, settings=settings, client=client)


@router.post("/sources")
async def prepare_source(
    body: GitHubSourcePrepareRequest,
    request: Request,
    db: Db,
    ctx: Auth,
    settings: Config,
    client: Client,
) -> GitHubSourcePrepared:
    store = ImmutableObjectStore(settings=settings.storage, client=request.app.state.object_client)
    return await service.prepare_source(
        db,
        ctx=ctx,
        body=body,
        settings=settings,
        client=client,
        store=store,
    )


@router.post("/actions")
async def plan_action(
    body: GitHubActionPlanRequest,
    db: Db,
    ctx: Auth,
    settings: Config,
    client: Client,
) -> GitHubActionPlanResponse:
    return await actions.create_plan(db, ctx=ctx, body=body, settings=settings, client=client)


@router.get("/actions/{plan_id}")
async def read_action(
    plan_id: str,
    db: Db,
    ctx: Auth,
    settings: Config,
    client: Client,
) -> GitHubActionPlanResponse:
    return await actions.read_plan(db, ctx=ctx, plan_id=plan_id, settings=settings, client=client)


@router.post("/actions/{plan_id}/confirm")
async def confirm_action(
    plan_id: str,
    body: GitHubActionConfirmRequest,
    db: Db,
    ctx: Auth,
    settings: Config,
    client: Client,
) -> GitHubActionPlanResponse:
    return await actions.confirm(
        db,
        ctx=ctx,
        plan_id=plan_id,
        body=body,
        settings=settings,
        client=client,
    )
