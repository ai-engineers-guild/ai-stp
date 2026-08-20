"""Reevaluate install eligibility job (SPEC-026 / ADR-0032)."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.publication_logic import execute_reevaluate_eligibility


async def handle_reevaluate(session: AsyncSession, payload: Mapping[str, object]) -> None:
    object_kind = payload.get("object_kind")
    stable_id = payload.get("stable_id")
    version = payload.get("version")
    if not all(isinstance(v, str) and v for v in (object_kind, stable_id, version)):
        msg = "reevaluate_eligibility requires object_kind, stable_id, version"
        raise ValueError(msg)
    await execute_reevaluate_eligibility(
        session,
        object_kind=str(object_kind),
        stable_id=str(stable_id),
        version=str(version),
    )
