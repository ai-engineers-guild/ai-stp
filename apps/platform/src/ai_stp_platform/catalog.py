"""Catalog persistence helpers that share transactions with the job queue."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.models import CatalogMetadata
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobType, Visibility


@dataclass(frozen=True)
class CatalogWriteResult:
    """Rows created by one catalog write path."""

    metadata: CatalogMetadata
    job: Job


async def create_catalog_metadata_and_enqueue_upload(
    session: AsyncSession,
    *,
    owner_account_id: str,
    object_kind: str,
    stable_id: str,
    current_revision_id: str,
    visibility: Visibility,
    idempotency_key: str,
    version: str | None = None,
    name: str | None = None,
) -> CatalogWriteResult:
    """Create catalog metadata and enqueue upload in the caller's transaction."""
    metadata = CatalogMetadata(
        owner_account_id=owner_account_id,
        object_kind=object_kind,
        stable_id=stable_id,
        current_revision_id=current_revision_id,
        visibility=str(visibility),
        lifecycle_state="draft",
        version=version,
        name=name,
    )
    session.add(metadata)
    await session.flush()
    job = await enqueue(
        session,
        job_type=JobType.UPLOAD,
        payload={
            "catalog_metadata_id": metadata.id,
            "stable_id": stable_id,
            "visibility": str(visibility),
        },
        idempotency_key=idempotency_key,
    )
    return CatalogWriteResult(metadata=metadata, job=job)
