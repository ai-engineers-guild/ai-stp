"""Closed registry of job-type handlers (SPEC-018 REQ-1802, SPEC-026)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.queue.states import JobType
from ai_stp_worker.handlers.catalog_enrichment import handle_catalog_enrichment
from ai_stp_worker.handlers.deliver_invitation import handle_deliver_invitation
from ai_stp_worker.handlers.github_archive import handle_github_archive
from ai_stp_worker.handlers.publish import handle_publish
from ai_stp_worker.handlers.reevaluate import handle_reevaluate
from ai_stp_worker.handlers.repository_metrics import handle_repository_metrics
from ai_stp_worker.handlers.update import handle_update
from ai_stp_worker.handlers.upload import handle_upload
from ai_stp_worker.handlers.validate import handle_validate

JobHandler = Callable[[AsyncSession, Mapping[str, object]], Awaitable[None]]


async def _upload(session: AsyncSession, payload: Mapping[str, object]) -> None:
    del session
    await handle_upload(payload)


async def _update(session: AsyncSession, payload: Mapping[str, object]) -> None:
    del session
    await handle_update(payload)


REGISTRY: Mapping[JobType, JobHandler] = {
    JobType.UPLOAD: _upload,
    JobType.UPDATE: _update,
    JobType.VALIDATE: handle_validate,
    JobType.PUBLISH: handle_publish,
    JobType.REEVALUATE_ELIGIBILITY: handle_reevaluate,
    JobType.DELIVER_INVITATION: handle_deliver_invitation,
    JobType.REPOSITORY_METRICS: handle_repository_metrics,
    JobType.GITHUB_ARCHIVE: handle_github_archive,
    JobType.CATALOG_ENRICHMENT: handle_catalog_enrichment,
}


def resolve(job_type: str) -> JobHandler | None:
    """Return the handler for a job type string, or None if unregistered."""
    try:
        typed = JobType(job_type)
    except ValueError:
        return None
    return REGISTRY.get(typed)
