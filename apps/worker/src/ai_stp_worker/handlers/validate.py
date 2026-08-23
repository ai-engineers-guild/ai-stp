"""Validate publication plan job (SPEC-026)."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.publication_logic import execute_validate


async def handle_validate(session: AsyncSession, payload: Mapping[str, object]) -> None:
    """Run validate including safety suite with object-store artifact fetch.

    ``execute_validate`` resolves artifact bytes from ``AI_STP_STORAGE_*`` when
    configured (content-addressed key + digest re-verify). Optional payload keys
    for tests: none on the wire; inject store via execute_validate in unit tests.
    """
    plan_id = payload.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id:
        msg = "validate requires plan_id"
        raise ValueError(msg)
    # Production path: execute_validate opens env object store and downloads
    # the content-addressed artifact before the staged safety suite.
    await execute_validate(session, plan_id=plan_id, release_read_transaction=True)
