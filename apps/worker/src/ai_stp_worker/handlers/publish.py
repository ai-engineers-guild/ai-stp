"""Publish catalog version job (SPEC-026)."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.publication_logic import execute_publish
from ai_stp_platform.safety.artifact_fetch import close_env_object_store, open_env_object_store


async def handle_publish(session: AsyncSession, payload: Mapping[str, object]) -> None:
    plan_id = payload.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id:
        msg = "publish requires plan_id"
        raise ValueError(msg)
    store = await open_env_object_store()
    try:
        await execute_publish(session, plan_id=plan_id, store=store)
    finally:
        await close_env_object_store(store)
