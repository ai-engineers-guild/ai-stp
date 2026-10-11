"""Tenant-scoped technology scan over a linked GitHub project."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.github_research import GitHubScanAdapter
from ai_stp_platform.github_settings import GitHubConnectorSettings
from ai_stp_platform.repository_scan import scan_linked_repository
from ai_stp_worker.handlers.repository_scan import parse_scan_job, user_principal


async def handle_github_technology_scan(
    session: AsyncSession, payload: Mapping[str, object]
) -> None:
    job = parse_scan_job(payload, job_label="github_technology_scan")
    await scan_linked_repository(
        session,
        organization_id=job.organization_id,
        provider_project_id=job.provider_project_id,
        project_id=job.project_id,
        scan_id=job.scan_id,
        mapping_version=job.mapping_version,
        adapter=GitHubScanAdapter(
            principal_id=user_principal(job, job_label="github_technology_scan"),
            settings=GitHubConnectorSettings(),
        ),
    )
