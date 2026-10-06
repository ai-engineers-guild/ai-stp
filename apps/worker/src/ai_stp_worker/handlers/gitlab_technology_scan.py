"""Tenant-scoped technology scan over a linked GitLab project (ADR-0224)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.gitlab_client import GitLabError
from ai_stp_platform.gitlab_research import scan_linked_gitlab_project
from ai_stp_platform.gitlab_settings import GitLabSettings
from ai_stp_platform.queue.engine import TENANT_ENVELOPE_KEY
from ai_stp_platform.queue.states import PermanentJobFailure


def _field(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise PermanentJobFailure(f"gitlab_technology_scan requires {name}")
    return value


async def handle_gitlab_technology_scan(
    session: AsyncSession, payload: Mapping[str, object]
) -> None:
    envelope = payload.get(TENANT_ENVELOPE_KEY)
    if not isinstance(envelope, Mapping):
        raise PermanentJobFailure("gitlab_technology_scan requires a tenant envelope")
    organization_id = cast(Mapping[str, object], envelope).get("organization_id")
    if not isinstance(organization_id, str) or not organization_id:
        raise PermanentJobFailure("gitlab_technology_scan requires organization_id")
    try:
        await scan_linked_gitlab_project(
            session,
            organization_id=organization_id,
            provider_project_id=_field(payload, "provider_project_id"),
            project_id=_field(payload, "project_id"),
            scan_id=_field(payload, "scan_id"),
            mapping_version=_field(payload, "mapping_version"),
            settings=GitLabSettings(),
        )
    except GitLabError:
        # Retryable upstream failures (rate limit, transient outage) bubble so
        # the queue schedules the next attempt instead of dead-lettering.
        raise
