"""Unit tests for catalog writes sharing a transaction with enqueue."""

from __future__ import annotations

from typing import Any

import pytest

from ai_stp_platform import catalog
from ai_stp_platform.models import CatalogMetadata
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobType, Visibility

pytestmark = pytest.mark.platform


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = False

    def add(self, value: object) -> None:
        self.added.append(value)
        if isinstance(value, CatalogMetadata):
            value.id = 42

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_catalog_write_enqueues_upload_in_same_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = RecordingSession()
    seen: dict[str, Any] = {}
    queued_job = Job(id=7, job_type=str(JobType.UPLOAD), payload={})

    async def fake_enqueue(
        called_session: object,
        *,
        job_type: JobType,
        payload: dict[str, object],
        idempotency_key: str,
    ) -> Job:
        seen.update(
            session=called_session,
            job_type=job_type,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        return queued_job

    monkeypatch.setattr(catalog, "enqueue", fake_enqueue)

    result = await catalog.create_catalog_metadata_and_enqueue_upload(
        session,  # type: ignore[arg-type]
        owner_account_id="account_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        object_kind="component",
        stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        current_revision_id="revision_" + "a" * 64,
        visibility=Visibility.PRIVATE,
        idempotency_key="idem-1",
    )

    assert result.metadata in session.added
    assert result.job is queued_job
    assert session.flushed is True
    assert seen["session"] is session
    assert seen["job_type"] is JobType.UPLOAD
    assert seen["payload"] == {
        "catalog_metadata_id": result.metadata.id,
        "stable_id": result.metadata.stable_id,
        "visibility": str(Visibility.PRIVATE),
    }
    assert seen["idempotency_key"] == "idem-1"
