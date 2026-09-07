"""PostgreSQL evidence for atomic exact-target latest assessment pointers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_contracts.assurance import TargetAssessmentIdentity
from ai_stp_platform.catalog_assessments import (
    _upsert_latest,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_platform.models import TargetAssessment, TargetAssessmentLatest

pytestmark = pytest.mark.platform


def _identity() -> TargetAssessmentIdentity:
    return TargetAssessmentIdentity(
        component_stable_id="component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        version="1.0",
        passport_digest="sha256:" + "a" * 64,
        adaptation_id="adaptation_" + "b" * 64,
        harness_id="codex",
        scope="global",
        projection_artifact_digest="sha256:" + "c" * 64,
        provider_id="ai-stp-publication",
        provider_version="1",
        surface_profile_id="codex/native-files/1",
        surface_profile_digest="sha256:" + "d" * 64,
        target_scope="global",
        harness_version="unspecified",
        operating_system="linux",
        architecture="x86_64",
        policy_version="safety-3",
    )


@pytest.mark.asyncio
async def test_concurrent_assessments_leave_one_latest_and_newer_wins(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    identity = _identity()
    key = "sha256:" + "e" * 64
    older = datetime.now(UTC) - timedelta(minutes=1)
    newer = datetime.now(UTC)

    async def write(*, state: str, observed_at: datetime, suffix: str) -> int:
        async with db_sessionmaker() as session, session.begin():
            row = TargetAssessment(
                target_key_digest=key,
                identity=identity.model_dump(mode="json"),
                stored_state=state,
                compatibility_result="not_run",
                evidence_refs=[],
                observed_at=observed_at,
                expires_at=None,
                idempotency_key="assessment-race-" + suffix,
                payload_digest="sha256:" + suffix.ljust(64, "0"),
            )
            session.add(row)
            await session.flush()
            await _upsert_latest(
                session,
                key=key,
                assessment_id=row.id,
                identity=identity,
                stored_state=state,
                expires_at=None,
                updated_at=observed_at,
            )
            return row.id

    ids = await asyncio.gather(
        write(state="verified", observed_at=newer, suffix="new"),
        write(state="failed", observed_at=older, suffix="old"),
    )

    async with db_sessionmaker() as session:
        latest = await session.get(TargetAssessmentLatest, key)
        assert latest is not None
        assert latest.assessment_id == ids[0]
        assert latest.stored_state == "verified"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TargetAssessmentLatest)
                .where(TargetAssessmentLatest.target_key_digest == key)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TargetAssessment)
                .where(TargetAssessment.target_key_digest == key)
            )
            == 2
        )
