"""Bounded entity action reads under the current authenticated principal."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, optional_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.entity_actions.service import read_menu
from ai_stp_contracts.entity_actions import EntityActionMenus, EntityActionQuery

router = APIRouter(tags=["entity-actions"])


@router.post("/entity-actions/query", response_model=EntityActionMenus)
async def query_entity_actions(
    payload: EntityActionQuery,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext | None, Depends(optional_auth)],
) -> EntityActionMenus:
    response.headers["Cache-Control"] = "no-store, private"
    menus = {}
    for subject in payload.subjects:
        if subject not in menus:
            menus[subject] = await read_menu(db, ctx=ctx, subject=subject)
    return EntityActionMenus(items=[menus[subject] for subject in payload.subjects])
