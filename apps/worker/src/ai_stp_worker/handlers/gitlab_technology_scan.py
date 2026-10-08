"""Tenant-scoped technology scan over a linked GitLab project (ADR-0224)."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.gitlab_research import gitlab_scan_adapter
from ai_stp_platform.gitlab_settings import GitLabSettings
from ai_stp_platform.repository_scan import scan_linked_repository
from ai_stp_worker.handlers.repository_scan import parse_scan_job


async def handle_gitlab_technology_scan(
    session: AsyncSession, payload: Mapping[str, object]
) -> None:
    job = parse_scan_job(payload, job_label="gitlab_technology_scan")
    await scan_linked_repository(
        session,
        organization_id=job.organization_id,
        provider_project_id=job.provider_project_id,
        project_id=job.project_id,
        scan_id=job.scan_id,
        mapping_version=job.mapping_version,
        adapter=gitlab_scan_adapter(organization_id=job.organization_id, settings=GitLabSettings()),
    )
